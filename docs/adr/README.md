# Architecture decision records

This directory records architecture decisions that affect system boundaries, technology choices, and cross-component contracts. Business goals and acceptance criteria are in the [PRD index](../prds/README.md) and the individual PRDs. Implementation locations are in the [service catalog](../services/README.md). The technical background comes from the [technical design](../technology).

## ADR list

| ID | Decision | Status | Service | Related PRDs |
|---|---|---|---|---|
| ADR-0001 | [Edge and cloud responsibility split](adr-0001-edge-cloud-boundary.md) | Accepted | [All services](../services/README.md) | PRD-01 through PRD-07 |
| ADR-0002 | [Edge collection and pre-filter engine](adr-0002-edge-collector.md) | Accepted (default) | [Filtering](../services/edge/filtering.md) | PRD-01 |
| ADR-0003 | [Edge SLM local inference and constrained output](adr-0003-edge-slm-runtime.md) | Accepted (constraint); model undecided | [Summarization](../services/edge/summarization.md) | PRD-02 |
| ADR-0004 | [Secure messaging from edge to cloud](adr-0004-secure-transport.md) | Accepted (MVP: MQTT) | [Transport](../services/edge/transport.md) | PRD-03 |
| ADR-0005 | [Cloud knowledge ingestion and vector storage](adr-0005-knowledge-platform.md) | Accepted (Milvus/bge-m3/MarkItDown MVP) | [Knowledge ingestion](../services/cloud/knowledge.md) | PRD-04 |
| ADR-0006 | [Metadata filter combined with vector retrieval](adr-0006-hybrid-retrieval.md) | Accepted (policy); fallback undecided | [Retrieval](../services/cloud/retrieval.md) | PRD-05 |
| ADR-0007 | [RAG orchestration and inference model](adr-0007-rag-platform.md) | Pending | [RAG](../services/cloud/rag.md) | PRD-06 |
| ADR-0008 | [Summary-quality feedback and prompt governance](adr-0008-feedback-governance.md) | Accepted (human review, no automatic distribution) | [Feedback](../services/cloud/feedback.md) | PRD-07 |
| ADR-0009 | [Edge event schema and data minimization](adr-0009-edge-event-contract.md) | Accepted (MVP) | [shared](../services/shared.md) | PRD-02, PRD-03, PRD-05 |
| ADR-0010 | [Manage code and docs at service granularity](adr-0010-service-granularity.md) | Accepted | [All services](../services/README.md) | PRD-01 through PRD-07 |

## Status meanings

- **Accepted**: the architecture direction or constraint is already set by the requirements or the technical design, and implementation can follow it.
- **Pending**: candidates exist, or a key runtime parameter is unset. The decision must be filled in before the corresponding production implementation starts.
- **Accepted (default)** means the documented recommendation is the default. Switching requires an explicit request and an update to the ADR.

## Decision rules

Each ADR describes context, the decision, alternatives, consequences, and open questions. A pending ADR does not mean every candidate has been validated. After a choice is made, update the status, rationale, date, and consequences. Do not overwrite the historical conclusion.
