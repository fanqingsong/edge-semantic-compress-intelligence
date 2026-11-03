"""LangGraph that turns one edge event into a stored RAG analysis.

``RagEventHandler`` compiles this graph and the consume graph in
``cloud.agent.consume_graph`` calls it as the ``handle`` step. A failure in any node
aborts that outer graph before the event is marked processed, so the delivery
is retried instead of being acknowledged.

Topology::

    START --> analyze (RagService)
                 |
                 +-- HybridRetriever
                 |     no target_ip --> no cases
                 |     else embed summary (BGE-M3)
                 |          Milvus top 5, filtered to that IP
                 +-- prompt: edge_summary + retrieved_cases
                 +-- model: OpenAI-compatible LLM
                 |
                 v
              save (SQLite analyses, upsert by event_id)
                 |
                 v
              END
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from cloud.rag.analysis import RagResult, RagService
from shared.contract import EdgeEvent


class AnalysisStore(Protocol):
    def save(self, result: RagResult) -> None:
        """Persist one analysis result."""


class AnalysisState(TypedDict, total=False):
    """Working memory for one analysis. The caller supplies ``event``.

    ``result``
        ``RagResult`` from ``analyze``: the event id, the retrieved cases,
        and the model's root cause, evidence, recommendations, and uncertainty.
        ``save`` only reads it.
    """

    event: EdgeEvent
    result: RagResult


def build_analysis_graph(rag_service: RagService, analysis_store: AnalysisStore):
    """Compile analyze → save.

    ``RagEventHandler`` invokes this with ``{"event": event}``.
    """

    def analyze(state: AnalysisState) -> AnalysisState:
        """Retrieve cases for the event and ask the analysis model.

        ``HybridRetriever`` returns nothing when ``target_ip`` is missing.
        Otherwise it embeds ``summary`` and searches Milvus for the top 5
        cases with that same IP. The prompt treats the summary and the cases
        as untrusted data. The model is the OpenAI-compatible endpoint.
        """
        return {"result": rag_service.analyze(state["event"])}

    def save(state: AnalysisState) -> AnalysisState:
        """Upsert the analysis JSON, keyed by ``event_id``."""
        analysis_store.save(state["result"])
        return {}

    builder = StateGraph(AnalysisState)
    builder.add_node("analyze", analyze)
    builder.add_node("save", save)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "save")
    builder.add_edge("save", END)
    return builder.compile()
