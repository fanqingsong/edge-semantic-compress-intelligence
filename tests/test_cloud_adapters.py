import json
import sys
import unittest
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from edge_semantic_compress_intelligence.services.cloud.adapters import (
    BgeM3HttpEmbedder,
    EmbeddingServiceError,
    MilvusVectorIndex,
    MilvusSchemaError,
    ensure_milvus_collection,
)
from edge_semantic_compress_intelligence.services.cloud.retrieval import VectorRecord


@dataclass
class FakeResponse:
    payload: bytes

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


@dataclass
class FakeMilvusClient:
    upserted: list[dict[str, object]] = field(default_factory=list)
    deleted_filter: str | None = None
    search_call: dict[str, Any] | None = None
    search_result: list[list[dict[str, Any]]] = field(default_factory=list)
    existing: bool = False
    description: dict[str, Any] = field(default_factory=dict)
    created_collection: dict[str, Any] | None = None

    def has_collection(self, **kwargs: Any) -> bool:
        return self.existing

    def describe_collection(self, **kwargs: Any) -> dict[str, Any]:
        return self.description

    def create_collection(self, **kwargs: Any) -> None:
        self.created_collection = kwargs

    def upsert(self, **kwargs: Any) -> None:
        self.upserted.extend(kwargs["data"])

    def delete(self, **kwargs: Any) -> dict[str, int]:
        self.deleted_filter = kwargs["filter"]
        return {"delete_count": 2}

    def search(self, **kwargs: Any) -> list[list[dict[str, Any]]]:
        self.search_call = kwargs
        return self.search_result


def vector_record() -> VectorRecord:
    return VectorRecord(
        case_id="CASE-1",
        summary="Database timeout",
        resolution="Review pool configuration",
        source="tickets.jsonl",
        target_ip="192.0.2.10",
        version="version-hash",
        vector=(0.1, 0.2),
    )


class FakeSchema:
    def __init__(self) -> None:
        self.fields: list[dict[str, Any]] = []

    def add_field(self, **kwargs: Any) -> None:
        self.fields.append(kwargs)


class FakeIndexParams:
    def __init__(self) -> None:
        self.indexes: list[dict[str, Any]] = []

    def add_index(self, **kwargs: Any) -> None:
        self.indexes.append(kwargs)


class FakeMilvusSchemaBuilder:
    schema: FakeSchema | None = None
    index_params: FakeIndexParams | None = None

    @classmethod
    def create_schema(cls, **kwargs: Any) -> FakeSchema:
        cls.schema = FakeSchema()
        return cls.schema

    @classmethod
    def prepare_index_params(cls) -> FakeIndexParams:
        cls.index_params = FakeIndexParams()
        return cls.index_params


class BgeM3HttpEmbedderTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_sends_text_and_parses_single_vector(self, urlopen: Any) -> None:
        urlopen.return_value = FakeResponse(b"[[0.1, 0.2, 0.3]]")
        embedder = BgeM3HttpEmbedder(
            endpoint="http://embedding.internal/embed", api_key="test-token"
        )

        vector = embedder.embed("database timeout")

        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"inputs": "database timeout"})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(vector, (0.1, 0.2, 0.3))

    @patch("urllib.request.urlopen")
    def test_rejects_non_finite_embedding_values(self, urlopen: Any) -> None:
        urlopen.return_value = FakeResponse(b"[0.1, NaN]")

        with self.assertRaisesRegex(EmbeddingServiceError, "invalid values"):
            BgeM3HttpEmbedder("http://embedding.internal/embed").embed("query")


class MilvusVectorIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sdk = SimpleNamespace(
            DataType=SimpleNamespace(VARCHAR=21, FLOAT_VECTOR=101),
            MilvusClient=FakeMilvusSchemaBuilder,
        )

    def test_creates_collection_with_required_fields_and_cosine_index(self) -> None:
        client = FakeMilvusClient()
        with patch.dict(sys.modules, {"pymilvus": self.sdk}):
            created = ensure_milvus_collection(
                client, "ops_cases", vector_dimension=1024
            )

        self.assertTrue(created)
        fields = client.created_collection["schema"].fields
        self.assertEqual(
            {field["field_name"] for field in fields},
            {
                "case_id",
                "summary",
                "resolution",
                "source",
                "target_ip",
                "version",
                "embedding",
            },
        )
        vector_field = next(field for field in fields if field["field_name"] == "embedding")
        self.assertEqual(vector_field["dim"], 1024)
        self.assertEqual(
            client.created_collection["index_params"].indexes[0]["metric_type"],
            "COSINE",
        )

    def test_accepts_existing_compatible_collection(self) -> None:
        client = FakeMilvusClient(
            existing=True,
            description={
                "fields": [
                    {"name": name}
                    for name in (
                        "case_id",
                        "summary",
                        "resolution",
                        "source",
                        "target_ip",
                        "version",
                    )
                ]
                + [
                    {
                        "name": "embedding",
                        "type": 101,
                        "params": {"dim": "1024"},
                    }
                ]
            },
        )
        with patch.dict(sys.modules, {"pymilvus": self.sdk}):
            created = ensure_milvus_collection(client, "ops_cases", 1024)

        self.assertFalse(created)
        self.assertIsNone(client.created_collection)

    def test_rejects_existing_collection_with_wrong_vector_dimension(self) -> None:
        client = FakeMilvusClient(
            existing=True,
            description={
                "fields": [
                    {"name": name}
                    for name in (
                        "case_id",
                        "summary",
                        "resolution",
                        "source",
                        "target_ip",
                        "version",
                    )
                ]
                + [
                    {
                        "name": "embedding",
                        "type": 101,
                        "params": {"dim": "768"},
                    }
                ]
            },
        )
        with patch.dict(sys.modules, {"pymilvus": self.sdk}):
            with self.assertRaisesRegex(MilvusSchemaError, "expected 1024"):
                ensure_milvus_collection(client, "ops_cases", 1024)

    def test_rejects_existing_collection_missing_required_field(self) -> None:
        client = FakeMilvusClient(existing=True, description={"fields": []})
        with patch.dict(sys.modules, {"pymilvus": self.sdk}):
            with self.assertRaisesRegex(MilvusSchemaError, "missing fields"):
                ensure_milvus_collection(client, "ops_cases", 1024)

    def test_upsert_and_source_scoped_stale_deletion(self) -> None:
        client = FakeMilvusClient()
        index = MilvusVectorIndex(client, "ops_cases", vector_dimension=2)

        index.upsert((vector_record(),))
        removed = index.delete_source_records_not_in(
            "tickets.jsonl", {"CASE-1", 'CASE"2'}
        )

        self.assertEqual(client.upserted[0]["case_id"], "CASE-1")
        self.assertEqual(client.upserted[0]["embedding"], [0.1, 0.2])
        self.assertEqual(removed, 2)
        self.assertIn('source == "tickets.jsonl"', client.deleted_filter)
        self.assertIn(
            r'case_id not in ["CASE\"2", "CASE-1"]', client.deleted_filter
        )

    def test_search_always_applies_exact_target_ip_filter(self) -> None:
        client = FakeMilvusClient(
            search_result=[
                [
                    {
                        "id": "CASE-1",
                        "distance": 0.91,
                        "entity": {
                            "case_id": "CASE-1",
                            "summary": "Database timeout",
                            "resolution": "Review pool limits",
                            "source": "tickets.jsonl",
                            "target_ip": "192.0.2.10",
                        },
                    }
                ]
            ]
        )
        index = MilvusVectorIndex(client, "ops_cases", vector_dimension=2)

        hits = index.search(
            (0.1, 0.2), metadata_filter={"target_ip": "192.0.2.10"}, limit=5
        )

        self.assertEqual(client.search_call["filter"], 'target_ip == "192.0.2.10"')
        self.assertEqual(client.search_call["limit"], 5)
        self.assertEqual(hits[0].score, 0.91)

    def test_rejects_query_without_metadata_filter(self) -> None:
        index = MilvusVectorIndex(FakeMilvusClient(), "ops_cases", vector_dimension=2)

        with self.assertRaisesRegex(ValueError, "exact target_ip"):
            index.search((0.1, 0.2), metadata_filter={}, limit=5)


if __name__ == "__main__":
    unittest.main()