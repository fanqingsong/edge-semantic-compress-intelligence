# ADR-0004: Secure messaging from edge to cloud

- Status: Accepted (MVP: MQTT v5 + MessagePack + SQLite outbox)
- Date: 2026-11-01
- The clustered MQTT broker and the cloud-side Kafka bridge are in [ADR-0011](adr-0011-clustered-mqtt-kafka-bridge.md). This record keeps the original MVP conclusion.
- Related PRD: PRD-03
- Code: [Transport](../services/edge/transport.md). Cloud consumption is in the [cloud agent](../services/cloud/agent.md).

## Context

The edge must send structured summaries over an unstable network. The system requires mTLS and local disk buffering. The technical design proposes MQTT v5 and Kafka, and specifies MessagePack serialization.

## Current constraints

- Transport must use mutual TLS.
- Structured messages travel on the wire as MessagePack. The boundary between model-generated JSON and the wire encoding must be explicit.
- On a weak network, buffer on local disk and retry after the connection returns.
- Message acknowledgement, retry, and idempotent handling must be verifiable.

## Decision

- The MVP uses MQTT v5. Structured events are published at QoS 1 and encoded as MessagePack.
- Use a persistent SQLite outbox. The default capacity is 100 MiB and is configurable. At the limit, new enqueue attempts are rejected with an explicit error. Old events are not dropped silently and are not overwritten.
- Delete a local outbox record only after the broker acknowledges the publish. That acknowledgement does not mean the cloud has finished business processing. The cloud still consumes idempotently by `event_id`.
- The cloud consumer uses MQTT manual ACK. It ACKs only after business processing succeeds and `event_id` is persisted. A duplicate with the same ID and the same content is ACKed immediately and is not passed to the processor again. The same ID with different content is not ACKed.
- This mode provides at-least-once delivery. It does not promise exactly-once. The business processor must be idempotent by `event_id`, because the process may exit after business success and before the deduplication record is persisted.
- The MQTT broker listens on TLS 8883, requires a client certificate issued by the CA, and maps the certificate CN to an ACL identity.
- The ACL allows only `edge-agent` to publish to `edge/events` and `cloud-agent` to subscribe to that topic. A separate `healthcheck` identity may only read `$SYS/broker/uptime`.
- Edge and cloud clients and the broker are all configured for mTLS. Local development uses the self-signed certificates from `scripts/generate-dev-mqtt-certs.sh`. The certificate directory is gitignored.
- Production must use an organizational CA and per-device certificates, with rotation, revocation, and controlled key storage. The development CA and keys must not be reused.

## Follow-up configuration

- Define the target device disk quota, the maximum offline duration, and the alert and response when the outbox is full.
- Configure an organizational CA, certificate rotation and revocation, and the cloud consumption acknowledgement policy for the production MQTT broker.
- Evaluate encryption at rest for the local outbox. Today only database file permissions are restricted. Disk encryption is not provided.
- The later Kafka transport evaluation is recorded in [ADR-0011](adr-0011-clustered-mqtt-kafka-bridge.md). The edge stays on MQTT. Kafka is a cloud-side bridge, not an edge client.

## Consequences

- The protocol choice affects edge resource use, cloud ingress, deployment complexity, and the delivery semantics that can be achieved.
- Before production, run end-to-end tests for disconnection, process restart, duplicate delivery, and certificate expiry.

## Alternatives

- MQTT v5: closer to weak-network and edge-device conditions.
- Kafka: a better fit when Kafka infrastructure already exists and throughput requirements are higher.
