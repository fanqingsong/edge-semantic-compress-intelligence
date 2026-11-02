import tempfile
import unittest
from pathlib import Path

from cloud.agent.runtime import (
    RagEventHandler,
    SQLiteAnalysisStore,
)
from cloud.retrieval.hashing import (
    DeterministicHashEmbedder,
)
from shared.contract import EdgeEvent
from cloud.feedback import (
    FeedbackStatus,
    PromptFeedbackService,
    SQLiteFeedbackStore,
)
from cloud.rag import (
    DeterministicMockAnalysisModel,
    RagService,
)


class EmptyRetriever:
    def retrieve(self, event: EdgeEvent) -> tuple[()]:
        return ()


class CloudRuntimeTests(unittest.TestCase):
    def test_mock_embedding_is_deterministic_and_dimensioned(self) -> None:
        embedder = DeterministicHashEmbedder(dimension=16)

        first = embedder.embed("database timeout")
        second = embedder.embed("database timeout")

        self.assertEqual(len(first), 16)
        self.assertEqual(first, second)

    def test_handler_persists_rag_result_by_event_id(self) -> None:
        event = EdgeEvent(
            event_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp="2026-11-01T10:30:00Z",
            service="payments",
            summary="Database connection timed out",
        )
        rag_service = RagService(EmptyRetriever(), DeterministicMockAnalysisModel())
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteAnalysisStore(str(Path(directory) / "analyses.sqlite3"))
            handler = RagEventHandler(rag_service, store)

            handler(event)
            result = store.get(event.event_id)

            self.assertEqual(result["event_id"], event.event_id)
            self.assertIn("Mock response", result["answer"]["root_cause"])

    def test_rag_handler_records_feedback_without_raw_log(self) -> None:
        event = EdgeEvent(
            event_id="550e8400-e29b-41d4-a716-446655440001",
            timestamp="2026-11-01T10:30:00Z",
            service="payments",
            summary="Database timeout",
        )
        rag_service = RagService(EmptyRetriever(), DeterministicMockAnalysisModel())
        with tempfile.TemporaryDirectory() as directory:
            analysis_store = SQLiteAnalysisStore(
                str(Path(directory) / "analyses.sqlite3")
            )
            feedback_store = SQLiteFeedbackStore(
                str(Path(directory) / "feedback.sqlite3")
            )
            handler = RagEventHandler(
                rag_service,
                analysis_store,
                PromptFeedbackService(feedback_store),
            )

            handler(event)

            suggestions = feedback_store.list()
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0].event_id, event.event_id)
            self.assertEqual(suggestions[0].status, FeedbackStatus.PENDING)
            self.assertEqual(analysis_store.get(event.event_id)["event_id"], event.event_id)


if __name__ == "__main__":
    unittest.main()