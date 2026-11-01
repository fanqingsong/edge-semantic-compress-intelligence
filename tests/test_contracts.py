import unittest

from edge_semantic_compress_intelligence.shared.contract import ContractError, EdgeEvent


class EdgeEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_event = {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-11-01T10:30:00Z",
            "service": "payments",
            "target_ip": "192.0.2.10",
            "target_port": 5432,
            "error_code": "ERR-42",
            "summary": "Database connection timed out",
        }

    def test_round_trip_json(self) -> None:
        event = EdgeEvent.from_mapping(self.valid_event)

        self.assertEqual(EdgeEvent.from_json(event.to_json()), event)
        self.assertEqual(event.schema_version, "1.0")

    def test_target_ip_must_be_valid(self) -> None:
        with self.assertRaisesRegex(ContractError, "valid IP"):
            EdgeEvent.from_mapping({**self.valid_event, "target_ip": "not-an-ip"})

    def test_target_port_must_be_in_range(self) -> None:
        with self.assertRaisesRegex(ContractError, "1 to 65535"):
            EdgeEvent.from_mapping({**self.valid_event, "target_port": 65536})

    def test_timestamp_must_include_timezone(self) -> None:
        with self.assertRaisesRegex(ContractError, "timezone"):
            EdgeEvent.from_mapping(
                {**self.valid_event, "timestamp": "2026-11-01T10:30:00"}
            )

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown fields"):
            EdgeEvent.from_mapping({**self.valid_event, "raw_log": "private log"})

    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "valid JSON"):
            EdgeEvent.from_json("{")


if __name__ == "__main__":
    unittest.main()