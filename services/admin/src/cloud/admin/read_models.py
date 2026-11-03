from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class StoreUnavailable(RuntimeError):
    """Raised when a read-only store is missing or cannot be queried."""


class AnalysisReader:
    def __init__(self, path: str) -> None:
        self.path = path

    def count(self) -> int:
        rows = self._rows("SELECT COUNT(*) FROM analyses", ())
        return int(rows[0][0])

    def list_page(self, *, limit: int, before: str | None) -> dict[str, Any]:
        created_at, event_id = _cursor(before)
        sql = (
            "SELECT event_id, result_json, created_at FROM analyses "
        )
        params: list[object] = []
        if created_at is not None and event_id is not None:
            sql += "WHERE created_at < ? OR (created_at = ? AND event_id < ?) "
            params.extend((created_at, created_at, event_id))
        sql += "ORDER BY created_at DESC, event_id DESC LIMIT ?"
        params.append(limit + 1)
        rows = self._rows(sql, tuple(params))
        extra = len(rows) > limit
        visible = rows[:limit]
        items = [
            _list_item(row_event_id, result_json, row_created_at)
            for row_event_id, result_json, row_created_at in visible
        ]
        next_before = None
        if extra and items:
            last = visible[-1]
            next_before = f"{last[2]}\t{last[0]}"
        return {"items": items, "next_before": next_before}

    def get(self, event_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "SELECT event_id, result_json, created_at FROM analyses WHERE event_id = ?",
            (event_id,),
        )
        if not rows:
            return None
        row_event_id, result_json, created_at = rows[0]
        return _detail(row_event_id, result_json, created_at)

    def _rows(self, sql: str, params: tuple[object, ...]) -> list[tuple[Any, ...]]:
        connection = _readonly(self.path)
        if connection is None:
            raise StoreUnavailable(self.path)
        try:
            try:
                return list(connection.execute(sql, params))
            except sqlite3.Error as error:
                raise StoreUnavailable(self.path) from error
        finally:
            connection.close()


class ProcessedReader:
    def __init__(self, path: str) -> None:
        self.path = path

    def count(self) -> int:
        connection = _readonly(self.path)
        if connection is None:
            raise StoreUnavailable(self.path)
        try:
            try:
                row = connection.execute("SELECT COUNT(*) FROM processed_events").fetchone()
            except sqlite3.Error as error:
                raise StoreUnavailable(self.path) from error
        finally:
            connection.close()
        return int(row[0])


def fetch_edge_status(url: str, timeout: float = 2.0) -> dict[str, object]:
    unavailable = {"reachable": False, "pending_count": None, "pending_bytes": None}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "reachable": True,
            "pending_count": int(payload["pending_count"]),
            "pending_bytes": int(payload["pending_bytes"]),
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return unavailable


def _readonly(path: str) -> sqlite3.Connection | None:
    database = Path(path)
    if not database.is_file():
        return None
    uri = database.resolve().as_posix().replace("?", "%3F")
    connection = sqlite3.connect(f"file:{uri}?mode=ro", uri=True, timeout=5.0)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _cursor(before: str | None) -> tuple[str | None, str | None]:
    if before is None:
        return None, None
    created_at, separator, event_id = before.partition("\t")
    if not separator or not created_at or not event_id:
        raise ValueError("invalid_before")
    return created_at, event_id


def _payload(result_json: str) -> dict[str, Any]:
    try:
        value = json.loads(result_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        return []
    cases: list[dict[str, Any]] = []
    for case in raw_cases:
        if not isinstance(case, dict):
            continue
        cases.append(
            {
                "case_id": case.get("case_id"),
                "summary": case.get("summary"),
                "resolution": case.get("resolution"),
                "source": case.get("source"),
                "target_ip": case.get("target_ip"),
                "score": case.get("score"),
            }
        )
    return cases


def _answer(payload: dict[str, Any]) -> dict[str, Any]:
    answer = payload.get("answer")
    return answer if isinstance(answer, dict) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _list_item(event_id: str, result_json: str, created_at: str) -> dict[str, Any]:
    payload = _payload(result_json)
    answer = _answer(payload)
    root_cause = answer.get("root_cause")
    text = root_cause if isinstance(root_cause, str) else ""
    return {
        "event_id": event_id,
        "created_at": created_at,
        "root_cause": text[:160],
        "case_count": len(_cases(payload)),
    }


def _detail(event_id: str, result_json: str, created_at: str) -> dict[str, Any]:
    payload = _payload(result_json)
    answer = _answer(payload)
    root_cause = answer.get("root_cause")
    uncertainty = answer.get("uncertainty")
    return {
        "event_id": event_id,
        "created_at": created_at,
        "root_cause": root_cause if isinstance(root_cause, str) else "",
        "evidence": _strings(answer.get("evidence")),
        "recommendations": _strings(answer.get("recommendations")),
        "uncertainty": uncertainty if isinstance(uncertainty, str) else "",
        "cases": _cases(payload),
    }
