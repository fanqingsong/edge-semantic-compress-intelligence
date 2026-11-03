from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from cloud.knowledge.ingest import IngestReport, KnowledgeCase


class CaseIngestor(Protocol):
    def ingest_cases(self, source: str, cases: Any) -> IngestReport:
        """Embed and upsert cases for one source document."""


class DocumentParser(Protocol):
    def parse_file(self, path: str | Path) -> tuple[KnowledgeCase, ...]:
        """Parse one saved upload into knowledge cases."""


class JobStore:
    def __init__(self, path: str) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        self.path = path
        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    upserted INTEGER,
                    removed_stale INTEGER,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        os.chmod(path, 0o600)

    def create(self, filename: str) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ingest_jobs (id, filename, status) VALUES (?, ?, 'queued')",
                (job_id, filename),
            )
        record = self.get(job_id)
        if record is None:
            raise RuntimeError("ingest job was not stored")
        return record

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, filename, status, upserted, removed_stale, error, created_at "
                "FROM ingest_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return _job(row) if row else None

    def latest(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, filename, status, upserted, removed_stale, error, created_at "
                "FROM ingest_jobs ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return _job(row) if row else None

    def mark(
        self,
        job_id: str,
        status: str,
        *,
        upserted: int | None = None,
        removed_stale: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE ingest_jobs SET status = ?, upserted = ?, removed_stale = ?, "
                "error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, upserted, removed_stale, error, job_id),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


class IngestWorker:
    """Run knowledge imports one at a time on a background thread."""

    def __init__(
        self,
        store: JobStore,
        parser: DocumentParser,
        ingestor: CaseIngestor,
        upload_dir: str,
    ) -> None:
        self.store = store
        self.parser = parser
        self.ingestor = ingestor
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[tuple[str, Path, str]] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="knowledge-ingest", daemon=True)
        self._thread.start()

    def submit(self, filename: str, content: bytes) -> dict[str, Any]:
        record = self.store.create(filename)
        destination = self.upload_dir / f"{record['id']}{Path(filename).suffix.casefold()}"
        try:
            destination.write_bytes(content)
        except OSError:
            self.store.mark(str(record["id"]), "failed", error="upload_failed")
            raise
        self._queue.put((str(record["id"]), destination, filename))
        return record

    def _loop(self) -> None:
        while True:
            job_id, path, filename = self._queue.get()
            self._execute(job_id, path, filename)

    def _execute(self, job_id: str, path: Path, filename: str) -> None:
        self.store.mark(job_id, "running")
        try:
            cases = self.parser.parse_file(path)
            report = self.ingestor.ingest_cases(filename, cases)
        except Exception as error:
            logging.exception("knowledge import failed for %s", filename)
            self.store.mark(job_id, "failed", error=str(error)[:500])
            return
        self.store.mark(
            job_id,
            "succeeded",
            upserted=report.upserted,
            removed_stale=report.removed_stale,
        )


def _job(row: tuple[Any, ...]) -> dict[str, Any]:
    job_id, filename, status, upserted, removed_stale, error, created_at = row
    return {
        "id": job_id,
        "filename": filename,
        "status": status,
        "upserted": upserted,
        "removed_stale": removed_stale,
        "error": error,
        "created_at": created_at,
    }
