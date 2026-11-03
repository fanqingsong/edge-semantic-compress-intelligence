from __future__ import annotations

import argparse
import logging
import os

from cloud.admin.http import (
    AdminConfig,
    AdminServices,
    create_admin_server,
)
from cloud.admin.jobs import IngestWorker, JobStore
from cloud.admin.read_models import (
    AnalysisReader,
    ProcessedReader,
    fetch_edge_status,
)
from cloud.knowledge.ingest import (
    KnowledgeIngestor,
    RawDocumentKnowledgeParser,
)
from cloud.retrieval.adapters import (
    BgeM3HttpEmbedder,
    MilvusVectorIndex,
    ensure_milvus_collection,
)


def require_token(value: str | None) -> str:
    token = (value or "").strip()
    if not token:
        raise SystemExit("ADMIN_TOKEN is required")
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cloud operator console")
    parser.add_argument("--host", default=os.environ.get("ADMIN_HTTP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("ADMIN_HTTP_PORT", "8088"))
    )
    parser.add_argument("--token", default=os.environ.get("ADMIN_TOKEN", ""))
    parser.add_argument(
        "--analysis-db",
        default=os.environ.get("ADMIN_ANALYSIS_DB", "/var/lib/cloud/analyses.sqlite3"),
    )
    parser.add_argument(
        "--processed-db",
        default=os.environ.get("ADMIN_PROCESSED_DB", "/var/lib/cloud/processed.sqlite3"),
    )
    parser.add_argument(
        "--job-db",
        default=os.environ.get("ADMIN_JOB_DB", "/var/lib/admin/jobs.sqlite3"),
    )
    parser.add_argument(
        "--upload-dir",
        default=os.environ.get("ADMIN_UPLOAD_DIR", "/var/lib/admin/uploads"),
    )
    parser.add_argument(
        "--edge-status-url",
        default=os.environ.get("EDGE_STATUS_URL", "http://127.0.0.1:8090/v1/status"),
    )
    parser.add_argument(
        "--milvus-uri",
        default=os.environ.get("CLOUD_MILVUS_URI", "http://127.0.0.1:19530"),
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("CLOUD_MILVUS_COLLECTION", "ops_cases"),
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
        "--max-upload-bytes",
        type=int,
        default=int(os.environ.get("ADMIN_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()
    token = require_token(args.token)

    from pymilvus import MilvusClient

    client = MilvusClient(uri=args.milvus_uri)
    try:
        ensure_milvus_collection(
            client,
            args.collection,
            vector_dimension=args.vector_dimension,
        )
        index = MilvusVectorIndex(
            client,
            args.collection,
            vector_dimension=args.vector_dimension,
        )
        parser = RawDocumentKnowledgeParser()
        ingestor = KnowledgeIngestor(
            parser,
            BgeM3HttpEmbedder(
                base_url=args.embedding_url,
                model=args.embedding_model,
                api_key=os.environ.get("SILICONFLOW_API_KEY"),
            ),
            index,
        )
        jobs = JobStore(args.job_db)
        edge_status_url = args.edge_status_url
        server = create_admin_server(
            AdminServices(
                analyses=AnalysisReader(args.analysis_db),
                processed=ProcessedReader(args.processed_db),
                cases=index,
                jobs=jobs,
                uploads=IngestWorker(jobs, parser, ingestor, args.upload_dir),
                edge_status=lambda: fetch_edge_status(edge_status_url),
            ),
            AdminConfig(
                token=token,
                host=args.host,
                port=args.port,
                max_upload_bytes=args.max_upload_bytes,
            ),
        )
        logging.info("admin console listening on %s:%d", args.host, server.server_port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        client.close()


if __name__ == "__main__":
    main()
