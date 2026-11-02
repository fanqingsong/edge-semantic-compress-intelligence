from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.cloud.rag.analysis import RagResult


class FeedbackStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class FeedbackTransitionError(ValueError):
    """Raised when a feedback suggestion cannot enter the requested state."""


@dataclass(frozen=True, slots=True)
class PromptSuggestion:
    suggestion_id: str
    event_id: str
    category: str
    suggestion: str
    prompt_version: str
    evidence: tuple[str, ...]
    prompt_patch: str
    expected_metric: str
    validation_cases: tuple[str, ...]
    risk_note: str
    status: FeedbackStatus
    created_at: str
    reviewed_by: str | None = None
    review_note: str | None = None
    published_at: str | None = None


@dataclass(frozen=True, slots=True)
class WeeklyFeedbackReport:
    generated: int
    reviewed_valid: int
    published: int


class SQLiteFeedbackStore:
    def __init__(self, path: str) -> None:
        if not path.strip():
            raise ValueError("path must not be empty")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS prompt_suggestions ("
                "suggestion_id TEXT PRIMARY KEY, "
                "event_id TEXT NOT NULL, "
                "category TEXT NOT NULL, "
                "suggestion TEXT NOT NULL, "
                "prompt_version TEXT NOT NULL, "
                "evidence_json TEXT NOT NULL DEFAULT '[]', "
                "prompt_patch TEXT NOT NULL DEFAULT '', "
                "expected_metric TEXT NOT NULL DEFAULT '', "
                "validation_cases_json TEXT NOT NULL DEFAULT '[]', "
                "risk_note TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "reviewed_by TEXT, "
                "review_note TEXT, "
                "published_at TEXT, "
                "UNIQUE(event_id, category))"
            )
            existing_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(prompt_suggestions)")
            }
            migrations = {
                "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
                "prompt_patch": "TEXT NOT NULL DEFAULT ''",
                "expected_metric": "TEXT NOT NULL DEFAULT ''",
                "validation_cases_json": "TEXT NOT NULL DEFAULT '[]'",
                "risk_note": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE prompt_suggestions ADD COLUMN {column} {definition}"
                    )
        if path != ":memory:":
            os.chmod(path, 0o600)

    def create(
        self,
        *,
        event_id: str,
        category: str,
        suggestion: str,
        prompt_version: str,
        evidence: Sequence[str] = (),
        prompt_patch: str = "",
        expected_metric: str = "",
        validation_cases: Sequence[str] = (),
        risk_note: str = "",
    ) -> PromptSuggestion:
        suggestion_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO prompt_suggestions "
                "(suggestion_id, event_id, category, suggestion, prompt_version, "
                "evidence_json, prompt_patch, expected_metric, validation_cases_json, "
                "risk_note, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion_id,
                    event_id,
                    category,
                    suggestion,
                    prompt_version,
                    json.dumps(tuple(evidence), ensure_ascii=False),
                    prompt_patch,
                    expected_metric,
                    json.dumps(tuple(validation_cases), ensure_ascii=False),
                    risk_note,
                    FeedbackStatus.PENDING.value,
                ),
            )
            row = connection.execute(
                "SELECT suggestion_id, event_id, category, suggestion, prompt_version, "
                "evidence_json, prompt_patch, expected_metric, validation_cases_json, "
                "risk_note, status, created_at, reviewed_by, review_note, published_at "
                "FROM prompt_suggestions WHERE event_id = ? AND category = ?",
                (event_id, category),
            ).fetchone()
        return self._from_row(row)

    def get(self, suggestion_id: str) -> PromptSuggestion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT suggestion_id, event_id, category, suggestion, prompt_version, "
                "evidence_json, prompt_patch, expected_metric, validation_cases_json, "
                "risk_note, status, created_at, reviewed_by, review_note, published_at "
                "FROM prompt_suggestions WHERE suggestion_id = ?",
                (suggestion_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        *,
        status: FeedbackStatus | None = None,
        limit: int = 100,
    ) -> tuple[PromptSuggestion, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query = (
            "SELECT suggestion_id, event_id, category, suggestion, prompt_version, "
            "evidence_json, prompt_patch, expected_metric, validation_cases_json, "
            "risk_note, status, created_at, reviewed_by, review_note, published_at "
            "FROM prompt_suggestions"
        )
        parameters: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status.value,)
        query += " ORDER BY created_at DESC, suggestion_id LIMIT ?"
        parameters += (limit,)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def review(
        self,
        suggestion_id: str,
        *,
        approve: bool,
        reviewer: str,
        note: str = "",
    ) -> PromptSuggestion:
        if not reviewer.strip():
            raise ValueError("reviewer must not be empty")
        target_status = (
            FeedbackStatus.APPROVED if approve else FeedbackStatus.REJECTED
        )
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE prompt_suggestions SET status = ?, reviewed_by = ?, review_note = ? "
                "WHERE suggestion_id = ? AND status = ?",
                (
                    target_status.value,
                    reviewer,
                    note,
                    suggestion_id,
                    FeedbackStatus.PENDING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise FeedbackTransitionError(
                    "only pending suggestions can be reviewed"
                )
        suggestion = self.get(suggestion_id)
        if suggestion is None:
            raise FeedbackTransitionError("suggestion disappeared during review")
        return suggestion

    def mark_published(self, suggestion_id: str) -> PromptSuggestion:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE prompt_suggestions SET status = ?, published_at = ? "
                "WHERE suggestion_id = ? AND status = ?",
                (
                    FeedbackStatus.PUBLISHED.value,
                    datetime.now().astimezone().isoformat(),
                    suggestion_id,
                    FeedbackStatus.APPROVED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise FeedbackTransitionError(
                    "only approved suggestions can be marked published"
                )
        suggestion = self.get(suggestion_id)
        if suggestion is None:
            raise FeedbackTransitionError("suggestion disappeared during publish")
        return suggestion

    def weekly_report(self) -> WeeklyFeedbackReport:
        with self._connect() as connection:
            generated, reviewed_valid, published = connection.execute(
                "SELECT COUNT(*), "
                "COALESCE(SUM(CASE WHEN status IN (?, ?) THEN 1 ELSE 0 END), 0), "
                "COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) "
                "FROM prompt_suggestions "
                "WHERE created_at >= datetime('now', '-7 days')",
                (
                    FeedbackStatus.APPROVED.value,
                    FeedbackStatus.PUBLISHED.value,
                    FeedbackStatus.PUBLISHED.value,
                ),
            ).fetchone()
        return WeeklyFeedbackReport(
            generated=generated,
            reviewed_valid=reviewed_valid,
            published=published,
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _from_row(row: Sequence[object]) -> PromptSuggestion:
        return PromptSuggestion(
            suggestion_id=str(row[0]),
            event_id=str(row[1]),
            category=str(row[2]),
            suggestion=str(row[3]),
            prompt_version=str(row[4]),
            evidence=tuple(json.loads(str(row[5]))),
            prompt_patch=str(row[6]),
            expected_metric=str(row[7]),
            validation_cases=tuple(json.loads(str(row[8]))),
            risk_note=str(row[9]),
            status=FeedbackStatus(str(row[10])),
            created_at=str(row[11]),
            reviewed_by=str(row[12]) if row[12] is not None else None,
            review_note=str(row[13]) if row[13] is not None else None,
            published_at=str(row[14]) if row[14] is not None else None,
        )


@dataclass(frozen=True, slots=True)
class PromptFeedbackService:
    store: SQLiteFeedbackStore
    prompt_version: str = "edge-summary-v1"

    def observe(self, event: EdgeEvent, result: RagResult) -> tuple[PromptSuggestion, ...]:
        missing_fields = tuple(
            field_name
            for field_name in ("target_ip", "target_port", "error_code")
            if getattr(event, field_name) is None
        )
        if missing_fields:
            category = "missing_entities"
            fields = ", ".join(missing_fields)
            suggestion = f"Improve extraction coverage for explicitly logged entities: {fields}."
            evidence = (
                f"event_id={event.event_id}",
                f"missing_fields={fields}",
                "raw source log is not stored in feedback",
            )
            prompt_patch = (
                "When source logs explicitly contain target_ip, target_port, or "
                "error_code, copy the exact value into the matching field. If a value "
                "is absent or ambiguous, emit null; never infer or normalize beyond "
                "schema validation rules."
            )
            expected_metric = (
                "Increase entity extraction recall on labeled positive examples "
                "without increasing false entity emission on negative examples."
            )
            validation_cases = (
                "Positive: source explicitly contains target_ip=192.0.2.10, "
                "port=5432, ERR-503; expect all three exact values.",
                "Negative: source contains no IP, port, or ERR code; expect null "
                "for all three fields.",
            )
            risk_note = (
                "Broader extraction wording can increase false positives; measure "
                "precision as well as recall before approval."
            )
        elif not result.cases:
            category = "no_retrieved_cases"
            suggestion = "Improve summary specificity for queries with no retrieved cases."
            evidence = (
                f"event_id={event.event_id}",
                "retrieved_case_count=0",
                f"target_ip_present={event.target_ip is not None}",
                "raw source log is not stored in feedback",
            )
            prompt_patch = (
                "Preserve the concrete failing component, operation, symptom, and "
                "explicit error code in the summary. Remove repeated boilerplate, but "
                "do not invent causes or entities absent from source logs."
            )
            expected_metric = (
                "Improve top-5 relevant-case recall on the labeled no-match query "
                "set without increasing unsupported entity claims."
            )
            validation_cases = (
                "Positive: a timeout from payments connecting to the database; expect "
                "the service, operation, timeout symptom, and logged code preserved.",
                "Negative: a vague log with no component or code; expect unknown "
                "details instead of an invented cause.",
            )
            risk_note = (
                "Longer summaries may increase token use; verify compressed payload "
                "size and summary latency remain within target."
            )
        else:
            return ()

        return (
            self.store.create(
                event_id=event.event_id,
                category=category,
                suggestion=suggestion,
                prompt_version=self.prompt_version,
                evidence=evidence,
                prompt_patch=prompt_patch,
                expected_metric=expected_metric,
                validation_cases=validation_cases,
                risk_note=risk_note,
            ),
        )