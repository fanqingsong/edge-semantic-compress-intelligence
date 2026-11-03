# Local development

This page explains how to test and start each service. Service responsibilities are in the [service catalog](services/README.md). The project overview is in the [README](../README.md).

Python 3.11 or newer is required. The edge and cloud agents import LangGraph, so install `langgraph>=1,<2` before running tests. Tests that do not depend on external services can then be run directly:

```bash
PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/mqtt-kafka-bridge/src:services/knowledge-ingest/src:libs/cloud/src:libs/shared/src python3 -m unittest discover -s tests -v
```

Agent orchestration imports LangGraph, so install it before running the agent tests. When real services are required, install the optional dependencies and generate local development certificates first:

```bash
python3 -m pip install 'langgraph>=1,<2' 'pymilvus>=2.4,<3' 'msgpack>=1.0' 'paho-mqtt>=2.0,<3' 'markitdown>=0.1.3,<0.2'
bash scripts/generate-dev-mqtt-certs.sh
```

## edge agent

The [edge agent](services/edge/agent.md) assembles [filtering](services/edge/filtering.md), [summarization](services/edge/summarization.md), and [transport](services/edge/transport.md).

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Put the SiliconFlow key in `.env` as `SILICONFLOW_API_KEY`. Compose reads that file for `SILICONFLOW_BASE_URL`, the key, and the model names. `.env` stays out of git.

Fluent Bit reads `./examples/logs/*.jsonl` and listens for syslog on UDP `5514`, then `POST`s batches to the edge agent on `8090`. The edge summarizer uses `SILICONFLOW_BASE_URL`, `EDGE_LLAMA_MODEL` (`Qwen/Qwen2-1.5B-Instruct`), and `SILICONFLOW_API_KEY`. The SQLite outbox defaults to a 100 MiB limit and rejects new messages when full.

MQTT uses mTLS on port `8883` against EMQX. Regenerate the development certificates after pulling this change so the broker certificate includes `DNS:emqx` and the bridge client certificate exists. The edge agent certificate may only publish to `edge/events`. The `mqtt-kafka-bridge` certificate may only subscribe to that topic. Anonymous and plaintext connections are not open. Development certificates are for local use only. The bridge writes the MessagePack payload to the Kafka topic `edge.events`, and the cloud agent consumes that topic. Kafka stays on the Compose network.

Integration tests for transport and collection:

```bash
RUN_MQTT_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/mqtt-kafka-bridge/src:services/knowledge-ingest/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_mqtt_integration -v
RUN_FLUENT_BIT_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/mqtt-kafka-bridge/src:services/knowledge-ingest/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_fluentbit_integration -v
```

Port backfill is taken only from an explicit port field or from log text that carries a port label.

## cloud agent

The [cloud agent](services/cloud/agent.md) consumes the Kafka topic `edge.events` and calls [retrieval](services/cloud/retrieval.md) and [RAG](services/cloud/rag.md). It starts with the edge agent through the `docker compose up` command above. Milvus depends on etcd and MinIO. The local stack runs one cloud agent replica.

The cloud agent uses the same `SILICONFLOW_BASE_URL` and `SILICONFLOW_API_KEY`. Embedding uses `CLOUD_EMBEDDING_MODEL` (`BAAI/bge-m3`). Analysis uses `CLOUD_ANALYSIS_MODEL` (`Qwen/Qwen2.5-72B-Instruct`).

Integration test for the retrieval adapter:

```bash
RUN_MILVUS_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/mqtt-kafka-bridge/src:services/knowledge-ingest/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_milvus_integration -v
```

The integration test uses a temporary SQLite database and a unique Milvus collection, and it cleans them up when it finishes.

## Knowledge ingestion

[Knowledge ingestion](services/cloud/knowledge.md) does not stay up with the main path. Put Markdown, TXT, JSONL, PDF, DOCX, PPTX, or HTML files in `examples/knowledge/sources`, then run:

```bash
docker compose --profile tools run --rm knowledge-ingest
```

Documents must contain explicit `Summary` and `Resolution` sections. Missing fields fail the import. The model does not fill in facts.

Stop the local stack:

```bash
docker compose stop
```
