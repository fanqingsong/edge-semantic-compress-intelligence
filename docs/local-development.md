# Local development

This page explains how to test and start each service. Service responsibilities are in the [service catalog](services/README.md). The project overview is in the [README](../README.md).

Python 3.11 or newer is required. The edge and cloud agents import LangGraph, so install `langgraph>=1,<2` before running tests. Tests that do not depend on external services can then be run directly:

```bash
PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/knowledge-ingest/src:services/feedback-admin/src:libs/cloud/src:libs/shared/src python3 -m unittest discover -s tests -v
```

Agent orchestration imports LangGraph, so install it before running the agent tests. When real services are required, install the optional dependencies and generate local development certificates first:

```bash
python3 -m pip install 'langgraph>=1,<2' 'pymilvus>=2.4,<3' 'msgpack>=1.0' 'paho-mqtt>=2.0,<3' 'markitdown>=0.1.3,<0.2'
bash scripts/generate-dev-mqtt-certs.sh
```

## edge agent

The [edge agent](services/edge/agent.md) assembles [filtering](services/edge/filtering.md), [summarization](services/edge/summarization.md), and [transport](services/edge/transport.md).

```bash
docker compose up -d --build --wait
```

Fluent Bit reads `./examples/logs/*.jsonl` and listens for syslog on UDP `5514`, then `POST`s batches to the edge agent on `8090`. The development environment uses the mock summarizer by default. Set `EDGE_SUMMARIZER=llama_cpp` and configure `EDGE_LLAMA_URL` to call a local llama.cpp server. The SQLite outbox defaults to a 100 MiB limit and rejects new messages when full.

MQTT uses mTLS on port `8883`. The edge agent certificate may only publish to `edge/events`. The cloud agent certificate may only subscribe to that topic. Anonymous and plaintext connections are not open. Development certificates are for local use only.

Integration tests for transport and collection:

```bash
RUN_MQTT_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/knowledge-ingest/src:services/feedback-admin/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_mqtt_integration -v
RUN_FLUENT_BIT_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/knowledge-ingest/src:services/feedback-admin/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_fluentbit_integration -v
```

Port backfill is taken only from an explicit port field or from log text that carries a port label.

## cloud agent

The [cloud agent](services/cloud/agent.md) subscribes to edge events and calls [retrieval](services/cloud/retrieval.md) and [RAG](services/cloud/rag.md). It starts with the edge agent through the `docker compose up` command above. Milvus depends on etcd and MinIO.

The development environment uses a mock embedding model and analysis model by default. Switch them with `CLOUD_EMBEDDING_MODE`, `CLOUD_EMBEDDING_URL`, `CLOUD_ANALYSIS_MODE`, and `CLOUD_ANALYSIS_URL`.

Integration test for the retrieval adapter:

```bash
RUN_MILVUS_INTEGRATION=1 PYTHONPATH=services/edge-agent/src:services/cloud-agent/src:services/knowledge-ingest/src:services/feedback-admin/src:libs/cloud/src:libs/shared/src python3 -m unittest tests.test_milvus_integration -v
```

The integration test uses a temporary SQLite database and a unique Milvus collection, and it cleans them up when it finishes.

## Knowledge ingestion

[Knowledge ingestion](services/cloud/knowledge.md) does not stay up with the main path. Put Markdown, TXT, JSONL, PDF, DOCX, PPTX, or HTML files in `examples/knowledge/sources`, then run:

```bash
docker compose --profile tools run --rm knowledge-ingest
```

Documents must contain explicit `Summary` and `Resolution` sections. Missing fields fail the import. The model does not fill in facts.

## Feedback

The review CLI for [feedback](services/cloud/feedback.md) also uses the `tools` profile:

```bash
docker compose --profile tools run --rm feedback-admin
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 review <suggestion-id> --approve --reviewer <name> --note "validated against labeled cases"
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 publish <suggestion-id>
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 weekly-report
```

`publish` only records a human confirmation. It does not push remotely or replace the edge prompt automatically.

Stop the local stack:

```bash
docker compose stop
```
