import sqlite3
import tempfile
import unittest
from pathlib import Path

from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.cloud.feedback import (
    FeedbackStatus,
    FeedbackTransitionError,
    PromptFeedbackService,
    SQLiteFeedbackStore,
)
from edge_semantic_compress_intelligence.services.cloud.rag import (
    AnalysisAnswer,
    RagResult,
    RetrievedCase,
)


def make_event(
    *,
    target_ip: str | None = None,
    target_port: int | None = None,
    error_code: str | None = None,
) -> EdgeEvent:
    return EdgeEvent(
        event_id="550e8400-e29b-41d4-a716-446655440000",
        timestamp="2026-11-01T10:30:00Z",
        service="payments",
        summary="Database connection timed out",
        target_ip=target_ip,
        target_port=target_port,
        error_code=error_code,
    )


def make_result(
    event_id: str,
    cases: tuple[RetrievedCase, ...] = (),
) -> RagResult:
    return RagResult(
        event_id=event_id,
        cases=cases,
        answer=AnalysisAnswer(
            root_cause="Unknown",
            evidence=(),
            recommendations=(),
            uncertainty="Insufficient evidence",
        ),
    )


class PromptFeedbackServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteFeedbackStore(
            str(Path(self.directory.name) / "feedback.sqlite3")
        )
        self.service = PromptFeedbackService(self.store)

    def test_missing_entities_create_traceable_pending_suggestion(self) -> None:
        event = make_event()

        suggestions = self.service.observe(event, make_result(event.event_id))

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].event_id, event.event_id)
        self.assertEqual(suggestions[0].category, "missing_entities")
        self.assertEqual(suggestions[0].status, FeedbackStatus.PENDING)
        self.assertIn("target_ip", suggestions[0].suggestion)
        self.assertIn("target_ip", suggestions[0].prompt_patch)
        self.assertIn("false positives", suggestions[0].risk_note)

        connection = sqlite3.connect(self.store.path)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(prompt_suggestions)")}
        connection.close()
        self.assertNotIn("raw_log", columns)
        self.assertNotIn("summary", columns)

    def test_complete_entities_and_no_cases_create_case_recall_suggestion(self) -> None:
        event = make_event(
            target_ip="192.0.2.10",
            target_port=5432,
            error_code="ERR-503",
        )

        suggestions = self.service.observe(event, make_result(event.event_id))

        self.assertEqual(suggestions[0].category, "no_retrieved_cases")
        self.assertIn("summary specificity", suggestions[0].suggestion)
        self.assertIn(
            "Preserve the concrete failing component", suggestions[0].prompt_patch
        )
        self.assertIn("top-5", suggestions[0].expected_metric)
        self.assertEqual(len(suggestions[0].validation_cases), 2)
        self.assertIn("token use", suggestions[0].risk_note)

    def test_complete_event_with_retrieved_case_has_no_feedback(self) -> None:
        event = make_event(
            target_ip="192.0.2.10",
            target_port=5432,
            error_code="ERR-503",
        )
        case = RetrievedCase(
            case_id="CASE-1",
            summary="Database timeout",
            resolution="Review pool limit",
            source="ticket-1",
            target_ip="192.0.2.10",
            score=0.9,
        )

        self.assertEqual(
            self.service.observe(event, make_result(event.event_id, (case,))), ()
        )

    def test_same_event_and_category_are_deduplicated(self) -> None:
        event = make_event()

        first = self.service.observe(event, make_result(event.event_id))[0]
        second = self.service.observe(event, make_result(event.event_id))[0]

        self.assertEqual(first.suggestion_id, second.suggestion_id)
        self.assertEqual(len(self.store.list()), 1)

    def test_review_and_publish_require_approved_state(self) -> None:
        suggestion = self.store.create(
            event_id="event-1",
            category="missing_entities",
            suggestion="Capture explicit error codes.",
            prompt_version="edge-summary-v1",
        )

        with self.assertRaises(FeedbackTransitionError):
            self.store.mark_published(suggestion.suggestion_id)

        approved = self.store.review(
            suggestion.suggestion_id,
            approve=True,
            reviewer="operator-1",
            note="Validated with labeled cases",
        )
        published = self.store.mark_published(approved.suggestion_id)

        self.assertEqual(published.status, FeedbackStatus.PUBLISHED)
        self.assertEqual(published.reviewed_by, "operator-1")
        self.assertIsNotNone(published.published_at)
        with self.assertRaises(FeedbackTransitionError):
            self.store.review(
                published.suggestion_id,
                approve=False,
                reviewer="operator-2",
            )

    def test_rejected_suggestion_cannot_be_published(self) -> None:
        suggestion = self.store.create(
            event_id="event-2",
            category="no_retrieved_cases",
            suggestion="Improve summary specificity.",
            prompt_version="edge-summary-v1",
        )
        rejected = self.store.review(
            suggestion.suggestion_id,
            approve=False,
            reviewer="operator-1",
        )

        self.assertEqual(rejected.status, FeedbackStatus.REJECTED)
        with self.assertRaises(FeedbackTransitionError):
            self.store.mark_published(rejected.suggestion_id)

    def test_weekly_report_counts_generated_reviewed_and_published(self) -> None:
        suggestion = self.store.create(
            event_id="event-3",
            category="missing_entities",
            suggestion="Capture explicit entities.",
            prompt_version="edge-summary-v1",
        )
        self.store.review(
            suggestion.suggestion_id,
            approve=True,
            reviewer="operator-1",
        )
        self.store.mark_published(suggestion.suggestion_id)

        report = self.store.weekly_report()

        self.assertEqual(report.generated, 1)
        self.assertEqual(report.reviewed_valid, 1)
        self.assertEqual(report.published, 1)


if __name__ == "__main__":
    unittest.main()