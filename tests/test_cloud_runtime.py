import tempfile
import unittest
from pathlib import Path

from cloud.agent.runtime import (
    RagEventHandler,
    SQLiteAnalysisStore,
)
from shared.contract import EdgeEvent
from cloud.rag import RagService
from tests.standins import FixedAnalysisModel


class EmptyRetriever:
    def retrieve(self, event: EdgeEvent) -> tuple[()]:
        return ()


class CloudRuntimeTests(unittest.TestCase):
    def test_handler_persists_rag_result_by_event_id(self) -> None:
        event = EdgeEvent(
            event_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp="2026-11-01T10:30:00Z",
            service="payments",
            summary="Database connection timed out",
        )
        rag_service = RagService(EmptyRetriever(), FixedAnalysisModel())
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteAnalysisStore(str(Path(directory) / "analyses.sqlite3"))
            handler = RagEventHandler(rag_service, store)

            handler(event)
            result = store.get(event.event_id)

            self.assertEqual(result["event_id"], event.event_id)
            self.assertEqual(
                result["answer"]["root_cause"], "Likely connection saturation"
            )


if __name__ == "__main__":
    unittest.main()