# ADR-0011: Clustered MQTT ingress and a cloud-side Kafka bridge

- Status: Accepted
- Date: 2026-11-02
- Related PRD: PRD-03
- Extends: [ADR-0004](adr-0004-secure-transport.md)
- Code: [Transport](../services/edge/transport.md). Cloud consumption is in the [cloud agent](../services/cloud/agent.md).

## Context

ADR-0004 fixes the edge-to-cloud contract: MQTT v5, QoS 1, MessagePack, a SQLite outbox, mTLS, and idempotent handling by `event_id`. The previous local runtime was a single Mosquitto container. That broker matches a weak network and a small number of publishers, and it does not provide a cluster.

More edge devices need a broker that can add nodes. Cloud analysis needs more than one consumer. Putting Kafka on the device would drop the weak-network behavior that ADR-0004 chose MQTT for. The two roles stay separate: MQTT at the edge, Kafka only after the message has reached the cloud.

## Decision

- The edge still publishes MQTT v5 to the ingress. The broker changes from a single Mosquitto instance to a clusterable MQTT broker. The selected broker is EMQX.
- Keep the ADR-0004 delivery rules. That includes mTLS, mapping the certificate CN to an identity, the `edge/events` publish and subscribe ACL, QoS 1, the local SQLite outbox, and idempotency by `event_id`.
- Edge devices do not connect to Kafka.
- On the cloud, bridge MQTT into Kafka so cloud consumers can run in parallel.
- Delivery stays at-least-once. A successful Kafka consume does not allow the edge to delete its outbox record. The outbox record is deleted only after the MQTT PUBACK. Cloud deduplication stays by `event_id`.
- Local Compose runs one EMQX 5.9 node. The `mqtt-kafka-bridge` process is the cloud-side bridge: it subscribes to `edge/events` and produces the original MessagePack payload to the Kafka topic `edge.events`. It acknowledges the MQTT message only after Kafka acknowledges the produce. A multi-node EMQX cluster is a later deployment step and needs the EMQX cluster license.

## Consequences

- Edge clients keep the MQTT v5 client, the outbox, and the certificate identity. Scaling the ingress is a broker deployment change, not a device-protocol change.
- Cloud consumption can fan out through Kafka. Consumers must still tolerate duplicates and must not treat a Kafka acknowledgement as a substitute for the MQTT PUBACK that releases the edge outbox.
- Local development uses one EMQX node, one Kafka broker, and one bridge process. Cloud analysis still runs as one consumer because the SQLite stores are not safe for concurrent replicas.

## Alternatives

- Connect edge devices directly to Kafka. Rejected. Kafka clients do not fit the weak network or the resource limits of the edge device, which is why ADR-0004 kept MQTT on the device.
- Keep a single Mosquitto instance. Rejected for the target deployment. It does not provide cluster scaling.
