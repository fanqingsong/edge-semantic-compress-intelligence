"""LangGraph that turns one log batch into per-service edge events.

Runtime path (assembled in ``edge.agent.main``, driven by ``EdgeRuntime``):

1. HTTP ``POST /v1/logs`` (``edge.agent.http``) accepts a UTF-8 body of JSON
   Lines, drops blank lines, and calls ``EdgeRuntime.process_batch``.
2. ``EdgeRuntime`` invokes this graph once with ``{"lines": [...]}``. The
   recursion limit is raised above LangGraph's default of 25 because the
   graph takes one step per service group, plus the filter step.
3. ``filter`` parses and drops noise, then buckets the survivors by service.
4. ``summarize_next`` runs once per bucket: the summary pipeline produces one
   ``EdgeEvent``, and the transport persists it before trying MQTT.
5. ``route`` loops back to ``summarize_next`` until every group is consumed,
   then ends. The final state becomes ``EdgeRuntimeReport`` (events, drop
   counts, published count, and how many events are still in the outbox).

Nothing in the graph talks to the network directly. Filtering, summarization,
and delivery are injected. The runtime summarizer is llama.cpp, and delivery
goes through the SQLite outbox before MQTT.

Topology of one batch::

    log source
        |  POST /v1/logs (JSON Lines; blank lines already dropped)
        v
    HTTP handler
        |  EdgeRuntime.process_batch({"lines"})
        v
    START --> filter (RuleFilter)
                 |
                 +-- drop, count only
                 |     invalid JSON
                 |     success status (200 / ok)
                 |     blacklist (heartbeat / health check)
                 |     repeats past the threshold (keep first and last)
                 |
                 +-- keep, group by service
                        |
                        v
                   +--> route ---- no groups left --> END
                   |      |
                   |      | next service group
                   |      v
                   |   summarize_next
                   |      |
                   |      +-- SummaryPipeline
                   |      |     SLM (llama.cpp)
                   |      |       --> EntityFallback (ip / port / error_code)
                   |      |       --> EdgeEvent
                   |      |
                   |      +-- ReliableMqttTransport.submit
                   |            1. enqueue SQLite outbox
                   |            2. flush one row, MQTT QoS 1
                   |                 ack  --> published
                   |                 fail --> pending
                   |
                   +------ more groups remain
                        |
                        v
                   EdgeRuntimeReport
                     events, dropped, published, pending
                        |
                        v
                   HTTP response
                     200 all published | 202 still pending | 507 outbox full
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal, TypedDict
from langgraph.graph import END, START, StateGraph

from edge.filtering.service import DropReason, LogRecord, RuleFilter
from edge.summarization.pipeline import SummaryPipeline
from edge.transport.outbox import FlushReport
from shared.contract import EdgeEvent


class EdgeGraphState(TypedDict, total=False):
    """Working memory for one batch. Only ``lines`` is supplied by the caller.

    ``groups``
        Accepted records split by ``service``. Each inner list is summarized
        into exactly one event. Order follows first appearance of the service.
    ``dropped``
        Counts from the rule filter, keyed by ``DropReason``: invalid JSON,
        success status (``200`` / ``ok``), blacklisted keywords (heartbeat /
        health check), and repeats of the same service+message beyond the
        threshold (the first and last copy are kept).
    ``index``
        Next group to summarize. Starts at 0; the route ends when it reaches
        ``len(groups)``.
    ``events``
        ``EdgeEvent`` values produced so far, in group order.
    ``published``
        How many outbox rows this batch confirmed to the broker. Each
        ``summarize_next`` adds only that step's flush count (limit 1), so
        earlier rows that fail to publish stay in ``pending``.
    ``pending``
        Outbox depth after the latest flush, including events left by earlier
        batches. Overwritten on every submit, so the last value is the one
        reported to the HTTP caller (202 when non-zero, otherwise 200).
    """

    lines: list[str]
    groups: list[list[LogRecord]]
    dropped: dict[DropReason, int]
    index: int
    events: list[EdgeEvent]
    published: int
    pending: int


def build_edge_graph(rule_filter: RuleFilter, summarizer: SummaryPipeline, transport):
    """Compile the filter-then-summarize graph.

    ``transport`` matches ``EventTransport``: ``submit(event)`` enqueues the
    MessagePack payload in SQLite, then flushes at most one pending row with
    MQTT QoS 1. A missing broker ack leaves the row in the outbox and stops
    the flush; a full outbox raises ``OutboxFullError``, which the HTTP layer
    maps to 507.
    """

    def filter_records(state: EdgeGraphState) -> EdgeGraphState:
        """Drop noise, then group what remains by service.

        ``RuleFilter.process_batch`` is the whole admission policy: malformed
        lines, successful statuses, blacklisted keywords, then frequency
        suppression. Records that pass are partitioned so later nodes never
        mix two services into one summary. Counters and the cursor are reset
        here; ``lines`` is left untouched because this node does not return it.
        """
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
        """Summarize group ``index`` and hand the event to the outbox.

        ``SummaryPipeline.summarize`` asks the configured chat model for structured fields, then
        ``EntityFallback`` keeps ``target_ip``, ``target_port``, and ``error_code`` only when they
        actually appear in the source records. ``EdgeEvent.from_mapping``
        rejects a summary that breaks the contract.

        ``transport.submit`` writes the event before publish, so a broker
        outage does not lose it. ``published`` accumulates this batch's
        successes; ``pending`` is the outbox size after this flush, not a
        delta.
        """
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
        """Continue while a service group is still waiting.

        An empty batch (every line dropped, or no lines) has ``index == 0``
        and no groups, so the graph ends immediately after ``filter``.
        """
        if state["index"] < len(state["groups"]):
            return "summarize_next"
        return END

    builder = StateGraph(EdgeGraphState)
    builder.add_node("filter", filter_records)
    builder.add_node("summarize_next", summarize_next)
    # filter always runs first; both nodes share the same "more groups?" check.
    builder.add_edge(START, "filter")
    builder.add_conditional_edges("filter", route)
    builder.add_conditional_edges("summarize_next", route)
    return builder.compile()
