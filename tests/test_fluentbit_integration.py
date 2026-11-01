from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from uuid import uuid4

from edge_semantic_compress_intelligence.shared.codec import MessagePackCodec
from edge_semantic_compress_intelligence.shared.mqtt import (
    configure_mtls,
    create_mqtt_v5_client,
)


@unittest.skipUnless(
    os.environ.get("RUN_FLUENT_BIT_INTEGRATION") == "1",
    "set RUN_FLUENT_BIT_INTEGRATION=1 with the compose stack running",
)
class FluentBitIntegrationTests(unittest.TestCase):
    def test_syslog_is_normalized_and_forwarded_as_edge_event(self) -> None:
        mqtt_host = os.environ.get("MQTT_HOST", "127.0.0.1")
        mqtt_port = int(os.environ.get("MQTT_PORT", "8883"))
        syslog_host = os.environ.get("SYSLOG_HOST", "127.0.0.1")
        syslog_port = int(os.environ.get("SYSLOG_PORT", "5514"))
        topic = os.environ.get("EDGE_MQTT_TOPIC", "edge/events")
        subscribed = threading.Event()
        received = threading.Event()
        events = []

        client = create_mqtt_v5_client(f"fluentbit-test-{uuid4().hex[:8]}")

        def on_connect(
            mqtt_client: Any,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            if reason_code == 0:
                mqtt_client.subscribe(topic, qos=1)

        def on_subscribe(*args: Any) -> None:
            subscribed.set()

        def on_message(mqtt_client: Any, userdata: Any, message: Any) -> None:
            events.append(MessagePackCodec().decode(message.payload))
            received.set()

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        cert_dir = Path(__file__).resolve().parents[1] / "deploy" / "mosquitto" / "certs"
        configure_mtls(
            client,
            ca_file=os.environ.get("MQTT_CA_FILE", str(cert_dir / "ca.crt")),
            certificate_file=os.environ.get(
                "MQTT_CERT_FILE", str(cert_dir / "cloud-agent.crt")
            ),
            key_file=os.environ.get("MQTT_KEY_FILE", str(cert_dir / "cloud-agent.key")),
        )
        try:
            client.connect(mqtt_host, mqtt_port, keepalive=15)
            client.loop_start()
            self.assertTrue(subscribed.wait(5), "MQTT subscribe timed out")

            syslog_message = (
                "<14>1 2026-11-01T10:30:00Z host payments 123 ID47 - "
                "database timeout 192.0.2.10 port=5432 ERR-503"
            )
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(syslog_message.encode("utf-8"), (syslog_host, syslog_port))

            self.assertTrue(received.wait(10), "Fluent Bit did not forward Syslog event")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].service, "payments")
            self.assertEqual(events[0].target_ip, "192.0.2.10")
            self.assertEqual(events[0].target_port, 5432)
            self.assertEqual(events[0].error_code, "ERR-503")
        finally:
            client.disconnect()
            client.loop_stop()

    def test_jsonl_file_is_forwarded_by_tail_input(self) -> None:
        mqtt_host = os.environ.get("MQTT_HOST", "127.0.0.1")
        mqtt_port = int(os.environ.get("MQTT_PORT", "8883"))
        topic = os.environ.get("EDGE_MQTT_TOPIC", "edge/events")
        subscribed = threading.Event()
        received = threading.Event()
        events = []

        client = create_mqtt_v5_client(f"fluentbit-file-test-{uuid4().hex[:8]}")
        client.on_connect = lambda mqtt_client, userdata, flags, reason, properties: (
            mqtt_client.subscribe(topic, qos=1) if reason == 0 else None
        )
        client.on_subscribe = lambda *args: subscribed.set()
        client.on_message = lambda mqtt_client, userdata, message: (
            events.append(MessagePackCodec().decode(message.payload)),
            received.set(),
        )
        cert_dir = Path(__file__).resolve().parents[1] / "deploy" / "mosquitto" / "certs"
        configure_mtls(
            client,
            ca_file=os.environ.get("MQTT_CA_FILE", str(cert_dir / "ca.crt")),
            certificate_file=os.environ.get(
                "MQTT_CERT_FILE", str(cert_dir / "cloud-agent.crt")
            ),
            key_file=os.environ.get("MQTT_KEY_FILE", str(cert_dir / "cloud-agent.key")),
        )

        log_directory = Path(__file__).resolve().parents[1] / "examples" / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        log_path: Path | None = None
        try:
            client.connect(mqtt_host, mqtt_port, keepalive=15)
            client.loop_start()
            self.assertTrue(subscribed.wait(5), "MQTT subscribe timed out")

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".jsonl",
                prefix=f"integration-{uuid4().hex}-",
                dir=log_directory,
                delete=False,
            ) as log_file:
                log_file.write(
                    json.dumps(
                        {
                            "timestamp": "2026-11-01T10:30:00Z",
                            "service": "inventory",
                            "status_code": 500,
                            "message": "file tail timeout 198.51.100.20 port=8080 ERR-812",
                        }
                    )
                    + "\n"
                )
                log_path = Path(log_file.name)

            self.assertTrue(received.wait(10), "Fluent Bit tail did not forward JSONL")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].service, "inventory")
            self.assertEqual(events[0].target_ip, "198.51.100.20")
            self.assertEqual(events[0].target_port, 8080)
            self.assertEqual(events[0].error_code, "ERR-812")
        finally:
            client.disconnect()
            client.loop_stop()
            if log_path is not None:
                log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()