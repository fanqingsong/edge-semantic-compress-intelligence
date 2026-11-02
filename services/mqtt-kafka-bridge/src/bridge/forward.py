from __future__ import annotations

from typing import Any, Protocol


class KafkaProducer(Protocol):
    def send_and_wait(self, topic: str, payload: bytes) -> None:
        """Produce one payload and return only after Kafka acknowledges it."""


class MqttKafkaForwarder:
    def __init__(self, producer: KafkaProducer, topic: str) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        self.producer = producer
        self.topic = topic

    def forward(self, client: Any, mid: int, qos: int, payload: bytes) -> bool:
        try:
            self.producer.send_and_wait(self.topic, payload)
        except Exception:
            return False
        try:
            result = client.ack(mid, qos)
        except Exception:
            return False
        return result == 0
