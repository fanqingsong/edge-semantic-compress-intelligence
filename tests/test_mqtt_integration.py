from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from uuid import uuid4

from edge_semantic_compress_intelligence.services.cloud.agent.consumer import (
    MqttEventConsumer,
    SQLiteProcessedEventStore,
)
from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.edge.agent.runtime import EdgeRuntime
from edge_semantic_compress_intelligence.services.edge.filtering import RuleFilter
from edge_semantic_compress_intelligence.services.cloud.rag import (
    DeterministicMockAnalysisModel,
    RagService,
    RetrievedCase,
)
from edge_semantic_compress_intelligence.services.edge.summarization import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)
from edge_semantic_compress_intelligence.shared.codec import MessagePackCodec
from edge_semantic_compress_intelligence.shared.mqtt import (
    configure_mtls,
    create_mqtt_v5_client,
)
from edge_semantic_compress_intelligence.services.edge.transport import (
    ReliableMqttTransport,
    SQLiteOutbox,
)


@unittest.skipUnless(
    os.environ.get("RUN_MQTT_INTEGRATION") == "1",
    "set RUN_MQTT_INTEGRATION=1 to run against a local MQTT broker",
)
class LocalMqttIntegrationTests(unittest.TestCase):
    def test_broker_rejects_connection_without_client_certificate(self) -> None:
        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "8883"))
        cert_dir = Path(__file__).resolve().parents[1] / "deploy" / "mosquitto" / "certs"
        client = create_mqtt_v5_client(f"no-cert-test-{uuid4().hex[:8]}")
        client.tls_set(ca_certs=str(cert_dir / "ca.crt"))
        rejected = threading.Event()
        connection_reason = []

        def on_connect(
            mqtt_client: Any,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            connection_reason.append(reason_code)
            if reason_code.is_failure:
                rejected.set()

        def on_disconnect(
            mqtt_client: Any,
            userdata: Any,
            disconnect_flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            rejected.set()

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        try:
            client.connect(host, port, keepalive=5)
            client.loop_start()
            self.assertTrue(rejected.wait(5), "broker did not reject the uncertified client")
            if connection_reason:
                self.assertTrue(connection_reason[0].is_failure)
        finally:
            client.disconnect()
            client.loop_stop()

    def test_cloud_certificate_cannot_publish_to_edge_topic(self) -> None:
        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "8883"))
        topic = "edge/events"
        cert_dir = Path(__file__).resolve().parents[1] / "deploy" / "mosquitto" / "certs"
        client = create_mqtt_v5_client(f"acl-negative-test-{uuid4().hex[:8]}")
        configure_mtls(
            client,
            ca_file=str(cert_dir / "ca.crt"),
            certificate_file=str(cert_dir / "cloud-agent.crt"),
            key_file=str(cert_dir / "cloud-agent.key"),
        )
        connected = threading.Event()
        publish_completed = threading.Event()
        publish_reason = []

        def on_connect(
            mqtt_client: Any,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            if reason_code == 0:
                connected.set()

        def on_publish(
            mqtt_client: Any,
            userdata: Any,
            mid: int,
            reason_code: Any,
            properties: Any,
        ) -> None:
            publish_reason.append(reason_code)
            publish_completed.set()

        client.on_connect = on_connect
        client.on_publish = on_publish
        try:
            client.connect(host, port, keepalive=5)
            client.loop_start()
            self.assertTrue(connected.wait(5), "mTLS connection timed out")
            info = client.publish(topic, b"unauthorized", qos=1)
            info.wait_for_publish(timeout=5)
            self.assertTrue(publish_completed.wait(5), "MQTT PUBACK timed out")
            self.assertTrue(publish_reason[0].is_failure)
        finally:
            client.disconnect()
            client.loop_stop()

    def test_logs_flow_from_edge_runtime_through_mqtt_to_cloud_rag(self) -> None:
        from collections.abc import Sequence

        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "8883"))
        topic = "edge/events"
        received = threading.Event()
        publisher_connected = threading.Event()
        analyses = []

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteProcessedEventStore(
                str(Path(directory) / "processed.sqlite3")
            )
            outbox = SQLiteOutbox(str(Path(directory) / "outbox.sqlite3"))

            class EmptyRetriever:
                def retrieve(self, event: EdgeEvent) -> Sequence[RetrievedCase]:
                    return ()

            rag_service = RagService(EmptyRetriever(), DeterministicMockAnalysisModel())
            consumer = MqttEventConsumer(
                topic,
                MessagePackCodec(),
                store,
                lambda event: analyses.append(rag_service.analyze(event)),
            )
            subscriber = create_mqtt_v5_client(f"edge-test-sub-{uuid4().hex[:8]}")
            consumer.bind(subscriber)
            cert_dir = Path(__file__).resolve().parents[1] / "deploy" / "mosquitto" / "certs"
            configure_mtls(
                subscriber,
                ca_file=os.environ.get("MQTT_CA_FILE", str(cert_dir / "ca.crt")),
                certificate_file=os.environ.get(
                    "MQTT_CERT_FILE", str(cert_dir / "cloud-agent.crt")
                ),
                key_file=os.environ.get("MQTT_KEY_FILE", str(cert_dir / "cloud-agent.key")),
            )
            subscribe_confirmed = threading.Event()
            original_on_message = subscriber.on_message

            def on_subscribe(*args: Any) -> None:
                subscribe_confirmed.set()

            def on_message(client: Any, userdata: Any, message: Any) -> None:
                original_on_message(client, userdata, message)
                received.set()

            subscriber.on_subscribe = on_subscribe
            subscriber.on_message = on_message
            publisher = create_mqtt_v5_client(f"edge-test-pub-{uuid4().hex[:8]}")
            configure_mtls(
                publisher,
                ca_file=os.environ.get("MQTT_CA_FILE", str(cert_dir / "ca.crt")),
                certificate_file=str(cert_dir / "edge-agent.crt"),
                key_file=str(cert_dir / "edge-agent.key"),
            )
            publisher.on_connect = lambda *args: publisher_connected.set()
            edge_runtime = EdgeRuntime(
                RuleFilter(),
                SummaryPipeline(DeterministicMockSummarizer()),
                ReliableMqttTransport(
                    publisher,
                    outbox,
                    MessagePackCodec(),
                    topic,
                ),
            )
            try:
                subscriber.connect(host, port, keepalive=15)
                subscriber.loop_start()
                self.assertTrue(subscribe_confirmed.wait(5), "MQTT subscribe timed out")

                publisher.connect(host, port, keepalive=15)
                publisher.loop_start()
                self.assertTrue(publisher_connected.wait(5), "MQTT connect timed out")
                report = edge_runtime.process_batch(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-11-01T10:30:00Z",
                                "service": "payments",
                                "status_code": 500,
                                "message": (
                                    "Database connection timeout at 192.0.2.10 "
                                    "port=5432 ERR-503"
                                ),
                            }
                        )
                    ]
                )
                self.assertTrue(received.wait(5), "consumer did not receive the event")
                self.assertEqual(report.published, 1)
                self.assertEqual(report.pending, 0)
                self.assertEqual(len(analyses), 1)
                self.assertEqual(analyses[0].event_id, report.events[0].event_id)
                self.assertEqual(report.events[0].target_ip, "192.0.2.10")
                self.assertEqual(report.events[0].target_port, 5432)
                self.assertEqual(report.events[0].error_code, "ERR-503")
                self.assertIn("Mock response", analyses[0].answer.root_cause)
            finally:
                publisher.disconnect()
                publisher.loop_stop()
                subscriber.disconnect()
                subscriber.loop_stop()
                outbox.close()
                store.close()


if __name__ == "__main__":
    unittest.main()