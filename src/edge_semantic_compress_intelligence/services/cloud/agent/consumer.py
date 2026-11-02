from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

from edge_semantic_compress_intelligence.shared.codec import MessageCodec
from edge_semantic_compress_intelligence.shared.contract import EdgeEvent


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
        try:
            event = self.codec.decode(delivery.payload)
        except Exception:
            return ConsumeResult(disposition="invalid_payload")

        payload_hash = hashlib.sha256(delivery.payload).hexdigest()
        try:
            with self._lock:
                previous_hash = self.store.payload_hash(event.event_id)
                if previous_hash is not None:
                    if previous_hash != payload_hash:
                        return ConsumeResult(
                            disposition="event_id_conflict",
                            event_id=event.event_id,
                        )
                    disposition = "duplicate"
                else:
                    self.handler(event)
                    self.store.mark_processed(event.event_id, payload_hash)
                    disposition = "processed"
        except Exception:
            return ConsumeResult(
                disposition="processing_failed",
                event_id=event.event_id,
            )

        try:
            result = client.ack(delivery.mid, delivery.qos)
        except Exception:
            return ConsumeResult(disposition="ack_failed", event_id=event.event_id)
        if result != 0:
            return ConsumeResult(disposition="ack_failed", event_id=event.event_id)
        return ConsumeResult(disposition=disposition, event_id=event.event_id)