from __future__ import annotations

import argparse
import logging
import os

from edge.agent.http import (
    EdgeHttpConfig,
    create_edge_server,
)
from edge.agent.runtime import EdgeRuntime
from edge.filtering.service import RuleFilter
from edge.summarization.pipeline import (
    DeterministicMockSummarizer,
    SummaryPipeline,
)
from edge.summarization.slm import (
    LlamaCppSummarizer,
)
from edge.transport.outbox import (
    ReliableMqttTransport,
    SQLiteOutbox,
)
from shared.codec import MessagePackCodec
from shared.mqtt import (
    configure_mtls,
    create_mqtt_v5_client,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Receive and process edge log batches")
    parser.add_argument("--host", default=os.environ.get("EDGE_HTTP_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("EDGE_HTTP_PORT", "8090"))
    )
    parser.add_argument(
        "--mqtt-host", default=os.environ.get("EDGE_MQTT_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--mqtt-port", type=int, default=int(os.environ.get("EDGE_MQTT_PORT", "1883"))
    )
    parser.add_argument(
        "--topic", default=os.environ.get("EDGE_MQTT_TOPIC", "edge/events")
    )
    parser.add_argument(
        "--outbox",
        default=os.environ.get("EDGE_OUTBOX_PATH", "./data/edge-outbox.sqlite3"),
    )
    parser.add_argument(
        "--max-outbox-bytes",
        type=int,
        default=int(os.environ.get("EDGE_OUTBOX_MAX_BYTES", str(100 * 1024 * 1024))),
    )
    parser.add_argument(
        "--summarizer",
        choices=("llama_cpp", "mock"),
        default=os.environ.get("EDGE_SUMMARIZER", "llama_cpp"),
    )
    parser.add_argument(
        "--llama-url",
        default=os.environ.get("EDGE_LLAMA_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument(
        "--max-batch-bytes",
        type=int,
        default=int(os.environ.get("EDGE_MAX_BATCH_BYTES", str(1024 * 1024))),
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()

    mqtt_client = create_mqtt_v5_client(os.environ.get("EDGE_MQTT_CLIENT_ID", "edge-agent"))
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
    ca_file = os.environ.get("EDGE_MQTT_CA_FILE")
    certificate_file = os.environ.get("EDGE_MQTT_CERT_FILE")
    key_file = os.environ.get("EDGE_MQTT_KEY_FILE")
    tls_files = (ca_file, certificate_file, key_file)
    if any(tls_files) and not all(tls_files):
        raise SystemExit("mTLS requires CA, client certificate, and client key files")
    if all(tls_files):
        configure_mtls(
            mqtt_client,
            ca_file=ca_file,
            certificate_file=certificate_file,
            key_file=key_file,
        )

    outbox = SQLiteOutbox(args.outbox, max_bytes=args.max_outbox_bytes)
    mqtt_client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=30)
    mqtt_client.loop_start()
    summarizer = (
        DeterministicMockSummarizer()
        if args.summarizer == "mock"
        else LlamaCppSummarizer(base_url=args.llama_url)
    )
    runtime = EdgeRuntime(
        rule_filter=RuleFilter(),
        summarizer=SummaryPipeline(summarizer),
        transport=ReliableMqttTransport(
            mqtt_client,
            outbox,
            MessagePackCodec(),
            args.topic,
        ),
    )
    server = create_edge_server(
        runtime,
        EdgeHttpConfig(
            host=args.host,
            port=args.port,
            max_body_bytes=args.max_batch_bytes,
        ),
    )
    logging.info("edge log endpoint listening on %s:%d", args.host, server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        mqtt_client.disconnect()
        mqtt_client.loop_stop()
        outbox.close()


if __name__ == "__main__":
    main()