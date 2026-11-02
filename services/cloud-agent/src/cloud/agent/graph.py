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
    event: EdgeEvent
    result: RagResult


class ConsumeState(TypedDict, total=False):
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
    """analyze → save → observe. The consumer calls this through its handler."""

    def analyze(state: AnalysisState) -> AnalysisState:
        return {"result": rag_service.analyze(state["event"])}

    def save(state: AnalysisState) -> AnalysisState:
        analysis_store.save(state["result"])
        return {}

    def observe(state: AnalysisState) -> AnalysisState:
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
    """decode → classify → handler → mark_processed.

    Invalid payloads, conflicting event IDs, and duplicates stop before the
    handler. Only a new event is marked processed, and only after the handler
    returns. ACK stays with the caller.
    """

    def decode(state: ConsumeState) -> ConsumeState:
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
        previous_hash = store.payload_hash(state["event_id"])
        if previous_hash is None:
            return {"disposition": "new"}
        if previous_hash != state["payload_hash"]:
            return {"disposition": "event_id_conflict"}
        return {"disposition": "duplicate"}

    def handle(state: ConsumeState) -> ConsumeState:
        handler(state["event"])
        return {}

    def mark_processed(state: ConsumeState) -> ConsumeState:
        store.mark_processed(state["event_id"], state["payload_hash"])
        return {"disposition": "processed"}

    def route_after_decode(state: ConsumeState) -> Literal["classify", "__end__"]:
        if state.get("disposition") == "invalid_payload":
            return END
        return "classify"

    def route_after_classify(state: ConsumeState) -> Literal["handle", "__end__"]:
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
