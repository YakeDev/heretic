"""Offline benchmark fixture and formal evaluation tests (no model download)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import benchmark_chat


class BenchmarkChatTests(unittest.TestCase):
    def test_all_cases_are_valid_and_categories_are_diverse(self) -> None:
        cases = benchmark_chat.load_cases()
        self.assertGreaterEqual(len(cases), 12)
        self.assertGreaterEqual(len({case["category"] for case in cases}), 7)
        self.assertTrue(any(len(case["turns"]) > 1 for case in cases))

    def test_only_format_not_factual_claims_are_autoscored(self) -> None:
        check = benchmark_chat.automatic_check
        self.assertEqual(check({"type": "number", "value": 42}, "42", ""), "pass")
        self.assertEqual(check({"type": "number", "value": 42}, "41", ""), "fail")
        self.assertEqual(
            check({"type": "contains", "value": "AZUR-47"}, "Code: AZUR-47", ""), "pass"
        )
        self.assertEqual(
            check(
                {"type": "json_fields", "value": {"ville": "Lubumbashi"}},
                '{"ville":"Lubumbashi"}',
                "",
            ),
            "pass",
        )
        self.assertEqual(check({"type": "different"}, "Bonjour.", "Bonjour."), "fail")
        self.assertEqual(check({"type": "different"}, "Salut.", "Bonjour."), "pass")
        self.assertEqual(check(None, "TCP est un réseau sans fil.", ""), "human_review")

    def test_runner_preserves_context_only_inside_case(self) -> None:
        calls = []
        responses = iter(["OK, AZUR-47.", "AZUR-47", "42"])

        def fake_api(path, token="", payload=None):
            if path.endswith("/generate"):
                assert payload is not None
                calls.append(payload["messages"])
                return {"request_id": "a" * 32}
            return {
                "state": "completed",
                "answer": next(responses),
                "generated_tokens": 2,
            }

        fixtures = [
            {
                "id": "memory",
                "category": "context",
                "title": "Memory",
                "turns": [
                    {"prompt": "Souviens-toi d'AZUR-47", "review": "Memory"},
                    {"prompt": "Quel est le code ?", "review": "AZUR-47"},
                ],
            },
            {
                "id": "math",
                "category": "math",
                "title": "Math",
                "turns": [{"prompt": "17+25 ?", "review": "42"}],
            },
        ]
        with patch.object(benchmark_chat, "api_request", side_effect=fake_api):
            results = benchmark_chat.run_cases(
                fixtures, "b" * 32, "token", "stable", 128
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            [item["role"] for item in calls[1]], ["user", "assistant", "user"]
        )
        self.assertEqual(calls[2], [{"role": "user", "content": "17+25 ?"}])
        self.assertEqual(calls[0][0]["content"], "Souviens-toi d'AZUR-47")


if __name__ == "__main__":
    unittest.main()
