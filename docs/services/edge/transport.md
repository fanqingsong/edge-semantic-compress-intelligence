# Transport

Code: [`services/edge-agent/src/edge/transport`](../../../services/edge-agent/src/edge/transport)

Related: [PRD-03](../../prds/prd-03-secure-transport.md), [ADR-0004](../../adr/adr-0004-secure-transport.md), [ADR-0011](../../adr/adr-0011-clustered-mqtt-kafka-bridge.md)

## Responsibilities

Encode `EdgeEvent` as MessagePack and publish it at QoS 1 to the default topic `edge/events`. The event is written to the SQLite outbox before it is sent, and the record is deleted only after the broker acknowledges the publish. That acknowledgement means the broker accepted the message. It does not mean cloud-side business processing has finished.

While disconnected, events stay local and are retried after the connection returns. The outbox defaults to a 100 MiB limit. At the limit, new events are rejected and old records are not overwritten. The [edge agent](agent.md) returns HTTP 507 in that case.

This service does not parse logs and does not call the summarization model. EMQX enforces topic ACLs by MQTT username: `edge-agent` may only publish to `edge/events`. The cloud-side bridge username may only subscribe to that topic. The broker listener is plaintext MQTT on port `1883`.
