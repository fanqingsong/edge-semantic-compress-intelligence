# Retrieval

Code: [`libs/cloud/src/cloud/retrieval`](../../../libs/cloud/src/cloud/retrieval)

Related: [PRD-05](../../prds/prd-05-hybrid-retrieval.md), [ADR-0006](../../adr/adr-0006-hybrid-retrieval.md)

## Responsibilities

Provide hybrid retrieval and the vector-store adapter. This service has no process of its own. [Knowledge ingestion](knowledge.md) uses it to write vectors. The [cloud agent](agent.md) uses it to retrieve by event.

The retrieval result type `RetrievedCase` is defined here. [RAG](rag.md) depends on that type. Retrieval does not depend on RAG.

Online retrieval rules:

- Use an exact `target_ip` filter and vector similarity on `summary` together.
- `top_k` is fixed at 5.
- When `target_ip` is missing, or there is no exact IP match, return an empty case set. Do not fall back to vector-only search.
- Compare the IP again after the vector store returns results, so a misconfigured index cannot recall cases from another host.

The Milvus collection adapter and the bge-m3 HTTP client belong to the retrieval service.
