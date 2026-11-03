# shared

Code: [`libs/shared/src/shared`](../../libs/shared/src/shared)

`shared` holds cross-service contracts. It does not contain filtering, summarization, retrieval, or analysis logic.

## Responsibilities

- `EdgeEvent` is the only business contract from the edge to the cloud. The machine-readable definition of schema `1.0` is [schemas/edge-event-v1.schema.json](../../schemas/edge-event-v1.schema.json).
- MessagePack encode and decode are used by the transport service and the cloud agent. JSON only constrains model output.
- The MQTT client factory is used by the edge agent and the MQTT-to-Kafka bridge.

## Contract

- Required: `event_id` (UUID), `schema_version`, timezone-aware ISO 8601 `timestamp`, non-empty `service`, and non-empty `summary`.
- Optional: `target_ip`, `target_port`, and `error_code`. The IP must parse. The port is an integer from 1 to 65535.
- Unknown fields are rejected. An event does not contain the raw log.

The decision is [ADR-0009](../adr/adr-0009-edge-event-contract.md). Summarization produces this contract, transport delivers it, and retrieval and RAG consume it.
