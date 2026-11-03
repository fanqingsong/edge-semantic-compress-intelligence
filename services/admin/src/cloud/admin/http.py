from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cloud.admin.formdata import UploadFormatError, parse_file_upload
from cloud.admin.jobs import IngestWorker, JobStore
from cloud.admin.read_models import AnalysisReader, ProcessedReader, StoreUnavailable
from cloud.knowledge.main import SUPPORTED_EXTENSIONS


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/assets/app.css": "app.css",
    "/assets/app.js": "app.js",
}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
EVENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
JOB_ID = re.compile(r"^[a-f0-9]{32}$")
MULTIPART_OVERHEAD = 16 * 1024


@dataclass(frozen=True, slots=True)
class AdminConfig:
    token: str
    host: str = "127.0.0.1"
    port: int = 8088
    max_upload_bytes: int = 20 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise ValueError("token must not be empty")
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be in range 0..65535")
        if self.max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")


@dataclass(frozen=True, slots=True)
class AdminServices:
    analyses: AnalysisReader
    processed: ProcessedReader
    cases: object
    jobs: JobStore
    uploads: IngestWorker
    edge_status: Callable[[], dict[str, object]]


def create_admin_server(
    services: AdminServices,
    config: AdminConfig,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "CloudAdmin/0.1"

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path in STATIC_FILES:
                self._send_static(STATIC_FILES[path])
                return
            if path == "/healthz":
                self._send_json(200, {"status": "ok"})
                return
            if not _authorized(self.headers.get("Authorization"), config.token):
                self._send_json(401, {"error": "unauthorized"})
                return
            try:
                if path == "/api/status":
                    self._send_json(200, _status(services))
                    return
                if path == "/api/analyses":
                    self._send_analyses()
                    return
                if path == "/api/cases":
                    self._send_cases()
                    return
                analysis_id = _suffix(path, "/api/analyses/")
                if analysis_id is not None:
                    self._send_analysis(analysis_id)
                    return
                job_id = _suffix(path, "/api/knowledge/jobs/")
                if job_id is not None:
                    self._send_job(job_id)
                    return
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            except StoreUnavailable:
                self._send_json(503, {"error": "store_unavailable"})
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path != "/api/knowledge/documents":
                self._send_json(404, {"error": "not_found"})
                return
            if not _authorized(self.headers.get("Authorization"), config.token):
                self._send_json(401, {"error": "unauthorized"})
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_json(411, {"error": "content_length_required"})
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                self._send_json(400, {"error": "invalid_content_length"})
                return
            if content_length < 1:
                self._send_json(400, {"error": "empty_upload"})
                return
            if content_length > config.max_upload_bytes + MULTIPART_OVERHEAD:
                self._send_json(413, {"error": "upload_too_large"})
                return
            body = self.rfile.read(content_length)
            try:
                filename, content = parse_file_upload(
                    self.headers.get("Content-Type", ""),
                    body,
                )
                filename = _filename(filename)
            except (UploadFormatError, ValueError) as error:
                code = str(error)
                if code not in {"invalid_filename", "unsupported_document_type"}:
                    code = "invalid_upload"
                self._send_json(400, {"error": code})
                return
            if not content:
                self._send_json(400, {"error": "empty_document"})
                return
            if len(content) > config.max_upload_bytes:
                self._send_json(413, {"error": "upload_too_large"})
                return
            try:
                record = services.uploads.submit(filename, content)
            except OSError:
                self._send_json(500, {"error": "upload_failed"})
                return
            self._send_json(202, record)

        def log_message(self, format_string: str, *args: object) -> None:
            return None

        def _send_analyses(self) -> None:
            query = parse_qs(urlsplit(self.path).query)
            limit = _limit(query, default=50, maximum=100)
            before_values = query.get("before")
            before = before_values[0] if before_values else None
            self._send_json(200, services.analyses.list_page(limit=limit, before=before))

        def _send_analysis(self, event_id: str) -> None:
            if EVENT_ID.fullmatch(event_id) is None:
                self._send_json(404, {"error": "not_found"})
                return
            detail = services.analyses.get(event_id)
            if detail is None:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(200, detail)

        def _send_cases(self) -> None:
            query = parse_qs(urlsplit(self.path).query)
            limit = _limit(query, default=50, maximum=200)
            target_ip = _optional(query, "target_ip")
            source = _optional(query, "source")
            try:
                cases = services.cases.list_cases(
                    target_ip=target_ip,
                    source=source,
                    limit=limit,
                )
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            except Exception:
                self._send_json(503, {"error": "case_store_unavailable"})
                return
            self._send_json(
                200,
                {
                    "items": [
                        {
                            "case_id": case.case_id,
                            "summary": case.summary,
                            "resolution": case.resolution,
                            "source": case.source,
                            "target_ip": case.target_ip,
                        }
                        for case in cases
                    ]
                },
            )

        def _send_job(self, job_id: str) -> None:
            if JOB_ID.fullmatch(job_id) is None:
                self._send_json(404, {"error": "not_found"})
                return
            record = services.jobs.get(job_id)
            if record is None:
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(200, record)

        def _send_static(self, name: str) -> None:
            file_path = STATIC_DIR / name
            if not file_path.is_file():
                self._send_json(404, {"error": "not_found"})
                return
            payload = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES[file_path.suffix])
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: int, value: dict[str, object]) -> None:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer((config.host, config.port), Handler)


def _status(services: AdminServices) -> dict[str, object]:
    try:
        edge = services.edge_status()
    except Exception:
        edge = {"reachable": False, "pending_count": None, "pending_bytes": None}
    return {
        "edge": edge,
        "processed_count": _count(services.processed.count),
        "analysis_count": _count(services.analyses.count),
        "case_count": _case_count(services.cases),
        "latest_job": services.jobs.latest(),
    }


def _count(method: Callable[[], int]) -> int | None:
    try:
        return method()
    except StoreUnavailable:
        return None


def _case_count(cases: object) -> int | None:
    try:
        return int(cases.count_cases())
    except Exception:
        return None


def _authorized(header: str | None, token: str) -> bool:
    if not header:
        return False
    scheme, separator, provided = header.partition(" ")
    if scheme != "Bearer" or not separator or not provided:
        return False
    actual = hashlib.sha256(provided.encode("utf-8")).digest()
    expected = hashlib.sha256(token.encode("utf-8")).digest()
    return hmac.compare_digest(actual, expected)


def _suffix(path: str, prefix: str) -> str | None:
    if not path.startswith(prefix):
        return None
    value = path[len(prefix):]
    if not value or "/" in value:
        return None
    return value


def _limit(query: dict[str, list[str]], *, default: int, maximum: int) -> int:
    raw = query.get("limit", [str(default)])[0]
    try:
        limit = int(raw)
    except ValueError as error:
        raise ValueError("invalid_limit") from error
    if limit < 1 or limit > maximum:
        raise ValueError("invalid_limit")
    return limit


def _optional(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    value = values[0]
    if not value.strip():
        raise ValueError(f"invalid_{name}")
    return value


def _filename(raw_name: str) -> str:
    if not raw_name or "\x00" in raw_name:
        raise ValueError("invalid_filename")
    name = Path(raw_name).name
    if name in {"", ".", ".."} or name != raw_name or len(name) > 200:
        raise ValueError("invalid_filename")
    if Path(name).suffix.casefold() not in SUPPORTED_EXTENSIONS:
        raise ValueError("unsupported_document_type")
    return name
