# ADR-0007: RAG orchestration and inference model

- Status: Accepted for orchestration; inference model still pending
- Date: 2026-11-01
- Related PRD: PRD-06
- Code: [RAG](../services/cloud/rag.md)

## Context

The cloud must assemble the edge summary and hybrid-retrieval cases into analysis context, then produce root-cause analysis and remediation suggestions. The technical design lists two orchestration frameworks and two inference deployment options.

## Current architecture constraints

- RAG input includes the edge summary and the cases returned by PRD-05.
- The prompt must contain the three sections `<edge_summary>`, `<retrieved_cases>`, and `<analysis_instructions>`.
- Response time is under 10 seconds. The actionability score is at least 4/5.
- The output should separate retrieved evidence from model inference and support effect evaluation.

## Decision

- The edge agent and the cloud agent use LangGraph `StateGraph` for control flow. The cloud graph branches on decode and idempotency, then runs analysis and persistence. The edge graph filters a batch and loops once per service. Retrieval, prompt assembly, and model adapters stay in their current modules.
- The graphs do not use a LangGraph checkpointer. `processed.sqlite3` and the edge outbox remain the durability mechanisms.
- Recorded: 2026-11-02.

## Open decisions

- Choose an inference model between self-hosted Qwen2.5-72B-Instruct on vLLM and the Claude API.
- Validate the choice against data compliance, latency, cost, availability, and operational capacity.
- Define behavior for timeout, rate limiting, model unavailability, empty retrieval, and high-risk suggestions.

## Consequences

- The model and the orchestration framework affect deployment, request latency, operational responsibility, and cost.
- A model or prompt change needs regression tests on a fixed evaluation set.

## Candidates

- LangGraph is the agent control-flow layer. A self-hosted Qwen model on vLLM, or a call to the Claude API, remains the inference choice.
