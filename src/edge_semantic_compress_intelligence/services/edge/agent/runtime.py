from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.edge.filtering.service import (
    DropReason,
    RuleFilter,
)
from edge_semantic_compress_intelligence.services.edge.summarization.pipeline import (
    SummaryPipeline,
)
from edge_semantic_compress_intelligence.services.edge.transport.outbox import FlushReport


class EventTransport(Protocol):
    def submit(self, event: EdgeEvent) -> FlushReport:
        """Persist and publish an event, retaining it if the broker is unavailable."""


@dataclass(frozen=True, slots=True)
class EdgeRuntimeReport:
    events: tuple[EdgeEvent, ...]
    dropped_by_reason: dict[DropReason, int]
    published: int
    pending: int


@dataclass(frozen=True, slots=True)
class EdgeRuntime:
    rule_filter: RuleFilter
    summarizer: SummaryPipeline
    transport: EventTransport

    def process_batch(self, lines: Iterable[str]) -> EdgeRuntimeReport:
        filter_report = self.rule_filter.process_batch(lines)
        records_by_service = defaultdict(list)
        for record in filter_report.accepted:
            records_by_service[record.service].append(record)

        events: list[EdgeEvent] = []
        published = 0
        pending = 0
        for records in records_by_service.values():
            event = self.summarizer.summarize(records)
            publish_report = self.transport.submit(event)
            events.append(event)
            published += publish_report.published
            pending = publish_report.pending

        return EdgeRuntimeReport(
            events=tuple(events),
            dropped_by_reason=filter_report.dropped,
            published=published,
            pending=pending,
        )