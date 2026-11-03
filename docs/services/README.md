# Service catalog

The edge application is [`services/edge-agent`](../../services/edge-agent). The cloud processes are [`services/cloud-agent`](../../services/cloud-agent), [`services/admin`](../../services/admin), [`services/mqtt-kafka-bridge`](../../services/mqtt-kafka-bridge), and [`services/knowledge-ingest`](../../services/knowledge-ingest). Each business module owns only its own code. Process entry points assemble modules and do not place another module's implementation in the same package. Retrieval and RAG live in [`libs/cloud`](../../libs/cloud). The contract shared by the applications lives in [`libs/shared`](../../libs/shared). This granularity rule is [ADR-0010](../adr/adr-0010-service-granularity.md).

Requirements and acceptance criteria remain in the [PRD index](../prds/README.md). Technology choices and constraints remain in the [ADR index](../adr/README.md).

## Edge

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Filtering | [`services/edge-agent/src/edge/filtering`](../../services/edge-agent/src/edge/filtering) | Called by the edge agent | [Filtering](edge/filtering.md) |
| Summarization | [`services/edge-agent/src/edge/summarization`](../../services/edge-agent/src/edge/summarization) | Called by the edge agent | [Summarization](edge/summarization.md) |
| Transport | [`services/edge-agent/src/edge/transport`](../../services/edge-agent/src/edge/transport) | Called by the edge agent | [Transport](edge/transport.md) |
| edge agent | [`services/edge-agent/src/edge/agent`](../../services/edge-agent/src/edge/agent) | Process `edge-log-agent` | [edge agent](edge/agent.md) |

Fluent Bit collects logs and posts them in time-based batches. That path is [Log collection](edge/collection.md). Configuration is in [`deploy/fluent-bit`](../../deploy/fluent-bit). It is not one of these Python services.

## Cloud

| Service | Code | How it runs | Notes |
|---|---|---|---|
| Knowledge ingestion | [`services/knowledge-ingest/src/cloud/knowledge`](../../services/knowledge-ingest/src/cloud/knowledge) | Process `knowledge-ingest` | [Knowledge ingestion](cloud/knowledge.md) |
| Retrieval | [`libs/cloud/src/cloud/retrieval`](../../libs/cloud/src/cloud/retrieval) | Called by knowledge ingestion and the cloud agent | [Retrieval](cloud/retrieval.md) |
| RAG | [`libs/cloud/src/cloud/rag`](../../libs/cloud/src/cloud/rag) | Called by the cloud agent | [RAG](cloud/rag.md) |
| cloud agent | [`services/cloud-agent/src/cloud/agent`](../../services/cloud-agent/src/cloud/agent) | Process `cloud-rag-agent` | [cloud agent](cloud/agent.md) |
| Admin | [`services/admin/src/cloud/admin`](../../services/admin/src/cloud/admin) | Process `cloud-admin` | [Admin](cloud/admin.md) |
| MQTT-to-Kafka bridge | [`services/mqtt-kafka-bridge/src/bridge`](../../services/mqtt-kafka-bridge/src/bridge) | Process `mqtt-kafka-bridge` | [MQTT-to-Kafka bridge](cloud/bridge.md) |

## Dependency direction

- `libs/shared` does not depend on any business module.
- Summarization reads the log records produced by filtering. Transport does not depend on filtering or summarization.
- The edge agent assembles filtering, summarization, and transport.
- `libs/cloud` holds retrieval and RAG. It does not depend on the cloud processes.
- Knowledge ingestion depends only on the vector-write interface of retrieval.
- RAG uses the `RetrievedCase` type produced by retrieval.
- The cloud agent assembles retrieval and RAG, and it owns Kafka consumption.
- The admin process reads the cloud agent's SQLite files and calls knowledge ingestion to write cases. It does not consume Kafka or publish MQTT.
- The MQTT-to-Kafka bridge owns the MQTT subscription. It does not decode events or run retrieval.
