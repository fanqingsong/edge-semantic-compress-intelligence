from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Iterable


class DropReason(StrEnum):
    INVALID_FORMAT = "invalid_format"
    SUCCESS_STATUS = "success_status"
    BLACKLISTED_KEYWORD = "blacklisted_keyword"
    FREQUENCY_SUPPRESSED = "frequency_suppressed"


class LogFormatError(ValueError):
    """Raised when a JSON Lines record does not match the MVP input format."""


@dataclass(frozen=True, slots=True)
class LogRecord:
    timestamp: str
    service: str
    message: str
    status_code: str | int | None = None
    target_ip: str | None = None
    target_port: int | str | None = None
    error_code: str | None = None

    @classmethod
    def from_json_line(cls, line: str) -> LogRecord:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise LogFormatError("line must contain valid JSON") from error

        if not isinstance(value, dict):
            raise LogFormatError("line must be a JSON object")

        for field_name in ("timestamp", "service", "message"):
            if not isinstance(value.get(field_name), str) or not value[field_name].strip():
                raise LogFormatError(f"{field_name} must be a non-empty string")

        try:
            datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
        except ValueError as error:
            raise LogFormatError("timestamp must be an ISO 8601 date-time") from error

        status_code = value.get("status_code")
        if status_code is not None and (
            isinstance(status_code, bool) or not isinstance(status_code, (str, int))
        ):
            raise LogFormatError("status_code must be a string, integer, or null")

        for field_name in ("target_ip", "error_code"):
            field_value = value.get(field_name)
            if field_value is not None and not isinstance(field_value, str):
                raise LogFormatError(f"{field_name} must be a string or null")

        target_port = value.get("target_port")
        if target_port is not None and (
            isinstance(target_port, bool)
            or not isinstance(target_port, (str, int))
        ):
            raise LogFormatError("target_port must be a string, integer, or null")

        return cls(
            timestamp=value["timestamp"],
            service=value["service"],
            message=value["message"],
            status_code=status_code,
            target_ip=value.get("target_ip"),
            target_port=target_port,
            error_code=value.get("error_code"),
        )


@dataclass(frozen=True, slots=True)
class FilterConfig:
    success_statuses: frozenset[str] = frozenset({"200", "ok"})
    blacklist_keywords: tuple[str, ...] = ("heartbeat", "health check", "healthcheck")
    repeat_threshold: int = 10

    def __post_init__(self) -> None:
        if self.repeat_threshold < 1:
            raise ValueError("repeat_threshold must be at least 1")
        if any(not keyword.strip() for keyword in self.blacklist_keywords):
            raise ValueError("blacklist keywords must not be empty")


@dataclass(frozen=True, slots=True)
class FilterReport:
    accepted: tuple[LogRecord, ...]
    dropped: dict[DropReason, int] = field(default_factory=dict)


class RuleFilter:
    def __init__(self, config: FilterConfig | None = None) -> None:
        self.config = config or FilterConfig()
        self._success_statuses = {
            status.strip().casefold() for status in self.config.success_statuses
        }
        self._blacklist_keywords = tuple(
            keyword.casefold() for keyword in self.config.blacklist_keywords
        )

    def process_batch(self, lines: Iterable[str]) -> FilterReport:
        dropped: Counter[DropReason] = Counter()
        candidates: list[LogRecord] = []

        for line in lines:
            try:
                record = LogRecord.from_json_line(line)
            except (LogFormatError, TypeError):
                dropped[DropReason.INVALID_FORMAT] += 1
                continue

            status = str(record.status_code).strip().casefold()
            if status and status in self._success_statuses:
                dropped[DropReason.SUCCESS_STATUS] += 1
                continue

            message = record.message.casefold()
            if any(keyword in message for keyword in self._blacklist_keywords):
                dropped[DropReason.BLACKLISTED_KEYWORD] += 1
                continue

            candidates.append(record)

        positions_by_fingerprint: dict[tuple[str, str], list[int]] = defaultdict(list)
        for index, record in enumerate(candidates):
            fingerprint = (record.service.casefold(), record.message.casefold())
            positions_by_fingerprint[fingerprint].append(index)

        suppressed_positions: set[int] = set()
        for positions in positions_by_fingerprint.values():
            if len(positions) > self.config.repeat_threshold:
                suppressed_positions.update(positions[1:-1])

        dropped[DropReason.FREQUENCY_SUPPRESSED] += len(suppressed_positions)
        accepted = tuple(
            record
            for index, record in enumerate(candidates)
            if index not in suppressed_positions
        )
        return FilterReport(accepted=accepted, dropped=dict(dropped))