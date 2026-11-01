from __future__ import annotations

import ipaddress
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.cloud.rag import RetrievedCase


@dataclass(frozen=True, slots=True)
class VectorHit:
    case_id: str
    summary: str
    resolution: str
    source: str
    target_ip: str | None
    score: float


@dataclass(frozen=True, slots=True)
class VectorRecord:
    case_id: str
    summary: str
    resolution: str
    source: str
    target_ip: str | None
    version: str
    vector: tuple[float, ...]


class TextEmbedder(Protocol):
    def embed(self, text: str) -> Sequence[float]:
        """Return a vector representation for text."""


class VectorIndex(Protocol):
    def upsert(self, records: Sequence[VectorRecord]) -> None:
        """Insert or replace records by case ID."""

    def delete_source_records_not_in(self, source: str, case_ids: set[str]) -> int:
        """Remove stale records belonging to a replaced source document."""

    def search(
        self,
        vector: Sequence[float],
        *,
        metadata_filter: Mapping[str, str],
        limit: int,
    ) -> Sequence[VectorHit]:
        """Search vectors with a mandatory metadata filter."""


@dataclass(frozen=True, slots=True)
class HybridRetriever:
    embedder: TextEmbedder
    index: VectorIndex
    top_k: int = 5

    def __post_init__(self) -> None:
        if self.top_k != 5:
            raise ValueError("the current retrieval contract requires top_k=5")

    def retrieve(self, event: EdgeEvent) -> tuple[RetrievedCase, ...]:
        if event.target_ip is None:
            return ()

        normalized_ip = str(ipaddress.ip_address(event.target_ip))
        vector = tuple(self.embedder.embed(event.summary))
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError("embedder must return a non-empty finite vector")

        hits = self.index.search(
            vector,
            metadata_filter={"target_ip": normalized_ip},
            limit=self.top_k,
        )

        cases: list[RetrievedCase] = []
        seen_case_ids: set[str] = set()
        for hit in hits:
            if hit.case_id in seen_case_ids or hit.target_ip is None:
                continue
            try:
                hit_ip = str(ipaddress.ip_address(hit.target_ip))
            except ValueError:
                continue
            if hit_ip != normalized_ip or not math.isfinite(hit.score):
                continue

            cases.append(
                RetrievedCase(
                    case_id=hit.case_id,
                    summary=hit.summary,
                    resolution=hit.resolution,
                    source=hit.source,
                    target_ip=hit_ip,
                    score=hit.score,
                )
            )
            seen_case_ids.add(hit.case_id)
            if len(cases) == self.top_k:
                break

        return tuple(cases)