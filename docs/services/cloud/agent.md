# cloud agent

Code: [`services/cloud-agent/src/cloud/agent`](../../../services/cloud-agent/src/cloud/agent)

Process: `cloud-rag-agent`. The Compose service name is `cloud-agent`.

## Responsibilities

This is the long-running process on the cloud online path. It reads the Kafka topic `edge.events` and runs the following steps as a LangGraph state graph. The Kafka offset commit stays outside the graph. The external behavior is unchanged:

1. [Retrieval](retrieval.md)
2. [RAG](rag.md), writing the result to `analyses.sqlite3`

Consumption records live in `processed.sqlite3`. The Kafka offset is committed only after processing succeeds and both `event_id` and the payload hash are persisted. A duplicate with the same ID and the same payload is committed immediately and is not passed to the processor again. The same ID with a different payload is not committed. A decode failure or a processing failure is not committed either.

The process does not connect to MQTT. `mqtt-kafka-bridge` is the MQTT subscriber. Knowledge ingestion is not part of this process. One cloud agent replica consumes the topic, because the SQLite stores are not safe for concurrent writers.
