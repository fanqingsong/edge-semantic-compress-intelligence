from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from edge_semantic_compress_intelligence.services.cloud.retrieval import TextEmbedder, VectorIndex, VectorRecord


class KnowledgeFormatError(ValueError):
    """Raised when a knowledge source is not valid MVP JSON Lines."""


@dataclass(frozen=True, slots=True)
class KnowledgeCase:
    case_id: str
    summary: str
    resolution: str
    target_ip: str | None = None


class KnowledgeParser(Protocol):
    def parse(self, content: str) -> Sequence[KnowledgeCase]:
        """Parse a source document into normalized historical cases."""


class JsonLinesKnowledgeParser:
    def parse(self, content: str) -> tuple[KnowledgeCase, ...]:
        cases: list[KnowledgeCase] = []
        seen_case_ids: set[str] = set()

        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise KnowledgeFormatError(
                    f"line {line_number} must contain valid JSON"
                ) from error

            if not isinstance(value, dict):
                raise KnowledgeFormatError(f"line {line_number} must be a JSON object")

            case_id = value.get("case_id")
            summary = value.get("summary")
            resolution = value.get("resolution")
            if not isinstance(case_id, str) or not case_id.strip():
                raise KnowledgeFormatError(f"line {line_number} requires case_id")
            if not isinstance(summary, str) or not summary.strip():
                raise KnowledgeFormatError(f"line {line_number} requires summary")
            if not isinstance(resolution, str) or not resolution.strip():
                raise KnowledgeFormatError(f"line {line_number} requires resolution")
            if case_id in seen_case_ids:
                raise KnowledgeFormatError(f"duplicate case_id on line {line_number}")

            target_ip = value.get("target_ip")
            if target_ip is not None:
                if not isinstance(target_ip, str):
                    raise KnowledgeFormatError(
                        f"line {line_number} target_ip must be a string or null"
                    )
                try:
                    target_ip = str(ipaddress.ip_address(target_ip))
                except ValueError as error:
                    raise KnowledgeFormatError(
                        f"line {line_number} target_ip must be a valid IP address"
                    ) from error

            seen_case_ids.add(case_id)
            cases.append(
                KnowledgeCase(
                    case_id=case_id,
                    summary=summary,
                    resolution=resolution,
                    target_ip=target_ip,
                )
            )

        return tuple(cases)


@dataclass(frozen=True, slots=True)
class RawDocumentKnowledgeParser:
    def parse(self, content: str) -> tuple[KnowledgeCase, ...]:
        return self.parse_markdown(content, source_name="inline-document")

    def parse_file(self, path: str | Path) -> tuple[KnowledgeCase, ...]:
        source_path = Path(path)
        extension = source_path.suffix.casefold()
        if extension == ".jsonl":
            return JsonLinesKnowledgeParser().parse(
                source_path.read_text(encoding="utf-8")
            )

        if extension in {".md", ".markdown", ".txt"}:
            markdown = source_path.read_text(encoding="utf-8")
        else:
            try:
                from markitdown import MarkItDown
            except ImportError as error:
                raise RuntimeError(
                    "PDF/DOCX/HTML parsing requires the 'documents' extra"
                ) from error
            try:
                markdown = MarkItDown().convert(source_path).text_content
            except Exception as error:
                raise KnowledgeFormatError(
                    f"failed to convert document {source_path.name}"
                ) from error

        return self.parse_markdown(markdown, source_name=source_path.as_posix())

    @classmethod
    def parse_markdown(
        cls,
        content: str,
        *,
        source_name: str,
    ) -> tuple[KnowledgeCase, ...]:
        sections = cls._sections(content)
        cases: list[KnowledgeCase] = []
        for heading, lines in sections:
            fields = cls._fields(lines)
            if not fields:
                continue

            summary = fields.get("summary", "").strip()
            resolution = fields.get("resolution", "").strip()
            if not summary or not resolution:
                raise KnowledgeFormatError(
                    f"section {heading!r} requires Summary and Resolution fields"
                )

            root_cause = fields.get("root_cause", "").strip()
            if root_cause:
                resolution = f"Root cause: {root_cause}\n{resolution}"

            case_id = fields.get("case_id", "").strip()
            if not case_id:
                heading_id = re.search(r"\bCASE-[A-Za-z0-9_-]+\b", heading, re.IGNORECASE)
                if heading_id:
                    case_id = heading_id.group().upper()
                else:
                    stable_source = f"{source_name}\0{heading}\0{summary}"
                    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:16]
                    case_id = f"DOC-{digest}"

            target_ip = fields.get("target_ip", "").strip() or None
            if target_ip is not None:
                try:
                    target_ip = str(ipaddress.ip_address(target_ip))
                except ValueError as error:
                    raise KnowledgeFormatError(
                        f"section {heading!r} has an invalid target_ip"
                    ) from error

            cases.append(
                KnowledgeCase(
                    case_id=case_id,
                    summary=summary,
                    resolution=resolution,
                    target_ip=target_ip,
                )
            )

        if not cases:
            raise KnowledgeFormatError(
                "document contains no sections with Summary and Resolution fields"
            )
        case_ids = [case.case_id for case in cases]
        if len(set(case_ids)) != len(case_ids):
            raise KnowledgeFormatError("document contains duplicate case IDs")
        return tuple(cases)

    @staticmethod
    def _sections(content: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        sections: list[tuple[str, list[str]]] = [("document", [])]
        for line in content.splitlines():
            heading = re.match(r"^#{1,2}\s+(.+?)\s*#*\s*$", line)
            if heading:
                sections.append((heading.group(1).strip(), []))
            else:
                sections[-1][1].append(line)
        return tuple((heading, tuple(lines)) for heading, lines in sections)

    @staticmethod
    def _fields(lines: Sequence[str]) -> dict[str, str]:
        labels = {
            "case_id": {"case_id", "case id", "id", "工单号", "案例编号"},
            "summary": {
                "summary",
                "symptom",
                "issue",
                "problem",
                "故障现象",
                "症状",
                "问题描述",
                "摘要",
            },
            "root_cause": {"root cause", "root_cause", "根因", "原因分析"},
            "resolution": {
                "resolution",
                "solution",
                "fix",
                "remediation",
                "处理步骤",
                "处理过程",
                "解决方案",
                "修复过程",
            },
            "target_ip": {"target_ip", "target ip", "ip", "目标ip", "目标 ip", "目标地址"},
        }
        aliases = {
            alias.casefold(): field_name
            for field_name, field_aliases in labels.items()
            for alias in field_aliases
        }
        fields: dict[str, list[str]] = {}
        current_field: str | None = None
        for line in lines:
            match = re.match(r"^\s*(?:[-*+]\s*)?([^:：]+?)\s*[:：]\s*(.*)$", line)
            if match:
                label = match.group(1).strip().strip("*_` ").casefold()
                current_field = aliases.get(label)
                if current_field is not None:
                    fields.setdefault(current_field, []).append(match.group(2).strip())
                continue
            if current_field is not None and line.strip():
                fields[current_field].append(line.strip())

        return {
            field_name: "\n".join(value for value in values if value).strip()
            for field_name, values in fields.items()
        }


@dataclass(frozen=True, slots=True)
class IngestReport:
    source: str
    upserted: int
    removed_stale: int


@dataclass(frozen=True, slots=True)
class KnowledgeIngestor:
    parser: KnowledgeParser
    embedder: TextEmbedder
    index: VectorIndex

    def ingest(self, source: str, content: str) -> IngestReport:
        if not source.strip():
            raise ValueError("source must not be empty")

        cases = tuple(self.parser.parse(content))
        return self.ingest_cases(source, cases)

    def ingest_file(self, path: str | Path) -> IngestReport:
        parser = self.parser
        parse_file = getattr(parser, "parse_file", None)
        if parse_file is None:
            raise TypeError("configured parser does not support file input")
        source_path = Path(path)
        cases = tuple(parse_file(source_path))
        return self.ingest_cases(source_path.as_posix(), cases)

    def ingest_cases(
        self,
        source: str,
        cases: Sequence[KnowledgeCase],
    ) -> IngestReport:
        if not source.strip():
            raise ValueError("source must not be empty")
        records: list[VectorRecord] = []
        for case in cases:
            embedding_text = f"{case.summary}\n{case.resolution}"
            vector = tuple(self.embedder.embed(embedding_text))
            if not vector or any(not math.isfinite(value) for value in vector):
                raise ValueError(f"embedder returned an invalid vector for {case.case_id}")

            version_payload = json.dumps(
                {
                    "summary": case.summary,
                    "resolution": case.resolution,
                    "target_ip": case.target_ip,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            version = hashlib.sha256(version_payload.encode("utf-8")).hexdigest()
            records.append(
                VectorRecord(
                    case_id=case.case_id,
                    summary=case.summary,
                    resolution=case.resolution,
                    source=source,
                    target_ip=case.target_ip,
                    version=version,
                    vector=vector,
                )
            )

        keep_ids = {case.case_id for case in cases}
        self.index.upsert(records)
        removed_stale = self.index.delete_source_records_not_in(source, keep_ids)
        return IngestReport(
            source=source,
            upserted=len(records),
            removed_stale=removed_stale,
        )