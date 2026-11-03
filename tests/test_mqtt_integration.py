from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from uuid import uuid4

from cloud.agent.consumer import (
    MqttEventConsumer,
    SQLiteProcessedEventStore,
)
from shared.contract import EdgeEvent
from edge.agent.runtime import EdgeRuntime
from edge.filtering import RuleFilter
from cloud.rag import (
    RagService,
    RetrievedCase,
)
from edge.summarization import SummaryPipeline
from tests.standins import FixedAnalysisModel, LogBatchSummarizer
from shared.codec import MessagePackCodec
from shared.mqtt import create_mqtt_v5_client
from edge.transport import (
    ReliableMqttTransport,
    SQLiteOutbox,
)


@unittest.skipUnless(
    os.environ.get("RUN_MQTT_INTEGRATION") == "1",
    "set RUN_MQTT_INTEGRATION=1 to run against a local MQTT broker",
)
class LocalMqttIntegrationTests(unittest.TestCase):
    def test_bridge_username_cannot_publish_to_edge_topic(self) -> None:
        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        topic = "edge/events"
        client = create_mqtt_v5_client(f"acl-negative-test-{uuid4().hex[:8]}")
        client.username_pw_set("mqtt-kafka-bridge")
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
            self.assertTrue(connected.wait(5), "MQTT connection timed out")
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
        port = int(os.environ.get("MQTT_PORT", "1883"))
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

            rag_service = RagService(EmptyRetriever(), FixedAnalysisModel())
            consumer = MqttEventConsumer(
                topic,
                MessagePackCodec(),
                store,
                lambda event: analyses.append(rag_service.analyze(event)),
            )
            subscriber = create_mqtt_v5_client(f"edge-test-sub-{uuid4().hex[:8]}")
            subscriber.username_pw_set("mqtt-kafka-bridge")
            consumer.bind(subscriber)
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
            publisher.username_pw_set("edge-agent")
            publisher.on_connect = lambda *args: publisher_connected.set()
            edge_runtime = EdgeRuntime(
                RuleFilter(),
                SummaryPipeline(LogBatchSummarizer()),
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
                self.assertEqual(
                    analyses[0].answer.root_cause, "Likely connection saturation"
                )
            finally:
                publisher.disconnect()
                publisher.loop_stop()
                subscriber.disconnect()
                subscriber.loop_stop()
                outbox.close()
                store.close()


if __name__ == "__main__":
    unittest.main()