"""LangGraph that accepts one edge-event delivery and runs it once.

``cloud.agent.main`` wires this graph to Kafka. ``MqttEventConsumer`` can run
the same graph against MQTT. The ``handle`` step calls the analysis graph in
``cloud.agent.analysis_graph``.

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
   ask the analysis model, and upsert the result.
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

``handle`` is ``cloud.agent.analysis_graph``: analyze, then save.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from shared.codec import MessageCodec
from shared.contract import EdgeEvent


class ProcessedEventLookup(Protocol):
    def payload_hash(self, event_id: str) -> str | None:
        """Return the previously processed payload hash, if any."""

    def mark_processed(self, event_id: str, payload_hash: str) -> None:
        """Persist a successfully processed event identity."""


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
