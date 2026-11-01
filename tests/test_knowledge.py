import json
import importlib.util
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from edge_semantic_compress_intelligence.services.cloud.knowledge import (
    JsonLinesKnowledgeParser,
    KnowledgeFormatError,
    KnowledgeIngestor,
    RawDocumentKnowledgeParser,
)
from edge_semantic_compress_intelligence.services.cloud.retrieval import VectorRecord


@dataclass
class FixedEmbedder:
    texts: list[str] = field(default_factory=list)

    def embed(self, text: str) -> Sequence[float]:
        self.texts.append(text)
        return (0.25, 0.75)


@dataclass
class RecordingIndex:
    upserted: tuple[VectorRecord, ...] = ()
    deleted: tuple[str, set[str]] | None = None

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        self.upserted = tuple(records)

    def delete_source_records_not_in(self, source: str, case_ids: set[str]) -> int:
        self.deleted = (source, case_ids)
        return 2


def case_line(case_id: str, *, target_ip: str | None = "192.0.2.10") -> str:
    return json.dumps(
        {
            "case_id": case_id,
            "summary": "Database connection timeout",
            "resolution": "Review the connection pool limits",
            "target_ip": target_ip,
        }
    )


class KnowledgeIngestorTests(unittest.TestCase):
    def test_ingests_and_versions_normalized_cases(self) -> None:
        embedder = FixedEmbedder()
        index = RecordingIndex()
        ingestor = KnowledgeIngestor(JsonLinesKnowledgeParser(), embedder, index)

        report = ingestor.ingest("tickets/2026-11.jsonl", case_line("CASE-1"))

        self.assertEqual(report.source, "tickets/2026-11.jsonl")
        self.assertEqual(report.upserted, 1)
        self.assertEqual(report.removed_stale, 2)
        self.assertEqual(len(index.upserted), 1)
        version = index.upserted[0].version
        self.assertEqual(index.upserted[0].target_ip, "192.0.2.10")
        self.assertEqual(index.deleted, ("tickets/2026-11.jsonl", {"CASE-1"}))
        self.assertEqual(
            embedder.texts,
            ["Database connection timeout\nReview the connection pool limits"],
        )

        ingestor.ingest("tickets/2026-11.jsonl", case_line("CASE-1"))
        self.assertEqual(index.upserted[0].version, version)

    def test_invalid_source_does_not_mutate_index(self) -> None:
        index = RecordingIndex()
        ingestor = KnowledgeIngestor(JsonLinesKnowledgeParser(), FixedEmbedder(), index)

        with self.assertRaises(KnowledgeFormatError):
            ingestor.ingest("tickets/bad.jsonl", "not-json")

        self.assertEqual(index.upserted, ())
        self.assertIsNone(index.deleted)

    def test_duplicate_case_ids_are_rejected(self) -> None:
        content = "\n".join((case_line("CASE-1"), case_line("CASE-1")))

        with self.assertRaisesRegex(KnowledgeFormatError, "duplicate case_id"):
            JsonLinesKnowledgeParser().parse(content)

    def test_invalid_target_ip_is_rejected(self) -> None:
        with self.assertRaisesRegex(KnowledgeFormatError, "valid IP address"):
            JsonLinesKnowledgeParser().parse(case_line("CASE-1", target_ip="bad-ip"))


class RawDocumentKnowledgeParserTests(unittest.TestCase):
    def test_extracts_multiple_markdown_cases_with_stable_ids(self) -> None:
        content = """# Operations runbook

## Incident: CASE-100
Summary: API requests time out
Root cause: Database connection pool was exhausted
Resolution: Restart the worker.
  Increase the pool after capacity review.
Target IP: 192.0.2.10

## Incident: CASE-101
Summary: Cache connection refused
Resolution: Restore the cache listener.
"""
        parser = RawDocumentKnowledgeParser()

        first_parse = parser.parse_markdown(content, source_name="runbook.md")
        second_parse = parser.parse_markdown(content, source_name="runbook.md")

        self.assertEqual(len(first_parse), 2)
        self.assertEqual(first_parse, second_parse)
        self.assertEqual(first_parse[0].case_id, "CASE-100")
        self.assertEqual(
            first_parse[0].resolution,
            "Root cause: Database connection pool was exhausted\n"
            "Restart the worker.\nIncrease the pool after capacity review.",
        )
        self.assertEqual(first_parse[0].target_ip, "192.0.2.10")
        self.assertTrue(first_parse[1].case_id)

    def test_rejects_unstructured_document_without_case_fields(self) -> None:
        with self.assertRaisesRegex(KnowledgeFormatError, "no sections"):
            RawDocumentKnowledgeParser().parse_markdown(
                "A general troubleshooting note without case labels.",
                source_name="notes.md",
            )

    def test_rejects_case_missing_resolution(self) -> None:
        with self.assertRaisesRegex(KnowledgeFormatError, "Summary and Resolution"):
            RawDocumentKnowledgeParser().parse_markdown(
                "## Incident CASE-102\nSummary: Service unavailable\n",
                source_name="notes.md",
            )

    def test_reads_markdown_file_and_ingests_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incident.md"
            path.write_text(
                "## Incident CASE-103\n"
                "Summary: Database unavailable\n"
                "Resolution: Restore database access\n",
                encoding="utf-8",
            )
            embedder = FixedEmbedder()
            index = RecordingIndex()
            ingestor = KnowledgeIngestor(
                RawDocumentKnowledgeParser(), embedder, index
            )

            report = ingestor.ingest_file(path)

        self.assertEqual(report.upserted, 1)
        self.assertEqual(index.upserted[0].case_id, "CASE-103")
        self.assertIn("Database unavailable", embedder.texts[0])

    def test_markitdown_converts_html_into_cases(self) -> None:
        if importlib.util.find_spec("markitdown") is None:
            self.skipTest("install the documents extra to test MarkItDown conversion")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incident.html"
            path.write_text(
                "<h2>Incident CASE-104</h2>"
                "<p>Summary: API requests time out</p>"
                "<p>Resolution: Restart the worker</p>",
                encoding="utf-8",
            )

            cases = RawDocumentKnowledgeParser().parse_file(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "CASE-104")
        self.assertEqual(cases[0].summary, "API requests time out")


if __name__ == "__main__":
    unittest.main()