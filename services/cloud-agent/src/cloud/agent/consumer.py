from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

from cloud.agent.graph import build_consume_graph
from shared.codec import MessageCodec
from shared.contract import EdgeEvent


class ProcessedEventConflict(RuntimeError):
    """Raised when one event ID is received with a different payload."""


class ProcessedEventStore(Protocol):
    def payload_hash(self, event_id: str) -> str | None:
        """Return the previously processed payload hash, if any."""

    def mark_processed(self, event_id: str, payload_hash: str) -> None:
        """Persist a successfully processed event identity."""


class SQLiteProcessedEventStore:
    def __init__(self, path: str) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        self.path = path
        self._memory_connection = (
            sqlite3.connect(":memory:") if path == ":memory:" else None
        )
        if path != ":memory:":
            database_path = Path(path)
            database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS processed_events ("
                "event_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, "
                "processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def payload_hash(self, event_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_hash FROM processed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row[0] if row else None

    def mark_processed(self, event_id: str, payload_hash: str) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM processed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != payload_hash:
                    raise ProcessedEventConflict(
                        "event_id already processed with a different payload"
                    )
                return
            connection.execute(
                "INSERT INTO processed_events (event_id, payload_hash) VALUES (?, ?)",
                (event_id, payload_hash),
            )

    def close(self) -> None:
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        memory_connection = self._memory_connection
        if self.path == ":memory:" and memory_connection is None:
            raise RuntimeError("processed event store is closed")
        connection = memory_connection or sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            if memory_connection is None:
                connection.close()


@dataclass(frozen=True, slots=True)
class MqttDelivery:
    mid: int
    qos: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class ConsumeResult:
    disposition: str
    event_id: str | None = None


class EventHandler(Protocol):
    def __call__(self, event: EdgeEvent) -> None:
        """Process the cloud event before it is acknowledged."""


class MqttEventConsumer:
    def __init__(
        self,
        topic: str,
        codec: MessageCodec,
        store: ProcessedEventStore,
        handler: EventHandler,
    ) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        self.topic = topic
        self.codec = codec
        self.store = store
        self.handler = handler
        self._lock = threading.Lock()
        self._graph = build_consume_graph(codec, store, handler)

    def bind(self, client: Any) -> None:
        client.manual_ack_set(True)
        client.on_connect = self.on_connect
        client.on_message = self.on_message

    def on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        if reason_code != 0:
            return
        result, _ = client.subscribe(self.topic, qos=1)
        if result != 0:
            raise RuntimeError("failed to subscribe to the configured MQTT topic")

    def on_message(self, client: Any, userdata: Any, message: Any) -> None:
        self.handle_message(
            client,
            MqttDelivery(
                mid=message.mid,
                qos=message.qos,
                payload=message.payload,
            ),
        )

    def handle_message(self, client: Any, delivery: MqttDelivery) -> ConsumeResult:
        result = self._process(delivery.payload)
        if result.disposition not in {"processed", "duplicate"}:
            return result
        try:
            ack_result = client.ack(delivery.mid, delivery.qos)
        except Exception:
            return ConsumeResult(disposition="ack_failed", event_id=result.event_id)
        if ack_result != 0:
            return ConsumeResult(disposition="ack_failed", event_id=result.event_id)
        return result

    def _process(self, payload: bytes) -> ConsumeResult:
        return process_payload(self._graph, self.codec, self._lock, payload)


class KafkaEventConsumer:
    def __init__(
        self,
        codec: MessageCodec,
        store: ProcessedEventStore,
        handler: EventHandler,
    ) -> None:
        self.codec = codec
        self.store = store
        self.handler = handler
        self._lock = threading.Lock()
        self._graph = build_consume_graph(codec, store, handler)

    def handle_payload(self, payload: bytes, commit: Callable[[], None]) -> ConsumeResult:
        result = process_payload(self._graph, self.codec, self._lock, payload)
        if result.disposition not in {"processed", "duplicate"}:
            return result
        try:
            commit()
        except Exception:
            return ConsumeResult(disposition="ack_failed", event_id=result.event_id)
        return result


def process_payload(
    graph: Any,
    codec: MessageCodec,
    lock: threading.Lock,
    payload: bytes,
) -> ConsumeResult:
    try:
        with lock:
            state = graph.invoke({"payload": payload})
    except Exception:
        return ConsumeResult(
            disposition="processing_failed",
            event_id=event_id_from_payload(codec, payload),
        )
    return ConsumeResult(
        disposition=state["disposition"],
        event_id=state.get("event_id"),
    )


def event_id_from_payload(codec: MessageCodec, payload: bytes) -> str | None:
    try:
        return codec.decode(payload).event_id
    except Exception:
        return None