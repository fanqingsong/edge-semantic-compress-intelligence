from __future__ import annotations

import argparse
import logging
import os

from cloud.agent.consumer import (
    MqttEventConsumer,
    SQLiteProcessedEventStore,
)
from cloud.agent.runtime import (
    RagEventHandler,
    SQLiteAnalysisStore,
)
from cloud.feedback.service import (
    PromptFeedbackService,
    SQLiteFeedbackStore,
)
from cloud.rag.analysis import (
    DeterministicMockAnalysisModel,
    RagService,
)
from cloud.rag.models import (
    OpenAICompatibleAnalysisModel,
)
from cloud.retrieval.adapters import (
    BgeM3HttpEmbedder,
    MilvusVectorIndex,
    ensure_milvus_collection,
)
from cloud.retrieval.hashing import (
    DeterministicHashEmbedder,
)
from cloud.retrieval.hybrid import (
    HybridRetriever,
)
from shared.codec import MessagePackCodec
from shared.mqtt import (
    configure_mtls,
    create_mqtt_v5_client,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume edge events and run cloud RAG")
    parser.add_argument(
        "--mqtt-host", default=os.environ.get("CLOUD_MQTT_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--mqtt-port", type=int, default=int(os.environ.get("CLOUD_MQTT_PORT", "1883"))
    )
    parser.add_argument(
        "--topic", default=os.environ.get("CLOUD_MQTT_TOPIC", "edge/events")
    )
    parser.add_argument(
        "--milvus-uri", default=os.environ.get("CLOUD_MILVUS_URI", "http://127.0.0.1:19530")
    )
    parser.add_argument(
        "--collection", default=os.environ.get("CLOUD_MILVUS_COLLECTION", "ops_cases")
    )
    parser.add_argument(
        "--vector-dimension",
        type=int,
        default=int(os.environ.get("CLOUD_VECTOR_DIMENSION", "1024")),
    )
    parser.add_argument(
        "--embedding-mode",
        choices=("http", "mock"),
        default=os.environ.get("CLOUD_EMBEDDING_MODE", "http"),
    )
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("CLOUD_EMBEDDING_URL", "http://127.0.0.1:8081/embed"),
    )
    parser.add_argument(
        "--analysis-mode",
        choices=("openai", "mock"),
        default=os.environ.get("CLOUD_ANALYSIS_MODE", "mock"),
    )
    parser.add_argument(
        "--analysis-url",
        default=os.environ.get("CLOUD_ANALYSIS_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--analysis-model",
        default=os.environ.get("CLOUD_ANALYSIS_MODEL", "local-cloud-llm"),
    )
    parser.add_argument(
        "--processed-db",
        default=os.environ.get("CLOUD_PROCESSED_DB", "/var/lib/cloud/processed.sqlite3"),
    )
    parser.add_argument(
        "--analysis-db",
        default=os.environ.get("CLOUD_ANALYSIS_DB", "/var/lib/cloud/analyses.sqlite3"),
    )
    parser.add_argument(
        "--feedback-db",
        default=os.environ.get("CLOUD_FEEDBACK_DB", "/var/lib/cloud/feedback.sqlite3"),
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()

    from pymilvus import MilvusClient

    milvus_client = MilvusClient(uri=args.milvus_uri)
    ensure_milvus_collection(
        milvus_client,
        args.collection,
        vector_dimension=args.vector_dimension,
    )
    vector_index = MilvusVectorIndex(
        milvus_client,
        args.collection,
        vector_dimension=args.vector_dimension,
    )
    embedder = (
        BgeM3HttpEmbedder(endpoint=args.embedding_url)
        if args.embedding_mode == "http"
        else DeterministicHashEmbedder(dimension=args.vector_dimension)
    )
    analysis_model = (
        OpenAICompatibleAnalysisModel(
            base_url=args.analysis_url,
            model=args.analysis_model,
            api_key=os.environ.get("CLOUD_ANALYSIS_API_KEY"),
        )
        if args.analysis_mode == "openai"
        else DeterministicMockAnalysisModel()
    )
    rag_service = RagService(
        retriever=HybridRetriever(embedder, vector_index),
        model=analysis_model,
    )
    processed_store = SQLiteProcessedEventStore(args.processed_db)
    analysis_store = SQLiteAnalysisStore(args.analysis_db)
    feedback_store = SQLiteFeedbackStore(args.feedback_db)
    handler = RagEventHandler(
        rag_service,
        analysis_store,
        PromptFeedbackService(feedback_store),
    )
    consumer = MqttEventConsumer(
        args.topic,
        MessagePackCodec(),
        processed_store,
        handler,
    )
    mqtt_client = create_mqtt_v5_client(
        os.environ.get("CLOUD_MQTT_CLIENT_ID", "cloud-rag-agent")
    )
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
    consumer.bind(mqtt_client)

    ca_file = os.environ.get("CLOUD_MQTT_CA_FILE")
    certificate_file = os.environ.get("CLOUD_MQTT_CERT_FILE")
    key_file = os.environ.get("CLOUD_MQTT_KEY_FILE")
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

    logging.info("cloud RAG consumer subscribing to %s", args.topic)
    try:
        mqtt_client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=30)
        mqtt_client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()
        processed_store.close()
        feedback_store.close()
        milvus_client.close()


if __name__ == "__main__":
    main()