# MQTT-to-Kafka bridge

Code: [`services/mqtt-kafka-bridge/src/bridge`](../../../services/mqtt-kafka-bridge/src/bridge)

Process: `mqtt-kafka-bridge`. The Compose service name is `mqtt-kafka-bridge`.

Related: [PRD-03](../../prds/prd-03-secure-transport.md), [ADR-0004](../../adr/adr-0004-secure-transport.md), [ADR-0011](../../adr/adr-0011-clustered-mqtt-kafka-bridge.md), [Transport](../edge/transport.md), [cloud agent](agent.md)

## Responsibilities

This process is the cloud-side handoff from MQTT to Kafka. Edge devices publish MQTT because a Kafka client does not fit a weak network or the device. Cloud analysis needs a topic that more than one consumer can read, so Kafka starts only after the message has reached the cloud. Edge devices do not connect to Kafka. The [cloud agent](agent.md) does not connect to MQTT.

The bridge does three things:

1. Connect to EMQX as MQTT username `mqtt-kafka-bridge` and subscribe to `edge/events` at QoS 1. The username ACL allows that subscription and denies every other action.
2. Produce the original MessagePack payload, unchanged, to the Kafka topic `edge.events`. The bridge does not decode the event, does not run retrieval, and does not call a model.
3. Acknowledge the MQTT message only after Kafka acknowledges the produce (`acks=all`). A produce or ack failure leaves the MQTT message unacknowledged. The edge [transport](../edge/transport.md) outbox deletes its record only after the MQTT PUBACK, so a Kafka acknowledgement is not a substitute for that PUBACK.

Delivery stays at-least-once. Cloud deduplication stays by `event_id` in the cloud agent. The MQTT session uses `clean_start=false` and a session expiry of 86400 seconds, so a restart can resume the subscription. The process writes `/tmp/ready` after the subscription succeeds. Compose uses that file as the health check.

Local Compose runs one EMQX 5.9 node, one Kafka broker, and one bridge process. A multi-node EMQX cluster is a later deployment step.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BRIDGE_MQTT_HOST` | `127.0.0.1` | EMQX host. Compose sets `emqx`. |
| `BRIDGE_MQTT_PORT` | `1883` | Plaintext MQTT port. |
| `BRIDGE_MQTT_TOPIC` | `edge/events` | Subscription topic. |
| `BRIDGE_MQTT_USERNAME` | `mqtt-kafka-bridge` | MQTT username used for the topic ACL. |
| `BRIDGE_MQTT_CLIENT_ID` | `mqtt-kafka-bridge` | MQTT client id. |
| `BRIDGE_KAFKA_BOOTSTRAP` | `127.0.0.1:9092` | Kafka bootstrap servers. Compose sets `kafka:9092`. |
| `BRIDGE_KAFKA_TOPIC` | `edge.events` | Kafka topic that receives the original payload. |
| `BRIDGE_READY_FILE` | `/tmp/ready` | File written after a successful subscribe. |
