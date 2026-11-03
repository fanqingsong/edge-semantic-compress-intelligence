from __future__ import annotations

import argparse
import logging
import os

from cloud.agent.consumer import (
    KafkaEventConsumer,
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
from cloud.rag.analysis import RagService
from cloud.rag.models import (
    OpenAICompatibleAnalysisModel,
)
from cloud.retrieval.adapters import (
    BgeM3HttpEmbedder,
    MilvusVectorIndex,
    ensure_milvus_collection,
)
from cloud.retrieval.hybrid import (
    HybridRetriever,
)
from shared.codec import MessagePackCodec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume edge events and run cloud RAG")
    parser.add_argument(
        "--kafka-bootstrap",
        default=os.environ.get("CLOUD_KAFKA_BOOTSTRAP", "127.0.0.1:9092"),
    )
    parser.add_argument(
        "--kafka-topic", default=os.environ.get("CLOUD_KAFKA_TOPIC", "edge.events")
    )
    parser.add_argument(
        "--kafka-group", default=os.environ.get("CLOUD_KAFKA_GROUP", "cloud-agent")
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
        "--embedding-url",
        default=os.environ.get("CLOUD_EMBEDDING_URL")
        or os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("CLOUD_EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
    parser.add_argument(
        "--analysis-url",
        default=os.environ.get("CLOUD_ANALYSIS_URL")
        or os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    )
    parser.add_argument(
        "--analysis-model",
        default=os.environ.get("CLOUD_ANALYSIS_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
    )
    parser.add_argument(
        "--analysis-timeout",
        type=float,
        default=float(os.environ.get("CLOUD_ANALYSIS_TIMEOUT", "60")),
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
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    embedder = BgeM3HttpEmbedder(
        base_url=args.embedding_url,
        model=args.embedding_model,
        api_key=api_key,
    )
    analysis_model = OpenAICompatibleAnalysisModel(
        base_url=args.analysis_url,
        model=args.analysis_model,
        api_key=api_key,
        timeout_seconds=args.analysis_timeout,
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
    consumer = KafkaEventConsumer(MessagePackCodec(), processed_store, handler)
    logging.info("cloud RAG consumer reading Kafka topic %s", args.kafka_topic)
    try:
        consume_kafka(args, consumer)
    except KeyboardInterrupt:
        pass
    finally:
        processed_store.close()
        feedback_store.close()
        milvus_client.close()


def consume_kafka(args: argparse.Namespace, consumer: KafkaEventConsumer) -> None:
    import time

    from kafka import KafkaConsumer, OffsetAndMetadata, TopicPartition

    kafka_consumer = KafkaConsumer(
        args.kafka_topic,
        bootstrap_servers=[
            server.strip() for server in args.kafka_bootstrap.split(",") if server.strip()
        ],
        group_id=args.kafka_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_records=1,
    )
    try:
        while True:
            batches = kafka_consumer.poll(timeout_ms=1000)
            retry = False
            for topic_partition, records in batches.items():
                for record in records:
                    result = consumer.handle_payload(
                        record.value,
                        lambda record=record: kafka_consumer.commit(
                            {
                                TopicPartition(record.topic, record.partition): OffsetAndMetadata(
                                    record.offset + 1, None
                                )
                            }
                        ),
                    )
                    if result.disposition not in {"processed", "duplicate"}:
                        kafka_consumer.seek(topic_partition, record.offset)
                        retry = True
                        break
                if retry:
                    break
            if retry:
                time.sleep(1)
    finally:
        kafka_consumer.close()


if __name__ == "__main__":
    main()