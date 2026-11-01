from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class ContractError(ValueError):
    """Raised when an input does not match the published event contract."""


@dataclass(frozen=True, slots=True)
class EdgeEvent:
    event_id: str
    timestamp: str
    service: str
    summary: str
    target_ip: str | None = None
    target_port: int | None = None
    error_code: str | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        try:
            UUID(self.event_id)
        except (ValueError, AttributeError) as error:
            raise ContractError("event_id must be a UUID") from error

        if self.schema_version != "1.0":
            raise ContractError("schema_version must be '1.0'")

        try:
            parsed_timestamp = datetime.fromisoformat(
                self.timestamp.replace("Z", "+00:00")
            )
        except (TypeError, ValueError) as error:
            raise ContractError("timestamp must be an ISO 8601 date-time") from error
        if parsed_timestamp.utcoffset() is None:
            raise ContractError("timestamp must include a timezone")

        if not isinstance(self.service, str) or not self.service.strip():
            raise ContractError("service must be a non-empty string")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ContractError("summary must be a non-empty string")

        if self.target_ip is not None:
            try:
                ipaddress.ip_address(self.target_ip)
            except ValueError as error:
                raise ContractError("target_ip must be a valid IP address") from error

        if self.target_port is not None and (
            isinstance(self.target_port, bool)
            or not isinstance(self.target_port, int)
            or not 1 <= self.target_port <= 65535
        ):
            raise ContractError("target_port must be an integer from 1 to 65535")

        if self.error_code is not None and (
            not isinstance(self.error_code, str) or not self.error_code.strip()
        ):
            raise ContractError("error_code must be null or a non-empty string")

    @classmethod
    def from_mapping(cls, value: object) -> EdgeEvent:
        if not isinstance(value, dict):
            raise ContractError("event must be a JSON object")

        allowed_fields = {
            "event_id",
            "schema_version",
            "timestamp",
            "service",
            "target_ip",
            "target_port",
            "error_code",
            "summary",
        }
        unknown_fields = set(value) - allowed_fields
        if unknown_fields:
            raise ContractError(f"unknown fields: {', '.join(sorted(unknown_fields))}")

        required_fields = {"event_id", "timestamp", "service", "summary"}
        missing_fields = required_fields - set(value)
        if missing_fields:
            raise ContractError(f"missing fields: {', '.join(sorted(missing_fields))}")

        for field in ("event_id", "timestamp", "service", "summary"):
            if not isinstance(value[field], str):
                raise ContractError(f"{field} must be a string")

        for field in ("target_ip", "error_code", "schema_version"):
            if field in value and value[field] is not None and not isinstance(
                value[field], str
            ):
                raise ContractError(f"{field} must be a string or null")
        if "target_port" in value and value["target_port"] is not None and (
            isinstance(value["target_port"], bool)
            or not isinstance(value["target_port"], int)
        ):
            raise ContractError("target_port must be an integer or null")

        return cls(
            event_id=value["event_id"],
            timestamp=value["timestamp"],
            service=value["service"],
            summary=value["summary"],
            target_ip=value.get("target_ip"),
            target_port=value.get("target_port"),
            error_code=value.get("error_code"),
            schema_version=value.get("schema_version", "1.0"),
        )

    @classmethod
    def from_json(cls, payload: str) -> EdgeEvent:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ContractError("event must contain valid JSON") from error
        return cls.from_mapping(value)

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "service": self.service,
            "target_ip": self.target_ip,
            "target_port": self.target_port,
            "error_code": self.error_code,
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), allow_nan=False)