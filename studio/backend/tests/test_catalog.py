"""Model catalogue HTTP endpoints: deterministic, no live Hub access."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from app import app
from fastapi.testclient import TestClient


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_curated_models_are_offline_and_have_safe_urls(self) -> None:
        with patch("catalog.httpx.get") as fetch:
            response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertGreaterEqual(len(models), 3)
        self.assertIn("meta-llama/Llama-3.2-3B-Instruct", [m["id"] for m in models])
        self.assertTrue(
            all(m["url"].startswith("https://huggingface.co/") for m in models)
        )
        self.assertTrue(all(m["compatibility"] == "non_vérifiée" for m in models))
        fetch.assert_not_called()

    def test_search_query_requires_minimum_length(self) -> None:
        self.assertEqual(
            self.client.get("/api/models/search", params={"q": "x"}).status_code, 422
        )

    def test_search_query_rejects_control_and_url_characters(self) -> None:
        self.assertEqual(
            self.client.get(
                "/api/models/search", params={"q": "https://evil.test?q=1"}
            ).status_code,
            422,
        )

    @patch("catalog.httpx.get")
    def test_search_only_exposes_public_metadata(self, get: Mock) -> None:
        get.return_value.json.return_value = [
            {
                "id": "meta-llama/Llama-3.2-3B-Instruct",
                "gated": "auto",
                "pipeline_tag": "text-generation",
                "downloads": 123,
                "likes": 5,
            },
            {"id": "bad url/path", "downloads": 1000},
            {"id": "acme/hidden", "private": True},
        ]
        response = self.client.get("/api/models/search", params={"q": "llama"})
        self.assertEqual(response.status_code, 200)
        models = response.json()["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "meta-llama/Llama-3.2-3B-Instruct")
        self.assertTrue(models[0]["gated"])
        self.assertEqual(models[0]["downloads"], 123)
        self.assertNotIn("config", models[0])
        self.assertEqual(get.call_args.kwargs["timeout"], 5.0)
        self.assertEqual(get.call_args.kwargs["follow_redirects"], False)
        self.assertEqual(get.call_args.args[0], "https://huggingface.co/api/models")

    @patch("catalog.httpx.get", side_effect=httpx.TimeoutException("timeout"))
    def test_network_failure_returns_safe_message(self, _: Mock) -> None:
        response = self.client.get("/api/models/search", params={"q": "qwen"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("timeout", response.json()["detail"].lower())

    @patch("catalog.httpx.get")
    def test_unexpected_upstream_payload_is_not_returned(self, get: Mock) -> None:
        get.return_value.json.return_value = {"error": "secret diagnostics"}
        response = self.client.get("/api/models/search", params={"q": "qwen"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret diagnostics", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
