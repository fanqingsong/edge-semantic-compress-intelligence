# PRD-05: Cloud hybrid retrieval

**Original requirement:** C-02

**Service:** [Retrieval](../services/cloud/retrieval.md)

## Goal

Use the entities and semantic content of an edge summary to retrieve historical cases from the operations knowledge base that can be used for fault analysis.

## Scope

- Accept a structured edge summary.
- Apply an exact metadata filter on `target_ip` and a vector similarity search on `summary`.
- Return the ranked Top-5 relevant cases and the metadata PRD-06 needs.

## Acceptance criteria

- Retrieval runs the metadata filter and the vector search together. Vector-only retrieval is not allowed.
- On a labeled query set agreed by both sides, Top-5 hit rate for relevant cases is at least 85%.
- Returned results include a traceable knowledge-source identifier and relevance information, so they can be evaluated and diagnosed.
- In the MVP, a missing `target_ip` or no exact match returns an empty case set. Falling back to vector-only retrieval is not allowed.

## Dependencies and open decisions

- Depends on the knowledge base built by PRD-04 and on the summary contract defined by PRD-02 and the message ingress.
- Confirm whether strict exact IP filtering drops similar cases on other hosts. Define the filter-relaxation policy when there is no match.
- Define behavior for a missing `target_ip`, address normalization, multi-IP logs, and access-control filtering.
- Fix the labeling rules, test set, and statistics for the Top-5 hit rate.
