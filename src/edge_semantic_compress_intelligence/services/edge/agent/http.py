from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type

from edge_semantic_compress_intelligence.services.edge.agent.runtime import EdgeRuntime
from edge_semantic_compress_intelligence.services.edge.transport.outbox import OutboxFullError


@dataclass(frozen=True, slots=True)
class EdgeHttpConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    max_body_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be in range 0..65535")
        if self.max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")


def create_edge_server(
    runtime: EdgeRuntime,
    config: EdgeHttpConfig | None = None,
) -> ThreadingHTTPServer:
    selected_config = config or EdgeHttpConfig()

    class Handler(BaseHTTPRequestHandler):
        server_version = "EdgeLogAgent/0.1"

        def do_GET(self) -> None:
            if self.path != "/healthz":
                self._send_json(404, {"error": "not_found"})
                return
            self._send_json(200, {"status": "ok"})

        def do_POST(self) -> None:
            if self.path != "/v1/logs":
                self._send_json(404, {"error": "not_found"})
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
                self._send_json(400, {"error": "empty_batch"})
                return
            if content_length > selected_config.max_body_bytes:
                self._send_json(413, {"error": "batch_too_large"})
                return

            try:
                body = self.rfile.read(content_length).decode("utf-8")
            except UnicodeDecodeError:
                self._send_json(400, {"error": "body_must_be_utf8"})
                return

            lines = [line for line in body.splitlines() if line.strip()]
            if not lines:
                self._send_json(400, {"error": "empty_batch"})
                return

            try:
                report = runtime.process_batch(lines)
            except OutboxFullError:
                self._send_json(507, {"error": "outbox_full"})
                return
            except Exception:
                self._send_json(503, {"error": "batch_processing_failed"})
                return

            self._send_json(
                202 if report.pending else 200,
                {
                    "event_count": len(report.events),
                    "published": report.published,
                    "pending": report.pending,
                    "dropped": {
                        reason.value: count
                        for reason, count in report.dropped_by_reason.items()
                    },
                },
            )

        def log_message(self, format_string: str, *args: object) -> None:
            return None

        def _send_json(self, status: int, value: dict[str, object]) -> None:
            payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer(
        (selected_config.host, selected_config.port),
        Handler,
    )