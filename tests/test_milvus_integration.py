from __future__ import annotations

import os
import unittest
from uuid import uuid4

from edge_semantic_compress_intelligence.services.cloud.retrieval.adapters import (
    MilvusVectorIndex,
    ensure_milvus_collection,
)
from edge_semantic_compress_intelligence.services.cloud.retrieval import VectorRecord


@unittest.skipUnless(
    os.environ.get("RUN_MILVUS_INTEGRATION") == "1",
    "set RUN_MILVUS_INTEGRATION=1 to run against a local Milvus service",
)
class LocalMilvusIntegrationTests(unittest.TestCase):
    def test_collection_upsert_filtered_search_and_source_cleanup(self) -> None:
        from pymilvus import MilvusClient

        uri = os.environ.get("MILVUS_URI", "http://127.0.0.1:19530")
        collection_name = f"edge_test_{uuid4().hex[:16]}"
        client = MilvusClient(uri=uri)
        try:
            self.assertTrue(
                ensure_milvus_collection(
                    client,
                    collection_name,
                    vector_dimension=4,
                )
            )
            index = MilvusVectorIndex(
                client,
                collection_name,
                vector_dimension=4,
            )
            index.upsert(
                (
                    VectorRecord(
                        case_id="CASE-1",
                        summary="Database connection timeout",
                        resolution="Review pool configuration",
                        source="integration-test",
                        target_ip="192.0.2.10",
                        version="v1",
                        vector=(0.1, 0.2, 0.3, 0.4),
                    ),
                    VectorRecord(
                        case_id="CASE-2",
                        summary="Unrelated host timeout",
                        resolution="Inspect host health",
                        source="integration-test",
                        target_ip="192.0.2.11",
                        version="v1",
                        vector=(0.1, 0.2, 0.3, 0.4),
                    ),
                )
            )
            client.flush(collection_name=collection_name)

            hits = index.search(
                (0.1, 0.2, 0.3, 0.4),
                metadata_filter={"target_ip": "192.0.2.10"},
                limit=5,
            )

            self.assertEqual([hit.case_id for hit in hits], ["CASE-1"])
            self.assertEqual(hits[0].target_ip, "192.0.2.10")
            self.assertEqual(
                index.delete_source_records_not_in("integration-test", set()), 2
            )
            client.flush(collection_name=collection_name)
            self.assertEqual(
                index.search(
                    (0.1, 0.2, 0.3, 0.4),
                    metadata_filter={"target_ip": "192.0.2.10"},
                    limit=5,
                ),
                (),
            )
        finally:
            if client.has_collection(collection_name=collection_name):
                client.drop_collection(collection_name=collection_name)
            client.close()


if __name__ == "__main__":
    unittest.main()