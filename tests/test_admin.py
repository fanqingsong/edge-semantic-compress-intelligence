from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from cloud.admin.formdata import parse_file_upload
from cloud.admin.http import (
    AdminConfig,
    AdminServices,
    create_admin_server,
)
from cloud.admin.jobs import IngestWorker, JobStore
from cloud.admin.main import require_token
from cloud.admin.read_models import AnalysisReader, ProcessedReader
from cloud.knowledge.ingest import IngestReport, RawDocumentKnowledgeParser
from cloud.retrieval.hybrid import ListedCase


DOCUMENT = b'{"case_id":"CASE-9","summary":"Disk full","resolution":"Free space","target_ip":"192.0.2.10"}\n'
SECRET = "raw-log-secret-do-not-leak"


class FakeCases:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []
        self.fail = False

    def list_cases(
        self,
        *,
        target_ip: str | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> tuple[ListedCase, ...]:
        self.calls.append((target_ip, source, limit))
        if self.fail:
            raise RuntimeError("milvus down")
        return (
            ListedCase(
                case_id="CASE-9",
                summary="Disk full",
                resolution="Free space",
                source="case.jsonl",
                target_ip=target_ip,
            ),
        )

    def count_cases(self) -> int:
        if self.fail:
            raise RuntimeError("milvus down")
        return 3


class GateIngestor:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.sources: list[str] = []
        self.lock = threading.Lock()

    def ingest_cases(self, source: str, cases: object) -> IngestReport:
        with self.lock:
            self.sources.append(source)
            started = len(self.sources)
        if started == 1:
            self.started.set()
            if not self.release.wait(3):
                raise TimeoutError("ingest was not released")
        return IngestReport(source=source, upserted=len(tuple(cases)), removed_stale=1)


class FailingIngestor:
    def ingest_cases(self, source: str, cases: object) -> IngestReport:
        raise RuntimeError("embed failed")


class AdminHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.analysis_path = root / "analyses.sqlite3"
        self.processed_path = root / "processed.sqlite3"
        self._seed_databases()
        self.cases = FakeCases()
        self.ingestor = GateIngestor()
        self.jobs = JobStore(str(root / "jobs.sqlite3"))
        self.server = create_admin_server(
            AdminServices(
                analyses=AnalysisReader(str(self.analysis_path)),
                processed=ProcessedReader(str(self.processed_path)),
                cases=self.cases,
                jobs=self.jobs,
                uploads=IngestWorker(
                    self.jobs,
                    RawDocumentKnowledgeParser(),
                    self.ingestor,
                    str(root / "uploads"),
                ),
                edge_status=lambda: {
                    "reachable": False,
                    "pending_count": None,
                    "pending_bytes": None,
                },
            ),
            AdminConfig(token="test-token", host="127.0.0.1", port=0, max_upload_bytes=1024),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.ingestor.release.set()
        deadline = time.time() + 2
        while time.time() < deadline:
            record = self.jobs.latest()
            if record is None or record["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def test_health_and_page_do_not_require_a_token(self) -> None:
        with urllib.request.urlopen(self.base_url + "/healthz", timeout=2) as response:
            self.assertEqual(json.loads(response.read())["status"], "ok")
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode("utf-8")
        self.assertIn("Operator console", page)

    def test_api_requires_the_admin_token(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base_url + "/api/status", timeout=2).close()
        self.assertEqual(error.exception.code, 401)

        request = urllib.request.Request(
            self.base_url + "/api/status",
            headers={"Authorization": "Bearer wrong-token"},
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2).close()
        self.assertEqual(error.exception.code, 401)

    def test_status_marks_missing_edge_and_counts_local_rows(self) -> None:
        status = self._json("GET", "/api/status")

        self.assertFalse(status["edge"]["reachable"])
        self.assertIsNone(status["edge"]["pending_count"])
        self.assertEqual(status["processed_count"], 2)
        self.assertEqual(status["analysis_count"], 2)
        self.assertEqual(status["case_count"], 3)
        self.assertIsNone(status["latest_job"])

    def test_analysis_pages_hide_raw_logs(self) -> None:
        page = self._json("GET", "/api/analyses?limit=1")
        raw = json.dumps(page)

        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["event_id"], "event-b")
        self.assertEqual(len(page["items"][0]["root_cause"]), 160)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn("raw_log", raw)
        self.assertTrue(page["next_before"])

        older = self._json(
            "GET",
            "/api/analyses?limit=1&before=" + urllib.request.quote(page["next_before"]),
        )
        self.assertEqual(older["items"][0]["event_id"], "event-a")
        self.assertIsNone(older["next_before"])

        detail = self._json("GET", "/api/analyses/event-a")
        detail_raw = json.dumps(detail)
        self.assertEqual(detail["evidence"], ["pool saturation"])
        self.assertEqual(detail["cases"][0]["case_id"], "CASE-1")
        self.assertNotIn(SECRET, detail_raw)
        self.assertNotIn("raw_log", detail_raw)
        self.assertGreater(len(detail["root_cause"]), 160)

    def test_case_list_uses_filters_and_omits_vectors(self) -> None:
        page = self._json("GET", "/api/cases?target_ip=192.0.2.10&source=case.jsonl&limit=10")

        self.assertEqual(self.cases.calls, [("192.0.2.10", "case.jsonl", 10)])
        self.assertEqual(set(page["items"][0]), {"case_id", "summary", "resolution", "source", "target_ip"})
        self.assertNotIn("embedding", json.dumps(page))

    def test_case_store_failure_does_not_hide_the_status_page(self) -> None:
        self.cases.fail = True

        status = self._json("GET", "/api/status")
        self.assertIsNone(status["case_count"])
        self.assertEqual(status["analysis_count"], 2)

        with self.assertRaises(urllib.error.HTTPError) as error:
            self._open("/api/cases")
        self.assertEqual(error.exception.code, 503)

    def test_upload_is_limited_to_one_supported_document(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as error:
            self._open(
                "/api/knowledge/documents",
                method="POST",
                body=self._multipart("notes.exe", b"not a document"),
                content_type="multipart/form-data; boundary=----admin",
            )
        self.assertEqual(error.exception.code, 400)
        self.assertIsNone(self.jobs.latest())

        oversized = b"x" * 1025
        with self.assertRaises(urllib.error.HTTPError) as error:
            self._open(
                "/api/knowledge/documents",
                method="POST",
                body=self._multipart("case.jsonl", oversized),
                content_type="multipart/form-data; boundary=----admin",
            )
        self.assertEqual(error.exception.code, 413)
        self.assertIsNone(self.jobs.latest())

    def test_uploads_import_one_at_a_time_under_the_original_filename(self) -> None:
        first = self._json(
            "POST",
            "/api/knowledge/documents",
            body=self._multipart("case.jsonl", DOCUMENT),
            content_type="multipart/form-data; boundary=----admin",
        )
        self.assertTrue(self.ingestor.started.wait(2))
        second = self._json(
            "POST",
            "/api/knowledge/documents",
            body=self._multipart("other.jsonl", DOCUMENT),
            content_type="multipart/form-data; boundary=----admin",
        )
        queued = self._json("GET", "/api/knowledge/jobs/" + second["id"])
        self.assertEqual(queued["status"], "queued")
        self.ingestor.release.set()

        finished = self._wait(first["id"], "succeeded")
        self.assertEqual(finished["upserted"], 1)
        self.assertEqual(finished["removed_stale"], 1)
        self.assertEqual(self._wait(second["id"], "succeeded")["filename"], "other.jsonl")
        self.assertEqual(self.ingestor.sources, ["case.jsonl", "other.jsonl"])

    def test_failed_import_keeps_the_error(self) -> None:
        self.ingestor.release.set()
        root = Path(self.temporary.name) / "failed"
        root.mkdir()
        jobs = JobStore(str(root / "jobs.sqlite3"))
        server = create_admin_server(
            AdminServices(
                analyses=AnalysisReader(str(self.analysis_path)),
                processed=ProcessedReader(str(self.processed_path)),
                cases=self.cases,
                jobs=jobs,
                uploads=IngestWorker(
                    jobs,
                    RawDocumentKnowledgeParser(),
                    FailingIngestor(),
                    str(root / "uploads"),
                ),
                edge_status=lambda: {"reachable": True, "pending_count": 0, "pending_bytes": 0},
            ),
            AdminConfig(token="test-token", host="127.0.0.1", port=0),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            created = self._json(
                "POST",
                "/api/knowledge/documents",
                body=self._multipart("case.jsonl", DOCUMENT),
                content_type="multipart/form-data; boundary=----admin",
                base_url=base_url,
            )
            failed = self._wait(created["id"], "failed", base_url=base_url)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertIn("embed failed", failed["error"])

    def test_token_is_required_to_start(self) -> None:
        with self.assertRaises(SystemExit):
            require_token("  ")

    def test_multipart_preserves_file_bytes(self) -> None:
        body = self._multipart("case.jsonl", b"line\r\n")
        filename, content = parse_file_upload(
            "multipart/form-data; boundary=----admin",
            body,
        )
        self.assertEqual(filename, "case.jsonl")
        self.assertEqual(content, b"line\r\n")

    def _seed_databases(self) -> None:
        root_cause = "x" * 180
        with sqlite3.connect(self.analysis_path) as connection:
            connection.execute(
                "CREATE TABLE analyses ("
                "event_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            for event_id in ("event-a", "event-b"):
                connection.execute(
                    "INSERT INTO analyses (event_id, result_json, created_at) VALUES (?, ?, ?)",
                    (
                        event_id,
                        json.dumps(
                            {
                                "event_id": event_id,
                                "raw_log": SECRET,
                                "cases": [
                                    {
                                        "case_id": "CASE-1",
                                        "summary": "Disk full",
                                        "resolution": "Free space",
                                        "source": "case.jsonl",
                                        "target_ip": "192.0.2.10",
                                        "score": 0.2,
                                        "embedding": [0.1],
                                    }
                                ],
                                "answer": {
                                    "root_cause": root_cause,
                                    "evidence": ["pool saturation"],
                                    "recommendations": ["raise the pool"],
                                    "uncertainty": "low",
                                },
                            }
                        ),
                        "2026-11-03 08:00:00" if event_id == "event-a" else "2026-11-03 09:00:00",
                    ),
                )
        with sqlite3.connect(self.processed_path) as connection:
            connection.execute(
                "CREATE TABLE processed_events ("
                "event_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, processed_at TEXT NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO processed_events (event_id, payload_hash, processed_at) VALUES (?, ?, ?)",
                (("event-a", "hash-a", "2026-11-03 08:00:00"), ("event-b", "hash-b", "2026-11-03 09:00:00")),
            )

    def _multipart(self, filename: str, content: bytes) -> bytes:
        return (
            b"------admin\r\n"
            b'Content-Disposition: form-data; name="file"; filename="'
            + filename.encode()
            + b'"\r\n\r\n'
            + content
            + b"\r\n------admin--\r\n"
        )

    def _open(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        base_url: str | None = None,
        token: str = "test-token",
    ) -> urllib.request.addinfourl:
        headers = {"Authorization": "Bearer " + token}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            (base_url or self.base_url) + path,
            data=body,
            headers=headers,
            method=method,
        )
        return urllib.request.urlopen(request, timeout=2)

    def _json(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        with self._open(path, method=method, **kwargs) as response:
            self.assertIn(response.status, {200, 202})
            return json.loads(response.read())

    def _wait(self, job_id: str, status: str, base_url: str | None = None) -> dict[str, object]:
        for _ in range(50):
            record = self._json("GET", "/api/knowledge/jobs/" + job_id, base_url=base_url)
            if record["status"] == status:
                return record
            time.sleep(0.02)
        self.fail(f"job {job_id} did not reach {status}")
        return {}


if __name__ == "__main__":
    unittest.main()
