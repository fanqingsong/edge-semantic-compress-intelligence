from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from edge.agent.graph import build_edge_graph
from edge.filtering.service import DropReason, RuleFilter
from edge.summarization.pipeline import SummaryPipeline
from edge.transport.outbox import FlushReport
from shared.contract import EdgeEvent


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
    _graph: object = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_graph",
            build_edge_graph(self.rule_filter, self.summarizer, self.transport),
        )

    def process_batch(self, lines: Iterable[str]) -> EdgeRuntimeReport:
        materialized = list(lines)
        # One graph step per service, plus the filter step. The default limit is 25.
        state = self._graph.invoke(
            {"lines": materialized},
            {"recursion_limit": max(50, len(materialized) + 5)},
        )
        return EdgeRuntimeReport(
            events=tuple(state["events"]),
            dropped_by_reason=state["dropped"],
            published=state["published"],
            pending=state["pending"],
        )
