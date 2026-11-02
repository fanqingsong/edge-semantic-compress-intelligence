# ADR-0001: Edge and cloud responsibility split

- Status: Accepted
- Date: 2026-11-01
- Related PRDs: PRD-01, PRD-02, PRD-03, PRD-04, PRD-05, PRD-06, PRD-07
- Code: [service catalog](../services/README.md)

## Context

The system must process logs on the edge, where resources are limited and the network is unstable, while relying on the cloud for higher-precision knowledge retrieval and reasoning. If the edge also embeds vectors, or if the cloud is bound to an edge model version, the device carries extra load and the components become coupled.

## Decision

- The edge owns log collection, rule pre-filtering, local SLM structured distillation, entity validation, and secure transport.
- The cloud owns knowledge parsing and embedding, vector storage, hybrid retrieval, RAG reasoning, and summary-quality feedback.
- The edge does not run an embedding model. The cloud interface is bounded by a stable data contract and does not depend on the specific edge SLM version.
- Edge pre-filtering stays rule-only and does not call AI.

## Consequences

- The structured message schema from edge to cloud is the core contract across the deployment boundary. It needs versioning and a compatibility policy.
- The edge SLM and the cloud embedding model and LLM can be upgraded independently. A contract change still needs a compatibility test.
- The cloud can use a larger model on its own. While offline, the edge depends on local collection and buffering.

## Alternatives

- Run embeddings on the edge and complete retrieval there. Rejected because of resource cost and coupled responsibilities.
- Let the cloud depend directly on the edge model runtime or model version. Rejected because it blocks independent upgrades.
