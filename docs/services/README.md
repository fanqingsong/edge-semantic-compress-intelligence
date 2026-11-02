# Service catalog

The edge application is [`services/edge`](../../services/edge) and the cloud application is [`services/cloud`](../../services/cloud). Each business module owns only its own code. Process entry points assemble modules and do not place another module's implementation in the same package. The contract shared by the two applications lives in [`libs/shared`](../../libs/shared). This granularity rule is [ADR-0010](../adr/adr-0010-service-granularity.md).

Requirements and acceptance criteria remain in the [PRD index](../prds/README.md). Technology choices and constraints remain in the [ADR index](../adr/README.md).

## Edge

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Filtering | [`services/edge/src/edge/filtering`](../../services/edge/src/edge/filtering) | Called by the edge agent | [Filtering](edge/filtering.md) |
| Summarization | [`services/edge/src/edge/summarization`](../../services/edge/src/edge/summarization) | Called by the edge agent | [Summarization](edge/summarization.md) |
| Transport | [`services/edge/src/edge/transport`](../../services/edge/src/edge/transport) | Called by the edge agent | [Transport](edge/transport.md) |
| edge agent | [`services/edge/src/edge/agent`](../../services/edge/src/edge/agent) | Process `edge-log-agent` | [edge agent](edge/agent.md) |

Fluent Bit collects logs. Its configuration is in [`deploy/fluent-bit`](../../deploy/fluent-bit). It is not one of these four Python services.

## Cloud

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Knowledge ingestion | [`services/cloud/src/cloud/knowledge`](../../services/cloud/src/cloud/knowledge) | Process `knowledge-ingest` | [Knowledge ingestion](cloud/knowledge.md) |
| Retrieval | [`services/cloud/src/cloud/retrieval`](../../services/cloud/src/cloud/retrieval) | Called by knowledge ingestion and the cloud agent | [Retrieval](cloud/retrieval.md) |
| RAG | [`services/cloud/src/cloud/rag`](../../services/cloud/src/cloud/rag) | Called by the cloud agent | [RAG](cloud/rag.md) |
| Feedback | [`services/cloud/src/cloud/feedback`](../../services/cloud/src/cloud/feedback) | Process `prompt-feedback`; online observation is called by the cloud agent | [Feedback](cloud/feedback.md) |
| cloud agent | [`services/cloud/src/cloud/agent`](../../services/cloud/src/cloud/agent) | Process `cloud-rag-agent` | [cloud agent](cloud/agent.md) |

## Dependency direction

- `libs/shared` does not depend on any business module.
- Summarization reads the log records produced by filtering. Transport does not depend on filtering or summarization.
- The edge agent assembles filtering, summarization, and transport.
- Knowledge ingestion depends only on the vector-write interface of retrieval.
- RAG uses the `RetrievedCase` type produced by retrieval.
- Feedback reads the analysis result from RAG.
- The cloud agent assembles retrieval, RAG, and feedback observation, and it owns MQTT consumption.
