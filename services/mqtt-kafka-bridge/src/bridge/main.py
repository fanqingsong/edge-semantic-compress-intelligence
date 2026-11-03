from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from bridge.forward import MqttKafkaForwarder
from shared.mqtt import create_mqtt_v5_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge edge MQTT events into Kafka")
    parser.add_argument(
        "--mqtt-host", default=os.environ.get("BRIDGE_MQTT_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--mqtt-port", type=int, default=int(os.environ.get("BRIDGE_MQTT_PORT", "1883"))
    )
    parser.add_argument(
        "--mqtt-topic", default=os.environ.get("BRIDGE_MQTT_TOPIC", "edge/events")
    )
    parser.add_argument(
        "--kafka-bootstrap",
        default=os.environ.get("BRIDGE_KAFKA_BOOTSTRAP", "127.0.0.1:9092"),
    )
    parser.add_argument(
        "--kafka-topic", default=os.environ.get("BRIDGE_KAFKA_TOPIC", "edge.events")
    )
    parser.add_argument(
        "--ready-file", default=os.environ.get("BRIDGE_READY_FILE", "/tmp/ready")
    )
    return parser


class KafkaPayloadProducer:
    def __init__(self, bootstrap: str) -> None:
        from kafka import KafkaProducer

        self._producer = KafkaProducer(
            bootstrap_servers=[server.strip() for server in bootstrap.split(",") if server.strip()],
            acks="all",
            retries=5,
            linger_ms=0,
        )

    def send_and_wait(self, topic: str, payload: bytes) -> None:
        self._producer.send(topic, value=payload).get(timeout=10)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()
    ready_file = Path(args.ready_file)
    ready_file.unlink(missing_ok=True)

    forwarder = MqttKafkaForwarder(KafkaPayloadProducer(args.kafka_bootstrap), args.kafka_topic)
    client_id = os.environ.get("BRIDGE_MQTT_CLIENT_ID", "mqtt-kafka-bridge")
    client = create_mqtt_v5_client(client_id)
    client.username_pw_set(os.environ.get("BRIDGE_MQTT_USERNAME", client_id))
    client.manual_ack_set(True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(mqtt_client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code != 0:
            logging.error("MQTT connect failed: %s", reason_code)
            return
        result, _ = mqtt_client.subscribe(args.mqtt_topic, qos=1)
        if result != 0:
            logging.error("MQTT subscribe failed: %s", result)

    def on_subscribe(mqtt_client, userdata, mid, reason_codes, properties=None) -> None:
        ready_file.write_text("ready\n")
        logging.info("subscribed to %s", args.mqtt_topic)

    def on_message(mqtt_client, userdata, message) -> None:
        forwarded = forwarder.forward(mqtt_client, message.mid, message.qos, message.payload)
        if not forwarded:
            logging.warning("left MQTT message %s unacked", message.mid)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    import paho.mqtt.client as mqtt

    properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 86400
    logging.info("bridging %s to Kafka topic %s", args.mqtt_topic, args.kafka_topic)
    try:
        client.connect_async(
            args.mqtt_host,
            args.mqtt_port,
            keepalive=30,
            clean_start=False,
            properties=properties,
        )
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
