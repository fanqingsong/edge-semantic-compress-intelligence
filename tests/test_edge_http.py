from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.edge.http import EdgeHttpConfig, create_edge_server
from edge_semantic_compress_intelligence.services.edge.runtime import EdgeRuntime
from edge_semantic_compress_intelligence.services.edge.filtering import RuleFilter
from edge_semantic_compress_intelligence.services.edge.summarization import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)
from edge_semantic_compress_intelligence.services.edge.transport import FlushReport


@dataclass
class RecordingTransport:
    events: list[EdgeEvent] = field(default_factory=list)
    pending: int = 0

    def submit(self, event: EdgeEvent) -> FlushReport:
        self.events.append(event)
        return FlushReport(published=1 - self.pending, pending=self.pending)


class EdgeHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RecordingTransport()
        runtime = EdgeRuntime(
            RuleFilter(),
            SummaryPipeline(DeterministicMockSummarizer()),
            self.transport,
        )
        self.server = create_edge_server(
            runtime,
            EdgeHttpConfig(host="127.0.0.1", port=0, max_body_bytes=512),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_accepts_jsonl_and_returns_filter_metrics(self) -> None:
        body = "\n".join(
            (
                json.dumps(
                    {
                        "timestamp": "2026-11-01T10:30:00Z",
                        "service": "payments",
                        "status_code": 500,
                        "message": "database timeout 192.0.2.10 port=5432 ERR-42",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-11-01T10:30:01Z",
                        "service": "payments",
                        "status_code": 200,
                        "message": "request completed",
                    }
                ),
            )
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/v1/logs",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["published"], 1)
        self.assertEqual(result["dropped"]["success_status"], 1)
        self.assertEqual(self.transport.events[0].target_ip, "192.0.2.10")
        self.assertEqual(self.transport.events[0].target_port, 5432)

    def test_reports_accepted_when_transport_has_pending_outbox(self) -> None:
        self.transport.pending = 2
        body = json.dumps(
            {
                "timestamp": "2026-11-01T10:30:00Z",
                "service": "payments",
                "message": "database timeout",
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/v1/logs", data=body, method="POST"
        )

        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())

        self.assertEqual(response.status, 202)
        self.assertEqual(result["pending"], 2)

    def test_rejects_oversized_batches(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/v1/logs",
            data=b"x" * 513,
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as error:
            response = urllib.request.urlopen(request, timeout=2)
            response.close()

        error.exception.close()
        self.assertEqual(error.exception.code, 413)
        self.assertEqual(self.transport.events, [])

    def test_health_endpoint_is_available(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=2) as response:
            result = json.loads(response.read())

        self.assertEqual(response.status, 200)
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()