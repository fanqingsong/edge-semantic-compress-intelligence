import unittest
from dataclasses import dataclass
from typing import Mapping, Sequence

from edge_semantic_compress_intelligence.filtering import LogRecord
from edge_semantic_compress_intelligence.summarization import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)


def record(
    message: str,
    *,
    service: str = "payments",
    target_ip: str | None = None,
    target_port: int | str | None = None,
    error_code: str | None = None,
) -> LogRecord:
    return LogRecord(
        timestamp="2026-11-01T10:30:00Z",
        service=service,
        message=message,
        target_ip=target_ip,
        target_port=target_port,
        error_code=error_code,
    )


@dataclass(frozen=True)
class FixedSummarizer:
    output: Mapping[str, object]

    def summarize(self, records: Sequence[LogRecord]) -> Mapping[str, object]:
        return self.output


class SummaryPipelineTests(unittest.TestCase):
    def test_mock_summarizer_produces_a_valid_event(self) -> None:
        event = SummaryPipeline(DeterministicMockSummarizer()).summarize(
            [record("Database timeout"), record("Connection refused")]
        )

        self.assertEqual(event.service, "payments")
        self.assertEqual(event.summary, "2 error log entries for payments")
        self.assertIsNone(event.target_ip)
        self.assertIsNone(event.error_code)

    def test_missing_entities_are_recovered_from_original_records(self) -> None:
        event = SummaryPipeline(DeterministicMockSummarizer()).summarize(
            [record("upstream 192.0.2.42 port 8443 failed with ERR-503")]
        )

        self.assertEqual(event.target_ip, "192.0.2.42")
        self.assertEqual(event.target_port, 8443)
        self.assertEqual(event.error_code, "ERR-503")

    def test_entities_not_present_in_source_logs_are_replaced(self) -> None:
        fixed_summarizer = FixedSummarizer(
            {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "schema_version": "1.0",
                "timestamp": "2026-11-01T10:30:00Z",
                "service": "payments",
                "target_ip": "203.0.113.99",
                "target_port": 9999,
                "error_code": "ERR-999",
                "summary": "Database timeout",
            }
        )

        event = SummaryPipeline(fixed_summarizer).summarize(
            [record("upstream 192.0.2.42 target_port=8443 failed with ERR-503")]
        )

        self.assertEqual(event.target_ip, "192.0.2.42")
        self.assertEqual(event.target_port, 8443)
        self.assertEqual(event.error_code, "ERR-503")

    def test_unlabeled_numbers_are_not_treated_as_ports(self) -> None:
        event = SummaryPipeline(DeterministicMockSummarizer()).summarize(
            [record("request 5432 failed with ERR-503")]
        )

        self.assertIsNone(event.target_port)

    def test_invalid_entity_candidates_are_not_emitted(self) -> None:
        event = SummaryPipeline(DeterministicMockSummarizer()).summarize(
            [record("upstream 999.999.999.999 failed with ERR-503")]
        )

        self.assertIsNone(event.target_ip)
        self.assertEqual(event.error_code, "ERR-503")

    def test_mock_rejects_mixed_service_batches(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one service"):
            SummaryPipeline(DeterministicMockSummarizer()).summarize(
                [record("Database timeout"), record("Cache timeout", service="cache")]
            )


if __name__ == "__main__":
    unittest.main()