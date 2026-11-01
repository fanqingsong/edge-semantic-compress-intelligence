import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edge_semantic_compress_intelligence.contracts import EdgeEvent
from edge_semantic_compress_intelligence.transport import (
    EventConflictError,
    FlushReport,
    MessagePackCodec,
    OutboxFullError,
    ReliableMqttTransport,
    SQLiteOutbox,
    configure_mtls,
    create_mqtt_v5_client,
)


@dataclass
class FakeCodec:
    def encode(self, event: EdgeEvent) -> bytes:
        return event.to_json().encode("utf-8")


@dataclass
class FakePublishInfo:
    published: bool = True
    rc: int = 0

    def wait_for_publish(self, timeout: float) -> None:
        return None

    def is_published(self) -> bool:
        return self.published


@dataclass
class FakeMqttClient:
    outcomes: list[FakePublishInfo] = field(default_factory=list)
    calls: list[tuple[str, bytes, int]] = field(default_factory=list)

    def publish(self, topic: str, payload: bytes, qos: int) -> FakePublishInfo:
        self.calls.append((topic, payload, qos))
        return self.outcomes.pop(0) if self.outcomes else FakePublishInfo()


class FakeTlsClient:
    tls_options: dict[str, Any] | None = None
    insecure: bool | None = None

    def tls_set(self, **kwargs: Any) -> None:
        self.tls_options = kwargs

    def tls_insecure_set(self, value: bool) -> None:
        self.insecure = value


def make_event() -> EdgeEvent:
    return EdgeEvent(
        event_id="550e8400-e29b-41d4-a716-446655440000",
        timestamp="2026-11-01T10:30:00Z",
        service="payments",
        summary="Database connection timed out",
    )


class SQLiteOutboxTests(unittest.TestCase):
    def test_outbox_persists_pending_messages_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "outbox.sqlite3")
            outbox = SQLiteOutbox(database)
            outbox.enqueue("event-1", "edge/events", b"payload")

            restarted = SQLiteOutbox(database)

            self.assertEqual(restarted.pending()[0].payload, b"payload")
            self.assertEqual(restarted.usage(), (1, len(b"payload") + len("edge/events")))

    def test_repeated_identical_event_is_idempotent(self) -> None:
        outbox = SQLiteOutbox(":memory:")
        self.addCleanup(outbox.close)
        outbox.enqueue("event-1", "edge/events", b"payload")
        outbox.enqueue("event-1", "edge/events", b"payload")

        self.assertEqual(outbox.usage()[0], 1)

    def test_reused_event_id_with_different_payload_is_rejected(self) -> None:
        outbox = SQLiteOutbox(":memory:")
        self.addCleanup(outbox.close)
        outbox.enqueue("event-1", "edge/events", b"payload")

        with self.assertRaises(EventConflictError):
            outbox.enqueue("event-1", "edge/events", b"different")

    def test_capacity_limit_is_enforced(self) -> None:
        outbox = SQLiteOutbox(":memory:", max_bytes=3)
        self.addCleanup(outbox.close)

        with self.assertRaises(OutboxFullError):
            outbox.enqueue("event-1", "edge/events", b"payload")


class ReliableMqttTransportTests(unittest.TestCase):
    def test_messagepack_codec_round_trip(self) -> None:
        event = make_event()

        payload = MessagePackCodec().encode(event)
        decoded = MessagePackCodec().decode(payload)

        self.assertEqual(decoded, event)

    def test_mqtt_client_factory_selects_mqtt_v5(self) -> None:
        client = create_mqtt_v5_client("edge-test-client")

        self.assertEqual(client._client_id, b"edge-test-client")
        self.assertEqual(client._protocol, 5)

    def test_acknowledged_publish_removes_message_from_outbox(self) -> None:
        client = FakeMqttClient()
        outbox = SQLiteOutbox(":memory:")
        self.addCleanup(outbox.close)
        transport = ReliableMqttTransport(client, outbox, FakeCodec(), "edge/events")

        result = transport.submit(make_event())

        self.assertEqual(result, FlushReport(published=1, pending=0))
        self.assertEqual(client.calls[0][0], "edge/events")
        self.assertEqual(client.calls[0][2], 1)

    def test_publish_failure_retains_message_for_later_retry(self) -> None:
        event = make_event()
        client = FakeMqttClient(outcomes=[FakePublishInfo(published=False)])
        outbox = SQLiteOutbox(":memory:")
        self.addCleanup(outbox.close)
        transport = ReliableMqttTransport(client, outbox, FakeCodec(), "edge/events")

        result = transport.submit(event)
        pending = outbox.pending()

        self.assertEqual(result, FlushReport(published=0, pending=1))
        self.assertEqual(pending[0].event_id, event.event_id)
        self.assertEqual(pending[0].attempts, 1)

    def test_tls_configuration_requires_peer_verification(self) -> None:
        client = FakeTlsClient()

        configure_mtls(
            client,
            ca_file="ca.pem",
            certificate_file="client.pem",
            key_file="client.key",
        )

        self.assertFalse(client.insecure)
        self.assertEqual(client.tls_options["ca_certs"], "ca.pem")


if __name__ == "__main__":
    unittest.main()