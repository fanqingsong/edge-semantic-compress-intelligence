from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from edge_semantic_compress_intelligence.services.cloud.feedback.service import (
    PromptFeedbackService,
)
from edge_semantic_compress_intelligence.services.cloud.rag.analysis import (
    RagResult,
    RagService,
)
from edge_semantic_compress_intelligence.shared.contract import EdgeEvent


class SQLiteAnalysisStore:
    def __init__(self, path: str) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS analyses ("
                "event_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        if path != ":memory:":
            os.chmod(path, 0o600)

    def save(self, result: RagResult) -> None:
        serialized = json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analyses (event_id, result_json) VALUES (?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET result_json = excluded.result_json",
                (result.event_id, serialized),
            )

    def get(self, event_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class RagEventHandler:
    rag_service: RagService
    analysis_store: SQLiteAnalysisStore
    feedback_service: PromptFeedbackService | None = None

    def __call__(self, event: EdgeEvent) -> None:
        result = self.rag_service.analyze(event)
        self.analysis_store.save(result)
        if self.feedback_service is not None:
            self.feedback_service.observe(event, result)