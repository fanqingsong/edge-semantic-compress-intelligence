from __future__ import annotations

from collections import defaultdict
from typing import Literal, TypedDict
from langgraph.graph import END, START, StateGraph

from edge.filtering.service import DropReason, LogRecord, RuleFilter
from edge.summarization.pipeline import SummaryPipeline
from edge.transport.outbox import FlushReport
from shared.contract import EdgeEvent


class EdgeGraphState(TypedDict, total=False):
    lines: list[str]
    groups: list[list[LogRecord]]
    dropped: dict[DropReason, int]
    index: int
    events: list[EdgeEvent]
    published: int
    pending: int


def build_edge_graph(rule_filter: RuleFilter, summarizer: SummaryPipeline, transport):
    """filter, then one summarize-and-submit step per service group."""

    def filter_records(state: EdgeGraphState) -> EdgeGraphState:
        report = rule_filter.process_batch(state["lines"])
        grouped: dict[str, list[LogRecord]] = defaultdict(list)
        for record in report.accepted:
            grouped[record.service].append(record)
        return {
            "groups": list(grouped.values()),
            "dropped": report.dropped,
            "index": 0,
            "events": [],
            "published": 0,
            "pending": 0,
        }

    def summarize_next(state: EdgeGraphState) -> EdgeGraphState:
        records = state["groups"][state["index"]]
        event = summarizer.summarize(records)
        publish_report: FlushReport = transport.submit(event)
        return {
            "events": [*state["events"], event],
            "published": state["published"] + publish_report.published,
            "pending": publish_report.pending,
            "index": state["index"] + 1,
        }

    def route(state: EdgeGraphState) -> Literal["summarize_next", "__end__"]:
        if state["index"] < len(state["groups"]):
            return "summarize_next"
        return END

    builder = StateGraph(EdgeGraphState)
    builder.add_node("filter", filter_records)
    builder.add_node("summarize_next", summarize_next)
    builder.add_edge(START, "filter")
    builder.add_conditional_edges("filter", route)
    builder.add_conditional_edges("summarize_next", route)
    return builder.compile()
