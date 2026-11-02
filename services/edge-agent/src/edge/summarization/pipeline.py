from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Callable, Protocol
from uuid import uuid4

from shared.contract import ContractError, EdgeEvent
from edge.filtering.service import LogRecord


class StructuredSummarizer(Protocol):
    def summarize(self, records: Sequence[LogRecord]) -> Mapping[str, object]:
        """Return structured fields for one service's log batch."""


@dataclass(frozen=True, slots=True)
class DeterministicMockSummarizer:
    def summarize(self, records: Sequence[LogRecord]) -> Mapping[str, object]:
        if not records:
            raise ValueError("records must not be empty")

        services = {record.service for record in records}
        if len(services) != 1:
            raise ValueError("a summary batch must contain exactly one service")

        service = records[0].service
        return {
            "event_id": str(uuid4()),
            "schema_version": "1.0",
            "timestamp": records[-1].timestamp,
            "service": service,
            "summary": f"{len(records)} error log entries for {service}",
        }


class EntityFallback:
    _ip_token = re.compile(r"(?<![A-Fa-f0-9:.])[A-Fa-f0-9:.]{2,45}(?![A-Fa-f0-9:.])")
    _port_token = re.compile(
        r"\b(?:target[_ -]?port|port)\s*(?:[:=]\s*|\s+)(\d{1,5})\b",
        re.IGNORECASE,
    )
    _error_code = re.compile(r"\bERR-\d+\b", re.IGNORECASE)

    def apply(
        self,
        summary: Mapping[str, object],
        records: Sequence[LogRecord],
    ) -> dict[str, object]:
        if not records:
            raise ValueError("records must not be empty")
        if not isinstance(summary, Mapping):
            raise ContractError("summarizer output must be a mapping")

        result = dict(summary)
        ip_candidates = self._find_ips(records)
        port_candidates = self._find_ports(records)
        error_candidates = self._find_error_codes(records)

        proposed_ip = result.get("target_ip")
        result["target_ip"] = self._validated_candidate(
            proposed_ip, ip_candidates, self._normalize_ip
        )

        proposed_port = result.get("target_port")
        result["target_port"] = self._validated_candidate(
            proposed_port, port_candidates, self._normalize_port
        )

        proposed_error = result.get("error_code")
        result["error_code"] = self._validated_candidate(
            proposed_error, error_candidates, self._normalize_error_code
        )
        return result

    def _find_ips(self, records: Sequence[LogRecord]) -> tuple[str, ...]:
        candidates: list[str] = []
        for record in records:
            if record.target_ip:
                normalized = self._normalize_ip(record.target_ip)
                if normalized is not None:
                    candidates.append(normalized)

            for match in self._ip_token.finditer(record.message):
                token = match.group()
                if "." not in token and ":" not in token:
                    continue
                normalized = self._normalize_ip(token)
                if normalized is not None:
                    candidates.append(normalized)

        return tuple(dict.fromkeys(candidates))

    def _find_ports(self, records: Sequence[LogRecord]) -> tuple[int, ...]:
        candidates: list[int] = []
        for record in records:
            if record.target_port is not None:
                normalized = self._normalize_port(record.target_port)
                if normalized is not None:
                    candidates.append(normalized)

            candidates.extend(
                normalized
                for match in self._port_token.finditer(record.message)
                if (normalized := self._normalize_port(match.group(1))) is not None
            )
        return tuple(dict.fromkeys(candidates))

    def _find_error_codes(self, records: Sequence[LogRecord]) -> tuple[str, ...]:
        candidates: list[str] = []
        for record in records:
            if record.error_code:
                normalized = self._normalize_error_code(record.error_code)
                if normalized is not None:
                    candidates.append(normalized)
            candidates.extend(
                match.group().upper()
                for match in self._error_code.finditer(record.message)
            )
        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def _validated_candidate(
        proposed: object,
        candidates: tuple[str, ...] | tuple[int, ...],
        normalize: Callable[[object], str | int | None],
    ) -> str | int | None:
        normalized = normalize(proposed)
        if normalized is not None and normalized in candidates:
            return normalized
        return candidates[0] if candidates else None

    @staticmethod
    def _normalize_ip(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return None

    @staticmethod
    def _normalize_port(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            port = int(value)
        except (TypeError, ValueError):
            return None
        if isinstance(value, str) and not value.strip().isdigit():
            return None
        return port if 1 <= port <= 65535 else None

    @staticmethod
    def _normalize_error_code(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        match = EntityFallback._error_code.fullmatch(value.strip())
        return match.group().upper() if match else None


@dataclass(frozen=True, slots=True)
class SummaryPipeline:
    summarizer: StructuredSummarizer
    entity_fallback: EntityFallback = EntityFallback()

    def summarize(self, records: Sequence[LogRecord]) -> EdgeEvent:
        candidate = self.summarizer.summarize(records)
        completed = self.entity_fallback.apply(candidate, records)
        return EdgeEvent.from_mapping(completed)