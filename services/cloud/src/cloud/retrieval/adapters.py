from __future__ import annotations

import ipaddress
import json
import math
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cloud.retrieval.hybrid import (
    VectorHit,
    VectorRecord,
)


class EmbeddingServiceError(RuntimeError):
    """Raised when the configured cloud embedding service fails."""


class MilvusSchemaError(ValueError):
    """Raised when an existing Milvus collection is incompatible with the app."""


@dataclass(frozen=True, slots=True)
class BgeM3HttpEmbedder:
    endpoint: str
    timeout_seconds: float = 10.0
    api_key: str | None = None

    def embed(self, text: str) -> Sequence[float]:
        if not self.endpoint.strip():
            raise ValueError("embedding endpoint must not be empty")
        if not text.strip():
            raise ValueError("embedding text must not be empty")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"inputs": text}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise EmbeddingServiceError(
                f"embedding service returned HTTP {error.code}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise EmbeddingServiceError("embedding service request failed") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EmbeddingServiceError("embedding service returned invalid JSON") from error

        vector = payload
        if (
            isinstance(vector, list)
            and vector
            and isinstance(vector[0], list)
            and len(vector) == 1
        ):
            vector = vector[0]
        if not isinstance(vector, list) or not vector:
            raise EmbeddingServiceError("embedding response must be a non-empty vector")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise EmbeddingServiceError("embedding response contains invalid values")
        return tuple(float(value) for value in vector)


@dataclass(frozen=True, slots=True)
class MilvusVectorIndex:
    client: Any
    collection_name: str
    vector_dimension: int = 1024
    vector_field: str = "embedding"

    def __post_init__(self) -> None:
        if not self.collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if self.vector_dimension < 1:
            raise ValueError("vector_dimension must be positive")

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        rows: list[dict[str, object]] = []
        for record in records:
            if len(record.vector) != self.vector_dimension:
                raise ValueError(
                    f"vector for {record.case_id} must have dimension "
                    f"{self.vector_dimension}"
                )
            rows.append(
                {
                    "case_id": record.case_id,
                    "summary": record.summary,
                    "resolution": record.resolution,
                    "source": record.source,
                    "target_ip": record.target_ip,
                    "version": record.version,
                    self.vector_field: list(record.vector),
                }
            )
        if rows:
            self.client.upsert(collection_name=self.collection_name, data=rows)

    def delete_source_records_not_in(self, source: str, case_ids: set[str]) -> int:
        source_literal = json.dumps(source)
        expression = f"source == {source_literal}"
        if case_ids:
            ids_literal = json.dumps(sorted(case_ids))
            expression += f" and case_id not in {ids_literal}"

        result = self.client.delete(
            collection_name=self.collection_name,
            filter=expression,
        )
        if isinstance(result, Mapping):
            return int(result.get("delete_count", 0))
        return int(getattr(result, "delete_count", 0))

    def search(
        self,
        vector: Sequence[float],
        *,
        metadata_filter: Mapping[str, str],
        limit: int,
    ) -> Sequence[VectorHit]:
        if set(metadata_filter) != {"target_ip"}:
            raise ValueError("Milvus search requires an exact target_ip filter")
        if len(vector) != self.vector_dimension:
            raise ValueError(f"query vector must have dimension {self.vector_dimension}")
        if limit != 5:
            raise ValueError("the current retrieval contract requires limit=5")

        target_ip = str(ipaddress.ip_address(metadata_filter["target_ip"]))
        response = self.client.search(
            collection_name=self.collection_name,
            data=[list(vector)],
            anns_field=self.vector_field,
            search_params={"metric_type": "COSINE", "params": {}},
            limit=limit,
            filter=f"target_ip == {json.dumps(target_ip)}",
            output_fields=["case_id", "summary", "resolution", "source", "target_ip"],
        )
        if not response:
            return ()

        hits: list[VectorHit] = []
        for item in response[0]:
            entity = item.get("entity", item)
            score = item.get("distance", item.get("score"))
            if not isinstance(entity, Mapping) or score is None:
                continue
            try:
                hits.append(
                    VectorHit(
                        case_id=str(entity["case_id"]),
                        summary=str(entity["summary"]),
                        resolution=str(entity["resolution"]),
                        source=str(entity["source"]),
                        target_ip=entity.get("target_ip"),
                        score=float(score),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(hits)


def ensure_milvus_collection(
    client: Any,
    collection_name: str,
    vector_dimension: int = 1024,
    vector_field: str = "embedding",
) -> bool:
    if not collection_name.strip():
        raise ValueError("collection_name must not be empty")
    if vector_dimension < 1:
        raise ValueError("vector_dimension must be positive")

    try:
        from pymilvus import DataType, MilvusClient
    except ImportError as error:
        raise RuntimeError("Milvus support requires the 'milvus' extra") from error

    if client.has_collection(collection_name=collection_name):
        description = client.describe_collection(collection_name=collection_name)
        fields = description.get("fields") if isinstance(description, Mapping) else None
        if not isinstance(fields, list):
            raise MilvusSchemaError("Milvus collection description has no fields")

        fields_by_name = {
            field.get("name", field.get("field_name")): field
            for field in fields
            if isinstance(field, Mapping)
        }
        required_fields = {
            "case_id",
            "summary",
            "resolution",
            "source",
            "target_ip",
            "version",
            vector_field,
        }
        missing_fields = required_fields - set(fields_by_name)
        if missing_fields:
            raise MilvusSchemaError(
                f"Milvus collection is missing fields: {', '.join(sorted(missing_fields))}"
            )

        vector_info = fields_by_name[vector_field]
        field_type = vector_info.get("type", vector_info.get("data_type"))
        if isinstance(field_type, str):
            if field_type.upper() not in {"FLOAT_VECTOR", "101"}:
                raise MilvusSchemaError(f"{vector_field} must be a FLOAT_VECTOR")
        elif field_type != DataType.FLOAT_VECTOR:
            raise MilvusSchemaError(f"{vector_field} must be a FLOAT_VECTOR")

        params = vector_info.get("params", vector_info.get("type_params", {}))
        actual_dimension = params.get("dim") if isinstance(params, Mapping) else None
        try:
            actual_dimension = int(actual_dimension)
        except (TypeError, ValueError) as error:
            raise MilvusSchemaError(
                f"{vector_field} has no valid dimension metadata"
            ) from error
        if actual_dimension != vector_dimension:
            raise MilvusSchemaError(
                f"{vector_field} dimension is {actual_dimension}, "
                f"expected {vector_dimension}"
            )
        return False

    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(
        field_name="case_id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=256,
    )
    schema.add_field(field_name="summary", datatype=DataType.VARCHAR, max_length=8192)
    schema.add_field(
        field_name="resolution", datatype=DataType.VARCHAR, max_length=8192
    )
    schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=2048)
    schema.add_field(
        field_name="target_ip",
        datatype=DataType.VARCHAR,
        max_length=64,
        nullable=True,
    )
    schema.add_field(field_name="version", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(
        field_name=vector_field,
        datatype=DataType.FLOAT_VECTOR,
        dim=vector_dimension,
    )

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name=vector_field,
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
    return True