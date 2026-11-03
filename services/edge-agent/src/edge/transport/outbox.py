from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from shared.codec import MessageCodec
from shared.contract import EdgeEvent


class OutboxFullError(RuntimeError):
    """Raised when adding an event would exceed the configured spool limit."""


class EventConflictError(RuntimeError):
    """Raised when one event ID is reused with different content or topic."""


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    event_id: str
    topic: str
    payload: bytes
    attempts: int


class SQLiteOutbox:
    def __init__(self, path: str, max_bytes: int = 100 * 1024 * 1024) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.path = path
        self.max_bytes = max_bytes
        self._memory_connection = (
            sqlite3.connect(":memory:") if path == ":memory:" else None
        )
        if path != ":memory:":
            database_path = Path(path)
            database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )

        if path != ":memory:":
            os.chmod(path, 0o600)

    def enqueue(self, event_id: str, topic: str, payload: bytes) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT topic, payload FROM outbox WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != topic or existing[1] != payload:
                    raise EventConflictError(
                        "event_id already exists with different topic or payload"
                    )
                return

            used_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(payload) + "
                "length(CAST(topic AS BLOB))), 0) FROM outbox"
            ).fetchone()[0]
            new_size = len(payload) + len(topic.encode("utf-8"))
            if used_bytes + new_size > self.max_bytes:
                raise OutboxFullError("disk outbox capacity would be exceeded")

            connection.execute(
                "INSERT INTO outbox (event_id, topic, payload) VALUES (?, ?, ?)",
                (event_id, topic, payload),
            )

    def pending(self, limit: int = 100) -> tuple[OutboxMessage, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, topic, payload, attempts
                FROM outbox ORDER BY created_at, event_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(OutboxMessage(*row) for row in rows)

    def mark_published(self, event_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM outbox WHERE event_id = ?", (event_id,))

    def mark_failed(self, event_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_error = ? "
                "WHERE event_id = ?",
                (error[:500], event_id),
            )

    def usage(self) -> tuple[int, int]:
        with self._connect() as connection:
            count, byte_count = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(payload) + "
                "length(CAST(topic AS BLOB))), 0) "
                "FROM outbox"
            ).fetchone()
        return count, byte_count

    def close(self) -> None:
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        memory_connection = self._memory_connection
        if self.path == ":memory:" and memory_connection is None:
            raise RuntimeError("outbox is closed")
        connection = memory_connection or sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            if memory_connection is None:
                connection.close()


@dataclass(frozen=True, slots=True)
class FlushReport:
    published: int
    pending: int


class ReliableMqttTransport:
    def __init__(
        self,
        client: Any,
        outbox: SQLiteOutbox,
        codec: MessageCodec,
        topic: str,
        ack_timeout: float = 10.0,
    ) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        if ack_timeout <= 0:
            raise ValueError("ack_timeout must be positive")
        self.client = client
        self.outbox = outbox
        self.codec = codec
        self.topic = topic
        self.ack_timeout = ack_timeout

    def submit(self, event: EdgeEvent) -> FlushReport:
        self.outbox.enqueue(event.event_id, self.topic, self.codec.encode(event))
        return self.flush(limit=1)

    def flush(self, limit: int = 100) -> FlushReport:
        if limit < 1:
            raise ValueError("limit must be positive")
        published = 0
        for message in self.outbox.pending(limit):
            try:
                info = self.client.publish(message.topic, message.payload, qos=1)
                info.wait_for_publish(timeout=self.ack_timeout)
                if getattr(info, "rc", 0) != 0 or not info.is_published():
                    raise RuntimeError("broker acknowledgement was not received")
            except Exception as error:
                self.outbox.mark_failed(message.event_id, str(error))
                break
            self.outbox.mark_published(message.event_id)
            published += 1
        pending_count, _ = self.outbox.usage()
        return FlushReport(published=published, pending=pending_count)

    def usage(self) -> tuple[int, int]:
        return self.outbox.usage()
