from __future__ import annotations

import ssl
from typing import Any


def configure_mtls(
    client: Any,
    *,
    ca_file: str,
    certificate_file: str,
    key_file: str,
) -> None:
    client.tls_set(
        ca_certs=ca_file,
        certfile=certificate_file,
        keyfile=key_file,
        cert_reqs=ssl.CERT_REQUIRED,
    )
    client.tls_insecure_set(False)


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
