# ADR-0006: Metadata filter combined with vector retrieval

- Status: Accepted (strict filter for the MVP)
- Date: 2026-11-01
- Related PRD: PRD-05
- Code: [Retrieval](../services/cloud/retrieval.md)

## Context

Semantic search alone can recall cases for a different target entity. Entity filtering alone cannot rank by the fault description. The cloud needs both the entities in the edge JSON and the summary.

## Decision

- Retrieval must combine an exact `target_ip` metadata filter with vector similarity search on `summary`.
- Return the Top-5 cases to the RAG analysis module.
- On the agreed labeled query set, the Top-5 hit rate for relevant cases is at least 85%.
- Vector-only search does not satisfy this requirement.
- In the MVP, a missing `target_ip` or no exact match returns an empty case set. There is no vector-only fallback. Relaxing the filter later requires a new ADR.
- Check the IP again on results returned by the vector store, so a misconfigured index filter cannot leak cases across IP addresses.

## Consequences

- Knowledge ingestion must maintain metadata fields that match the retrieval request.
- A strict `target_ip` filter may exclude the same kind of fault on a different host. The MVP empty-result behavior prefers avoiding cross-host false recall.
- Retrieval evaluation must cover cases with an IP, without an IP, with an exact match, and with no match.

## Follow-up evaluation

- Whether a controlled relaxation based on service or error code is needed, and how to show that it does not leak across tenants or hosts.
- How to handle multiple IPs, IPv6, address normalization, and permission filtering.
- The relevance labels and statistics for the Top-5 hit rate.
