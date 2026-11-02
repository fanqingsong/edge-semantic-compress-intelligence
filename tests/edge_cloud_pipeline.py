from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from shared.contract import EdgeEvent
from edge.filtering import DropReason, RuleFilter
from cloud.rag import RagResult, RagService
from edge.summarization import SummaryPipeline


@dataclass(frozen=True, slots=True)
class PipelineReport:
    events: tuple[EdgeEvent, ...]
    analyses: tuple[RagResult, ...]
    dropped_by_reason: dict[DropReason, int]


@dataclass(frozen=True, slots=True)
class EdgeCloudPipeline:
    rule_filter: RuleFilter
    summarizer: SummaryPipeline
    rag_service: RagService

    def process_batch(self, lines: Iterable[str]) -> PipelineReport:
        filter_report = self.rule_filter.process_batch(lines)
        records_by_service = defaultdict(list)
        for record in filter_report.accepted:
            records_by_service[record.service].append(record)

        events: list[EdgeEvent] = []
        analyses: list[RagResult] = []
        for records in records_by_service.values():
            event = self.summarizer.summarize(records)
            events.append(event)
            analyses.append(self.rag_service.analyze(event))

        return PipelineReport(
            events=tuple(events),
            analyses=tuple(analyses),
            dropped_by_reason=filter_report.dropped,
        )