import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Sequence

from edge_semantic_compress_intelligence.services.cloud.agent.consumer import (
    MqttDelivery,
    MqttEventConsumer,
    SQLiteProcessedEventStore,
)
from edge_semantic_compress_intelligence.shared.contract import EdgeEvent
from edge_semantic_compress_intelligence.services.cloud.rag import (
    AnalysisAnswer,
    DeterministicMockAnalysisModel,
    RagService,
    RetrievedCase,
)
from edge_semantic_compress_intelligence.shared.codec import MessagePackCodec


@dataclass
class JsonCodec:
    def encode(self, event: EdgeEvent) -> bytes:
        return event.to_json().encode("utf-8")

    def decode(self, payload: bytes) -> EdgeEvent:
        return EdgeEvent.from_json(payload.decode("utf-8"))


@dataclass
class FakeClient:
    acks: list[tuple[int, int]] = field(default_factory=list)
    subscriptions: list[tuple[str, int]] = field(default_factory=list)
    manual_ack: bool = False
    ack_result: int = 0

    def manual_ack_set(self, enabled: bool) -> None:
        self.manual_ack = enabled

    def subscribe(self, topic: str, qos: int) -> tuple[int, int]:
        self.subscriptions.append((topic, qos))
        return 0, 1

    def ack(self, mid: int, qos: int) -> int:
        self.acks.append((mid, qos))
        return self.ack_result


@dataclass
class FakeMessage:
    mid: int
    qos: int
    payload: bytes


@dataclass(frozen=True)
class EmptyRetriever:
    def retrieve(self, event: EdgeEvent) -> Sequence[RetrievedCase]:
        return ()


def event_payload(summary: str = "Database timeout") -> bytes:
    return json.dumps(
        {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "schema_version": "1.0",
            "timestamp": "2026-11-01T10:30:00Z",
            "service": "payments",
            "summary": summary,
        }
    ).encode("utf-8")


class MqttEventConsumerTests(unittest.TestCase):
    def test_bind_enables_manual_ack_and_subscribes_at_qos_one(self) -> None:
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)
        consumer = MqttEventConsumer(
            "edge/events", JsonCodec(), store, lambda event: None
        )

        consumer.bind(client)
        client.on_connect(client, None, None, 0, None)

        self.assertTrue(client.manual_ack)
        self.assertEqual(client.subscriptions, [("edge/events", 1)])

    def test_messagepack_event_reaches_rag_before_ack(self) -> None:
        event = EdgeEvent(
            event_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp="2026-11-01T10:30:00Z",
            service="payments",
            summary="Database connection timed out",
        )
        rag_service = RagService(EmptyRetriever(), DeterministicMockAnalysisModel())
        analyses = []
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)
        consumer = MqttEventConsumer(
            "edge/events",
            MessagePackCodec(),
            store,
            lambda received: analyses.append(rag_service.analyze(received)),
        )

        result = consumer.handle_message(
            client,
            MqttDelivery(mid=22, qos=1, payload=MessagePackCodec().encode(event)),
        )

        self.assertEqual(result.disposition, "processed")
        self.assertEqual(analyses[0].event_id, event.event_id)
        self.assertIn("Mock response", analyses[0].answer.root_cause)
        self.assertEqual(client.acks, [(22, 1)])

    def test_successful_processing_is_persisted_before_ack(self) -> None:
        handled: list[str] = []
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)
        consumer = MqttEventConsumer(
            "edge/events", JsonCodec(), store, lambda event: handled.append(event.event_id)
        )

        result = consumer.handle_message(
            client, MqttDelivery(mid=12, qos=1, payload=event_payload())
        )

        self.assertEqual(result.disposition, "processed")
        self.assertEqual(len(handled), 1)
        self.assertEqual(client.acks, [(12, 1)])
        self.assertIsNotNone(store.payload_hash(handled[0]))

    def test_duplicate_payload_is_acked_without_reprocessing(self) -> None:
        handled: list[str] = []
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)
        consumer = MqttEventConsumer(
            "edge/events",
            JsonCodec(),
            store,
            lambda event: handled.append(event.event_id),
        )
        payload = event_payload()

        first = consumer.handle_message(client, MqttDelivery(1, 1, payload))
        second = consumer.handle_message(client, MqttDelivery(2, 1, payload))

        self.assertEqual(first.disposition, "processed")
        self.assertEqual(second.disposition, "duplicate")
        self.assertEqual(len(handled), 1)
        self.assertEqual(client.acks, [(1, 1), (2, 1)])

    def test_failed_handler_is_not_acked_or_recorded(self) -> None:
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)

        def fail(event: EdgeEvent) -> None:
            raise RuntimeError("temporary downstream error")

        consumer = MqttEventConsumer("edge/events", JsonCodec(), store, fail)
        payload = event_payload()
        result = consumer.handle_message(client, MqttDelivery(7, 1, payload))

        self.assertEqual(result.disposition, "processing_failed")
        self.assertEqual(client.acks, [])
        self.assertIsNone(store.payload_hash("550e8400-e29b-41d4-a716-446655440000"))

    def test_same_id_with_different_payload_is_not_acked(self) -> None:
        client = FakeClient()
        store = SQLiteProcessedEventStore(":memory:")
        self.addCleanup(store.close)
        consumer = MqttEventConsumer(
            "edge/events", JsonCodec(), store, lambda event: None
        )
        consumer.handle_message(client, MqttDelivery(1, 1, event_payload()))

        result = consumer.handle_message(
            client, MqttDelivery(2, 1, event_payload("Different content"))
        )

        self.assertEqual(result.disposition, "event_id_conflict")
        self.assertEqual(client.acks, [(1, 1)])

    def test_processed_store_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "processed.sqlite3")
            first = SQLiteProcessedEventStore(path)
            self.addCleanup(first.close)
            first.mark_processed("event-1", "payload-hash")
            restarted = SQLiteProcessedEventStore(path)
            self.addCleanup(restarted.close)

            self.assertEqual(restarted.payload_hash("event-1"), "payload-hash")


if __name__ == "__main__":
    unittest.main()