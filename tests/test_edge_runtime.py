import json
import unittest
from dataclasses import dataclass, field

from shared.contract import EdgeEvent
from edge.agent.runtime import EdgeRuntime
from edge.filtering import (
    DropReason,
    FilterConfig,
    RuleFilter,
)
from edge.summarization import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)
from edge.transport import FlushReport


@dataclass
class RecordingTransport:
    published_events: list[EdgeEvent] = field(default_factory=list)
    report: FlushReport = FlushReport(published=1, pending=0)

    def submit(self, event: EdgeEvent) -> FlushReport:
        self.published_events.append(event)
        return self.report


def log_line(service: str, message: str, status: int = 500) -> str:
    return json.dumps(
        {
            "timestamp": "2026-11-01T10:30:00Z",
            "service": service,
            "message": message,
            "status_code": status,
        }
    )


class EdgeRuntimeTests(unittest.TestCase):
    def test_filters_summarizes_and_submits_by_service(self) -> None:
        transport = RecordingTransport()
        runtime = EdgeRuntime(
            RuleFilter(FilterConfig(repeat_threshold=5)),
            SummaryPipeline(DeterministicMockSummarizer()),
            transport,
        )

        report = runtime.process_batch(
            [
                log_line("payments", "database timeout 192.0.2.10 port=5432 ERR-42"),
                log_line("payments", "health check heartbeat"),
                log_line("cache", "cache connection refused"),
            ]
        )

        self.assertEqual(len(report.events), 2)
        self.assertEqual(len(transport.published_events), 2)
        self.assertEqual(report.published, 2)
        self.assertEqual(report.pending, 0)
        payments = next(event for event in report.events if event.service == "payments")
        self.assertEqual(payments.target_ip, "192.0.2.10")
        self.assertEqual(payments.target_port, 5432)
        self.assertEqual(payments.error_code, "ERR-42")
        self.assertEqual(report.dropped_by_reason[DropReason.BLACKLISTED_KEYWORD], 1)

    def test_offline_outbox_count_is_reported(self) -> None:
        transport = RecordingTransport(report=FlushReport(published=0, pending=3))
        runtime = EdgeRuntime(
            RuleFilter(),
            SummaryPipeline(DeterministicMockSummarizer()),
            transport,
        )

        report = runtime.process_batch([log_line("payments", "database timeout")])

        self.assertEqual(report.published, 0)
        self.assertEqual(report.pending, 3)
        self.assertEqual(len(report.events), 1)

    def test_fully_filtered_batch_does_not_submit_events(self) -> None:
        transport = RecordingTransport()
        runtime = EdgeRuntime(
            RuleFilter(),
            SummaryPipeline(DeterministicMockSummarizer()),
            transport,
        )

        report = runtime.process_batch([log_line("payments", "health check")])

        self.assertEqual(report.events, ())
        self.assertEqual(transport.published_events, [])
        self.assertEqual(report.published, 0)


if __name__ == "__main__":
    unittest.main()