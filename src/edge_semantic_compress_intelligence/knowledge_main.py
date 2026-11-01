from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from edge_semantic_compress_intelligence.cloud_adapters import (
    BgeM3HttpEmbedder,
    MilvusVectorIndex,
    ensure_milvus_collection,
)
from edge_semantic_compress_intelligence.cloud_runtime import DeterministicHashEmbedder
from edge_semantic_compress_intelligence.knowledge import (
    KnowledgeIngestor,
    RawDocumentKnowledgeParser,
)


SUPPORTED_EXTENSIONS = {
    ".docx",
    ".html",
    ".htm",
    ".jsonl",
    ".md",
    ".markdown",
    ".pdf",
    ".pptx",
    ".txt",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse raw operational documents and upsert cases into Milvus"
    )
    parser.add_argument("--path", required=True, help="A file or directory to ingest")
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
        "--embedding-mode",
        choices=("http", "mock"),
        default=os.environ.get("CLOUD_EMBEDDING_MODE", "http"),
    )
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("CLOUD_EMBEDDING_URL", "http://127.0.0.1:8081/embed"),
    )
    return parser


def _collect_files(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"unsupported document type: {path.suffix or '(none)'}")
        return (path,)
    if not path.is_dir():
        raise ValueError(f"input path does not exist: {path}")
    files = tuple(
        sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and candidate.suffix.casefold() in SUPPORTED_EXTENSIONS
        )
    )
    if not files:
        raise ValueError(f"no supported documents found in {path}")
    return files


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args()
    input_path = Path(args.path).expanduser().resolve()
    files = _collect_files(input_path)
    source_root = input_path if input_path.is_dir() else input_path.parent

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
        embedder = (
            BgeM3HttpEmbedder(args.embedding_url)
            if args.embedding_mode == "http"
            else DeterministicHashEmbedder(args.vector_dimension)
        )
        ingestor = KnowledgeIngestor(RawDocumentKnowledgeParser(), embedder, index)

        reports = []
        failures = []
        for document in files:
            source = document.relative_to(source_root).as_posix()
            try:
                cases = ingestor.parser.parse_file(document)
                reports.append(ingestor.ingest_cases(source, cases))
            except Exception as error:
                logging.exception("failed to ingest %s", source)
                failures.append({"source": source, "error": str(error)})

        summary = {
            "sources": len(reports),
            "upserted": sum(report.upserted for report in reports),
            "removed_stale": sum(report.removed_stale for report in reports),
            "failures": failures,
        }
        print(json.dumps(summary, ensure_ascii=False))
        if failures:
            raise SystemExit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()