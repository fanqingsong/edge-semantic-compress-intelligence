from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from cloud.rag.models import (
    AnalysisModelError,
    OpenAICompatibleAnalysisModel,
)
from cloud.rag import AnalysisAnswer


class FakeResponse:
    def __init__(self, value: object) -> None:
        self.payload = json.dumps(value).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class OpenAICompatibleAnalysisModelTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_sends_json_object_request_and_parses_analysis(self, urlopen: Any) -> None:
        answer = {
            "root_cause": "Likely connection pool exhaustion",
            "evidence": ["CASE-1"],
            "recommendations": ["Review pool limits"],
            "uncertainty": "Confirm with current metrics",
        }
        urlopen.return_value = FakeResponse(
            {"choices": [{"message": {"content": json.dumps(answer)}}]}
        )
        model = OpenAICompatibleAnalysisModel(
            base_url="http://llm.internal/v1/",
            model="qwen-test",
            api_key="test-key",
        )

        result = model.generate("<edge_summary>{}</edge_summary>")

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/v1/chat/completions"))
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(
            result,
            AnalysisAnswer(
                root_cause=answer["root_cause"],
                evidence=("CASE-1",),
                recommendations=("Review pool limits",),
                uncertainty="Confirm with current metrics",
            ),
        )

    @patch("urllib.request.urlopen")
    def test_rejects_missing_or_malformed_analysis_fields(self, urlopen: Any) -> None:
        urlopen.return_value = FakeResponse(
            {"choices": [{"message": {"content": '{"root_cause":"unknown"}'}}]}
        )

        with self.assertRaisesRegex(AnalysisModelError, "fields mismatch"):
            OpenAICompatibleAnalysisModel("http://llm.internal", "qwen-test").generate(
                "prompt"
            )

    @patch("urllib.request.urlopen")
    def test_rejects_non_string_evidence(self, urlopen: Any) -> None:
        answer = {
            "root_cause": "unknown",
            "evidence": [1],
            "recommendations": [],
            "uncertainty": "not verified",
        }
        urlopen.return_value = FakeResponse(
            {"choices": [{"message": {"content": json.dumps(answer)}}]}
        )

        with self.assertRaisesRegex(AnalysisModelError, "evidence must be"):
            OpenAICompatibleAnalysisModel("http://llm.internal", "qwen-test").generate(
                "prompt"
            )


if __name__ == "__main__":
    unittest.main()