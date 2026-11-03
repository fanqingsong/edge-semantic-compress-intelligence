"""In-process stand-ins so pipeline tests do not call a model server."""

from collections.abc import Mapping, Sequence
from uuid import uuid4

from cloud.rag.analysis import AnalysisAnswer
from edge.filtering.service import LogRecord


class LogBatchSummarizer:
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


class FixedAnalysisModel:
    def generate(self, prompt: str) -> AnalysisAnswer:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        return AnalysisAnswer(
            root_cause="Likely connection saturation",
            evidence=(),
            recommendations=("Check the service.",),
            uncertainty="Fixture answer for the pipeline test.",
        )
