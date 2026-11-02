# Transport

Code: [`services/edge/src/edge/transport`](../../../services/edge/src/edge/transport)

Related: [PRD-03](../../prds/prd-03-secure-transport.md), [ADR-0004](../../adr/adr-0004-secure-transport.md)

## Responsibilities

Encode `EdgeEvent` as MessagePack and publish it at QoS 1 to the default topic `edge/events`. The event is written to the SQLite outbox before it is sent, and the record is deleted only after the broker acknowledges the publish. That acknowledgement means the broker accepted the message. It does not mean cloud-side business processing has finished.

While disconnected, events stay local and are retried after the connection returns. The outbox defaults to a 100 MiB limit. At the limit, new events are rejected and old records are not overwritten. The [edge agent](agent.md) returns HTTP 507 in that case.

This service does not parse logs and does not call the summarization model. mTLS and topic ACLs are enforced by Mosquitto: the `edge-agent` certificate may only publish to `edge/events`.
