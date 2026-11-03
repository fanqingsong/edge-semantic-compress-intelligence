"""LangGraphs that turn one edge event into a stored RAG analysis.

Two graphs, nested. ``cloud.agent.main`` wires the outer one to Kafka;
``MqttEventConsumer`` can run the same outer graph against MQTT. The inner
graph is the handler the outer graph calls.

Runtime path:

1. Kafka polls ``edge.events`` with auto-commit off and one record per poll.
   The payload is the MessagePack ``EdgeEvent`` published by the edge agent.
2. ``KafkaEventConsumer.handle_payload`` invokes the consume graph under a
   lock. MQTT uses the same graph, then ACKs the message instead of a Kafka
   offset. The graph itself never acknowledges.
3. Consume graph: decode the payload, classify it against the SQLite
   processed-event store, and stop unless the event is new. A new event is
   handed to ``RagEventHandler``, then marked processed only after that
   handler returns.
4. ``RagEventHandler`` invokes the analysis graph: retrieve similar cases,
   ask the analysis model, upsert the result, then record a prompt suggestion
   when the event is a weak summary.
5. The caller commits the Kafka offset only for ``processed`` and
   ``duplicate``. Any other disposition seeks back to that record and retries
   after one second. A commit failure is reported as ``ack_failed``.

Topology of one payload::

    Kafka edge.events (or MQTT QoS 1)
        |  MessagePack EdgeEvent, auto-commit off
        v
    KafkaEventConsumer.handle_payload
        |
        v
    consume graph
        START --> decode (MessagePackCodec, sha256 of the raw payload)
                     |
                     +-- invalid_payload --> END
                     |
                     +-- decoded
                           |
                           v
                        classify (processed_events by event_id)
                           |
                           +-- duplicate -----------> END
                           +-- event_id_conflict ---> END
                           |
                           +-- new
                                 |
                                 v
                              handle = analysis graph
                                 |
                                 v
                              mark_processed (event_id + payload hash)
                                 |
                                 v
                              END  disposition=processed
        |
        +-- processed or duplicate --> commit offset (MQTT: ACK)
        +-- anything else -----------> seek back, sleep 1s, retry
            (handler exception is processing_failed, outside the graph)

    analysis graph, invoked as handle
        START --> analyze (RagService)
                     |
                     +-- HybridRetriever
                     |     no target_ip --> no cases
                     |     else embed summary (BGE-M3 or hash mock)
                     |          Milvus top 5, filtered to that IP
                     +-- prompt: edge_summary + retrieved_cases
                     +-- model: OpenAI-compatible LLM or mock
                     |
                     v
                  save (SQLite analyses, upsert by event_id)
                     |
                     v
                  observe (PromptFeedbackService; skipped when unset)
                     |
                     +-- missing target_ip / target_port / error_code
                     |     --> suggestion "missing_entities"
                     +-- entities present but no retrieved cases
                     |     --> suggestion "no_retrieved_cases"
                     +-- otherwise write nothing
                     |
                     v
                  END
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from cloud.feedback.service import PromptFeedbackService
from cloud.rag.analysis import RagResult, RagService
from shared.codec import MessageCodec
from shared.contract import EdgeEvent


class AnalysisStore(Protocol):
    def save(self, result: RagResult) -> None:
        """Persist one analysis result."""


class ProcessedEventLookup(Protocol):
    def payload_hash(self, event_id: str) -> str | None:
        """Return the previously processed payload hash, if any."""

    def mark_processed(self, event_id: str, payload_hash: str) -> None:
        """Persist a successfully processed event identity."""


class AnalysisState(TypedDict, total=False):
    """Working memory for one analysis. The caller supplies ``event``.

    ``result``
        ``RagResult`` from ``analyze``: the event id, the retrieved cases,
        and the model's root cause, evidence, recommendations, and uncertainty.
        ``save`` and ``observe`` only read it.
    """

    event: EdgeEvent
    result: RagResult


class ConsumeState(TypedDict, total=False):
    """Working memory for one delivery. The caller supplies ``payload``.

    ``event`` / ``event_id``
        Decoded ``EdgeEvent``. Absent when the payload is not valid MessagePack.
    ``payload_hash``
        SHA-256 of the raw bytes. Identity is ``event_id`` plus this hash, so
        the same id with a different body is a conflict rather than a replay.
    ``disposition``
        ``decoded``, then ``new`` / ``duplicate`` / ``event_id_conflict``,
        or ``invalid_payload`` / ``processed``. The Kafka and MQTT callers
        treat only ``processed`` and ``duplicate`` as safe to acknowledge.
    """

    payload: bytes
    event: EdgeEvent
    event_id: str
    payload_hash: str
    disposition: str


def build_analysis_graph(
    rag_service: RagService,
    analysis_store: AnalysisStore,
    feedback_service: PromptFeedbackService | None,
):
    """Compile analyze → save → observe.

    ``RagEventHandler`` invokes this with ``{"event": event}``. A failure in
    any node aborts the consume graph before ``mark_processed``, so the
    delivery is retried instead of being acknowledged.
    """

    def analyze(state: AnalysisState) -> AnalysisState:
        """Retrieve cases for the event and ask the analysis model.

        ``HybridRetriever`` returns nothing when ``target_ip`` is missing.
        Otherwise it embeds ``summary`` and searches Milvus for the top 5
        cases with that same IP. The prompt treats the summary and the cases
        as untrusted data. The model is the OpenAI-compatible endpoint or the
        deterministic mock.
        """
        return {"result": rag_service.analyze(state["event"])}

    def save(state: AnalysisState) -> AnalysisState:
        """Upsert the analysis JSON, keyed by ``event_id``."""
        analysis_store.save(state["result"])
        return {}

    def observe(state: AnalysisState) -> AnalysisState:
        """Record a prompt suggestion when this event shows a summary gap.

        Missing ``target_ip``, ``target_port``, or ``error_code`` produces a
        ``missing_entities`` suggestion. Entities present but zero retrieved
        cases produce ``no_retrieved_cases``. A complete event with cases
        writes nothing. No suggestion is written when feedback is not wired.
        """
        if feedback_service is not None:
            feedback_service.observe(state["event"], state["result"])
        return {}

    builder = StateGraph(AnalysisState)
    builder.add_node("analyze", analyze)
    builder.add_node("save", save)
    builder.add_node("observe", observe)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "save")
    builder.add_edge("save", "observe")
    builder.add_edge("observe", END)
    return builder.compile()


def build_consume_graph(
    codec: MessageCodec,
    store: ProcessedEventLookup,
    handler: Callable[[EdgeEvent], None],
):
    """Compile decode → classify → handler → mark_processed.

    Invalid payloads, conflicting event IDs, and duplicates stop before the
    handler. Only a new event is marked processed, and only after the handler
    returns. ACK stays with the caller.
    """

    def decode(state: ConsumeState) -> ConsumeState:
        """Turn MessagePack bytes into an event, or stop as invalid.

        The hash covers the raw payload, not the decoded fields, so two
        encodings of the same logical event still compare as different bodies.
        """
        try:
            event = codec.decode(state["payload"])
        except Exception:
            return {"disposition": "invalid_payload"}
        return {
            "event": event,
            "event_id": event.event_id,
            "payload_hash": hashlib.sha256(state["payload"]).hexdigest(),
            "disposition": "decoded",
        }

    def classify(state: ConsumeState) -> ConsumeState:
        """Decide whether this event id has been seen, and with which body.

        No row means ``new``. The same hash means ``duplicate`` and is safe
        to acknowledge without running RAG again. A different hash for the
        same id is ``event_id_conflict`` and is not acknowledged.
        """
        previous_hash = store.payload_hash(state["event_id"])
        if previous_hash is None:
            return {"disposition": "new"}
        if previous_hash != state["payload_hash"]:
            return {"disposition": "event_id_conflict"}
        return {"disposition": "duplicate"}

    def handle(state: ConsumeState) -> ConsumeState:
        """Run the analysis graph. Exceptions skip ``mark_processed``."""
        handler(state["event"])
        return {}

    def mark_processed(state: ConsumeState) -> ConsumeState:
        """Record event id and payload hash after a successful handler."""
        store.mark_processed(state["event_id"], state["payload_hash"])
        return {"disposition": "processed"}

    def route_after_decode(state: ConsumeState) -> Literal["classify", "__end__"]:
        """Skip classification when the payload could not be decoded."""
        if state.get("disposition") == "invalid_payload":
            return END
        return "classify"

    def route_after_classify(state: ConsumeState) -> Literal["handle", "__end__"]:
        """Run the handler only for an event id that is not already stored."""
        if state.get("disposition") == "new":
            return "handle"
        return END

    builder = StateGraph(ConsumeState)
    builder.add_node("decode", decode)
    builder.add_node("classify", classify)
    builder.add_node("handle", handle)
    builder.add_node("mark_processed", mark_processed)
    builder.add_edge(START, "decode")
    builder.add_conditional_edges("decode", route_after_decode)
    builder.add_conditional_edges("classify", route_after_classify)
    builder.add_edge("handle", "mark_processed")
    builder.add_edge("mark_processed", END)
    return builder.compile()
