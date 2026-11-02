# Service catalog

The implementation is packaged by service. Each service owns only its own code. Process entry points assemble services and do not place another service's implementation in the same package. The contract shared by the edge and the cloud lives in [`shared`](shared.md). This granularity rule is [ADR-0010](../adr/adr-0010-service-granularity.md).

Requirements and acceptance criteria remain in the [PRD index](../prds/README.md). Technology choices and constraints remain in the [ADR index](../adr/README.md).

## Edge

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Filtering | [`services/edge/filtering`](../../src/edge_semantic_compress_intelligence/services/edge/filtering) | Called by the edge agent | [Filtering](edge/filtering.md) |
| Summarization | [`services/edge/summarization`](../../src/edge_semantic_compress_intelligence/services/edge/summarization) | Called by the edge agent | [Summarization](edge/summarization.md) |
| Transport | [`services/edge/transport`](../../src/edge_semantic_compress_intelligence/services/edge/transport) | Called by the edge agent | [Transport](edge/transport.md) |
| edge agent | [`services/edge/agent`](../../src/edge_semantic_compress_intelligence/services/edge/agent) | Process `edge-log-agent` | [edge agent](edge/agent.md) |

Fluent Bit collects logs. Its configuration is in [`deploy/fluent-bit`](../../deploy/fluent-bit). It is not one of these four Python services.

## Cloud

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Knowledge ingestion | [`services/cloud/knowledge`](../../src/edge_semantic_compress_intelligence/services/cloud/knowledge) | Process `knowledge-ingest` | [Knowledge ingestion](cloud/knowledge.md) |
| Retrieval | [`services/cloud/retrieval`](../../src/edge_semantic_compress_intelligence/services/cloud/retrieval) | Called by knowledge ingestion and the cloud agent | [Retrieval](cloud/retrieval.md) |
| RAG | [`services/cloud/rag`](../../src/edge_semantic_compress_intelligence/services/cloud/rag) | Called by the cloud agent | [RAG](cloud/rag.md) |
| Feedback | [`services/cloud/feedback`](../../src/edge_semantic_compress_intelligence/services/cloud/feedback) | Process `prompt-feedback`; online observation is called by the cloud agent | [Feedback](cloud/feedback.md) |
| cloud agent | [`services/cloud/agent`](../../src/edge_semantic_compress_intelligence/services/cloud/agent) | Process `cloud-rag-agent` | [cloud agent](cloud/agent.md) |

## Dependency direction

- `shared` does not depend on any service.
- Summarization reads the log records produced by filtering. Transport does not depend on filtering or summarization.
- The edge agent assembles filtering, summarization, and transport.
- Knowledge ingestion depends only on the vector-write interface of retrieval.
- RAG uses the `RetrievedCase` type produced by retrieval.
- Feedback reads the analysis result from RAG.
- The cloud agent assembles retrieval, RAG, and feedback observation, and it owns MQTT consumption.
