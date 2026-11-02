import unittest
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from shared.contract import EdgeEvent
from cloud.rag import RetrievedCase
from cloud.retrieval import (
    HybridRetriever,
    VectorHit,
)


@dataclass
class FixedEmbedder:
    calls: list[str] = field(default_factory=list)

    def embed(self, text: str) -> Sequence[float]:
        self.calls.append(text)
        return (0.25, 0.75)


@dataclass
class FixedVectorIndex:
    hits: tuple[VectorHit, ...]
    filters: list[Mapping[str, str]] = field(default_factory=list)
    limits: list[int] = field(default_factory=list)

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
        self.limits.append(limit)
        return self.hits


def event(target_ip: str | None = "192.0.2.10") -> EdgeEvent:
    return EdgeEvent(
        event_id="550e8400-e29b-41d4-a716-446655440000",
        timestamp="2026-11-01T10:30:00Z",
        service="payments",
        target_ip=target_ip,
        summary="Database connection timed out",
    )


def hit(case_id: str, target_ip: str, score: float = 0.9) -> VectorHit:
    return VectorHit(
        case_id=case_id,
        summary="Connection pool exhaustion",
        resolution="Review pool configuration",
        source="ticket-17",
        target_ip=target_ip,
        score=score,
    )


class HybridRetrieverTests(unittest.TestCase):
    def test_search_uses_summary_and_exact_ip_filter(self) -> None:
        embedder = FixedEmbedder()
        index = FixedVectorIndex((hit("CASE-1", "192.0.2.10"),))
        result = HybridRetriever(embedder, index).retrieve(event())

        self.assertEqual(embedder.calls, ["Database connection timed out"])
        self.assertEqual(index.filters, [{"target_ip": "192.0.2.10"}])
        self.assertEqual(index.limits, [5])
        self.assertEqual(
            result,
            (
                RetrievedCase(
                    case_id="CASE-1",
                    summary="Connection pool exhaustion",
                    resolution="Review pool configuration",
                    source="ticket-17",
                    target_ip="192.0.2.10",
                    score=0.9,
                ),
            ),
        )

    def test_results_with_other_ips_are_rejected(self) -> None:
        index = FixedVectorIndex(
            (
                hit("CASE-OTHER", "192.0.2.11"),
                hit("CASE-MATCH", "192.0.2.10"),
            )
        )
        result = HybridRetriever(FixedEmbedder(), index).retrieve(event())

        self.assertEqual([case.case_id for case in result], ["CASE-MATCH"])

    def test_missing_ip_does_not_fall_back_to_vector_only_search(self) -> None:
        embedder = FixedEmbedder()
        index = FixedVectorIndex((hit("CASE-1", "192.0.2.10"),))

        result = HybridRetriever(embedder, index).retrieve(event(target_ip=None))

        self.assertEqual(result, ())
        self.assertEqual(embedder.calls, [])
        self.assertEqual(index.filters, [])

    def test_non_finite_scores_are_rejected(self) -> None:
        index = FixedVectorIndex((hit("CASE-NAN", "192.0.2.10", float("nan")),))

        result = HybridRetriever(FixedEmbedder(), index).retrieve(event())

        self.assertEqual(result, ())

    def test_top_k_is_fixed_to_five(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_k=5"):
            HybridRetriever(FixedEmbedder(), FixedVectorIndex(()), top_k=10)


if __name__ == "__main__":
    unittest.main()