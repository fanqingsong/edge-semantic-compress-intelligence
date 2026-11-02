# cloud agent

Code: [`services/cloud/src/cloud/agent`](../../../services/cloud/src/cloud/agent)

Process: `cloud-rag-agent`. The Compose service name is `cloud-agent`.

## Responsibilities

This is the long-running process on the cloud online path. It subscribes to `edge/events`, then calls:

1. [Retrieval](retrieval.md)
2. [RAG](rag.md), writing the result to `analyses.sqlite3`
3. The observation interface of [feedback](feedback.md), writing suggestions to `feedback.sqlite3`

Consumption records live in `processed.sqlite3`. A manual ACK is sent only after processing succeeds and both `event_id` and the payload hash are persisted. A duplicate with the same ID and the same payload is ACKed immediately and is not passed to the processor again. The same ID with a different payload is not ACKed. A decode failure or a processing failure is not ACKed either.

The `cloud-agent` certificate may only subscribe to `edge/events`. Knowledge ingestion and feedback review are not part of this process.
