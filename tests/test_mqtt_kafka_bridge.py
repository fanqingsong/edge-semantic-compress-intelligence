import unittest

from bridge.forward import MqttKafkaForwarder


class FakeProducer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, bytes]] = []

    def send_and_wait(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise RuntimeError("kafka unavailable")
        self.sent.append((topic, payload))


class FakeClient:
    def __init__(self, ack_result: int = 0, fail: bool = False) -> None:
        self.ack_result = ack_result
        self.fail = fail
        self.acks: list[tuple[int, int]] = []

    def ack(self, mid: int, qos: int) -> int:
        if self.fail:
            raise RuntimeError("mqtt ack failed")
        self.acks.append((mid, qos))
        return self.ack_result


class MqttKafkaForwarderTests(unittest.TestCase):
    def test_acks_mqtt_only_after_kafka_accepts_the_payload(self) -> None:
        producer = FakeProducer()
        client = FakeClient()
        forwarder = MqttKafkaForwarder(producer, "edge.events")

        forwarded = forwarder.forward(client, 7, 1, b"payload")

        self.assertTrue(forwarded)
        self.assertEqual(producer.sent, [("edge.events", b"payload")])
        self.assertEqual(client.acks, [(7, 1)])

    def test_kafka_failure_leaves_the_mqtt_message_unacked(self) -> None:
        client = FakeClient()
        forwarder = MqttKafkaForwarder(FakeProducer(fail=True), "edge.events")

        forwarded = forwarder.forward(client, 7, 1, b"payload")

        self.assertFalse(forwarded)
        self.assertEqual(client.acks, [])

    def test_mqtt_ack_failure_is_not_treated_as_forwarded(self) -> None:
        producer = FakeProducer()
        forwarder = MqttKafkaForwarder(producer, "edge.events")

        forwarded = forwarder.forward(FakeClient(fail=True), 7, 1, b"payload")

        self.assertFalse(forwarded)
        self.assertEqual(producer.sent, [("edge.events", b"payload")])


if __name__ == "__main__":
    unittest.main()
