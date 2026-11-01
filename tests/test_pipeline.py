import json
import unittest
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from edge_semantic_compress_intelligence.filtering import (
    DropReason,
    FilterConfig,
    RuleFilter,
)
from edge_semantic_compress_intelligence.pipeline import EdgeCloudPipeline
from edge_semantic_compress_intelligence.rag import (
    DeterministicMockAnalysisModel,
    RagService,
)
from edge_semantic_compress_intelligence.retrieval import (
    HybridRetriever,
    VectorHit,
)
from edge_semantic_compress_intelligence.summarization import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)


@dataclass
class FixedEmbedder:
    texts: list[str] = field(default_factory=list)

    def embed(self, text: str) -> Sequence[float]:
        self.texts.append(text)
        return (0.1, 0.9)


@dataclass
class FixedIndex:
    filters: list[Mapping[str, str]] = field(default_factory=list)

    def upsert(self, records: Sequence[object]) -> None:
        return None

    def delete_source_records_not_in(self, source: str, case_ids: set[str]) -> int:
        return 0

    def search(
        self,
        vector: Sequence[float],
        *,
        metadata_filter: Mapping[str, str],
        limit: int,
    ) -> Sequence[VectorHit]:
        self.filters.append(metadata_filter)
        return (
            VectorHit(
                case_id="CASE-1",
                summary="Database connection timeout",
                resolution="Review the database connection pool",
                source="ticket-17",
                target_ip="192.0.2.10",
                score=0.93,
            ),
        )


def line(message: str, *, status_code: int = 500) -> str:
    return json.dumps(
        {
            "timestamp": "2026-11-01T10:30:00Z",
            "service": "payments",
            "message": message,
            "status_code": status_code,
            "target_ip": "192.0.2.10",
        }
    )


class EdgeCloudPipelineTests(unittest.TestCase):
    def test_batch_flows_from_filtering_to_rag(self) -> None:
        embedder = FixedEmbedder()
        index = FixedIndex()
        pipeline = EdgeCloudPipeline(
            rule_filter=RuleFilter(FilterConfig(repeat_threshold=5)),
            summarizer=SummaryPipeline(DeterministicMockSummarizer()),
            rag_service=RagService(
                HybridRetriever(embedder, index), DeterministicMockAnalysisModel()
            ),
        )

        report = pipeline.process_batch(
            [
                line("Database connection timed out port=5432 ERR-42"),
                line("health check heartbeat"),
            ]
        )

        self.assertEqual(len(report.events), 1)
        self.assertEqual(report.events[0].target_ip, "192.0.2.10")
        self.assertEqual(report.events[0].target_port, 5432)
        self.assertEqual(report.events[0].error_code, "ERR-42")
        self.assertEqual(report.analyses[0].cases[0].case_id, "CASE-1")
        self.assertIn("Mock response", report.analyses[0].answer.root_cause)
        self.assertEqual(
            report.dropped_by_reason[DropReason.BLACKLISTED_KEYWORD], 1
        )
        self.assertEqual(index.filters, [{"target_ip": "192.0.2.10"}])
        self.assertEqual(embedder.texts, [report.events[0].summary])

    def test_all_filtered_batch_has_no_events_or_analyses(self) -> None:
        pipeline = EdgeCloudPipeline(
            rule_filter=RuleFilter(),
            summarizer=SummaryPipeline(DeterministicMockSummarizer()),
            rag_service=RagService(
                HybridRetriever(FixedEmbedder(), FixedIndex()),
                DeterministicMockAnalysisModel(),
            ),
        )

        report = pipeline.process_batch([line("health check heartbeat")])

        self.assertEqual(report.events, ())
        self.assertEqual(report.analyses, ())


if __name__ == "__main__":
    unittest.main()