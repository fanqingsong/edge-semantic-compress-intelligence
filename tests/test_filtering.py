import json
import unittest

from edge.filtering import (
    DropReason,
    FilterConfig,
    RuleFilter,
)


def log_line(
    message: str,
    *,
    status_code: str | int | None = 500,
    timestamp: str = "2026-11-01T10:30:00Z",
    service: str = "payments",
) -> str:
    return json.dumps(
        {
            "timestamp": timestamp,
            "service": service,
            "message": message,
            "status_code": status_code,
        }
    )


class RuleFilterTests(unittest.TestCase):
    def test_invalid_format_is_counted_and_dropped(self) -> None:
        report = RuleFilter().process_batch(["not-json", "[]"])

        self.assertEqual(report.accepted, ())
        self.assertEqual(report.dropped[DropReason.INVALID_FORMAT], 2)

    def test_success_status_is_filtered(self) -> None:
        report = RuleFilter().process_batch(
            [
                log_line("request completed", status_code=200),
                log_line("request completed", status_code="OK"),
            ]
        )

        self.assertEqual(report.accepted, ())
        self.assertEqual(report.dropped[DropReason.SUCCESS_STATUS], 2)

    def test_blacklist_is_case_insensitive(self) -> None:
        report = RuleFilter().process_batch([log_line("Heartbeat check")])

        self.assertEqual(report.accepted, ())
        self.assertEqual(report.dropped[DropReason.BLACKLISTED_KEYWORD], 1)

    def test_repeated_logs_keep_first_and_last_above_threshold(self) -> None:
        rule_filter = RuleFilter(FilterConfig(repeat_threshold=2))
        report = rule_filter.process_batch(
            [
                log_line("database timeout", timestamp=f"2026-11-01T10:30:0{i}Z")
                for i in range(4)
            ]
        )

        self.assertEqual(len(report.accepted), 2)
        self.assertEqual(report.accepted[0].timestamp, "2026-11-01T10:30:00Z")
        self.assertEqual(report.accepted[-1].timestamp, "2026-11-01T10:30:03Z")
        self.assertEqual(report.dropped[DropReason.FREQUENCY_SUPPRESSED], 2)

    def test_repeats_at_threshold_are_not_suppressed(self) -> None:
        rule_filter = RuleFilter(FilterConfig(repeat_threshold=3))
        report = rule_filter.process_batch([log_line("database timeout")] * 3)

        self.assertEqual(len(report.accepted), 3)
        self.assertEqual(report.dropped.get(DropReason.FREQUENCY_SUPPRESSED, 0), 0)

    def test_different_services_have_independent_repeat_counts(self) -> None:
        rule_filter = RuleFilter(FilterConfig(repeat_threshold=2))
        report = rule_filter.process_batch(
            [
                log_line("database timeout", service="payments"),
                log_line("database timeout", service="inventory"),
            ]
        )

        self.assertEqual(len(report.accepted), 2)


if __name__ == "__main__":
    unittest.main()