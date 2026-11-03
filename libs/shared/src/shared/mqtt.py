from __future__ import annotations

from typing import Any


def create_mqtt_v5_client(client_id: str) -> Any:
    if not client_id.strip():
        raise ValueError("client_id must not be empty")
    try:
        import paho.mqtt.client as mqtt
    except ImportError as error:
        raise RuntimeError(
            "MQTT support requires the 'transport' extra"
        ) from error
    return mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv5,
    )
