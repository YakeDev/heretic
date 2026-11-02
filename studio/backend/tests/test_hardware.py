"""Strictly offline tests for resource estimation and OS probe."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from fastapi.testclient import TestClient
from hardware import estimate_resources, system_resources


class ResourceEstimateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.model_id = "meta-llama/Llama-3.2-3B-Instruct"

    def test_nvidia_vram_uses_best_single_gpu_not_sum(self) -> None:
        info: dict[str, object] = {
            "disk_available_gb": 200,
            "ram_available_gb": 64,
            "nvidia_gpus": [
                {"name": "GPU-1", "memory_free_gb": 6, "memory_total_gb": 8},
                {"name": "GPU-2", "memory_free_gb": 6, "memory_total_gb": 8},
            ],
        }
        result = estimate_resources(self.model_id, "inference", "fp16", info)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["best_single_nvidia_free_gib"], 6)
        self.assertEqual(result["status"], "probably_insufficient")
        self.assertFalse(result["guaranteed"])

    def test_no_nvidia_is_not_mistaken_for_incompatibility(self) -> None:
        result = estimate_resources(
            self.model_id,
            "inference",
            "bnb_4bit",
            {"nvidia_gpus": [], "ram_available_gb": 32, "disk_available_gb": 100},
        )
        assert result is not None
        self.assertEqual(result["status"], "indeterminate")

    def test_sufficient_memory_is_only_a_candidate(self) -> None:
        result = estimate_resources(
            self.model_id,
            "inference",
            "fp16",
            {
                "nvidia_gpus": [{"memory_free_gb": 48, "memory_total_gb": 48}],
                "ram_available_gb": 64,
                "disk_available_gb": 100,
            },
        )
        assert result is not None
        self.assertEqual(result["status"], "candidate_only")
        self.assertFalse(result["guaranteed"])

    def test_disk_shortage_cannot_be_masked_by_gpu(self) -> None:
        result = estimate_resources(
            self.model_id,
            "inference",
            "fp16",
            {
                "nvidia_gpus": [{"memory_free_gb": 80, "memory_total_gb": 80}],
                "ram_available_gb": 64,
                "disk_available_gb": 1,
            },
        )
        assert result is not None
        self.assertEqual(result["status"], "probably_insufficient")

    def test_unrecognized_models_cannot_be_guessed(self) -> None:
        self.assertIsNone(
            estimate_resources(
                "unknown/unknown-8B", "inference", "fp16", {"nvidia_gpus": []}
            )
        )

    def test_optimization_estimate_exceeds_inference(self) -> None:
        info: dict[str, object] = {"nvidia_gpus": [], "disk_available_gb": 60}
        low = estimate_resources(self.model_id, "inference", "fp16", info)
        high = estimate_resources(self.model_id, "optimization", "fp16", info)
        assert low is not None and high is not None
        self.assertGreater(high["estimated_gpu_gib"], low["estimated_gpu_gib"])

    def test_endpoint_does_not_download_models(self) -> None:
        with (
            patch(
                "app.inspect_nvidia_gpus",
                return_value=[
                    {"name": "Mock", "memory_free_gb": 12, "memory_total_gb": 16}
                ],
            ),
            patch("catalog.httpx.get") as fetch,
        ):
            response = self.client.get(
                "/api/hardware/estimate",
                params={
                    "model_id": self.model_id,
                    "mode": "inference",
                    "precision": "fp16",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_id"], self.model_id)
        self.assertFalse(response.json()["guaranteed"])
        fetch.assert_not_called()

    def test_unknown_model_returns_404(self) -> None:
        self.assertEqual(
            self.client.get(
                "/api/hardware/estimate", params={"model_id": "unknown/nonexistent-8B"}
            ).status_code,
            404,
        )

    def test_invalid_precision_returns_422(self) -> None:
        self.assertEqual(
            self.client.get(
                "/api/hardware/estimate",
                params={"model_id": self.model_id, "precision": "arbitrary"},
            ).status_code,
            422,
        )

    def test_invalid_mode_returns_422(self) -> None:
        self.assertEqual(
            self.client.get(
                "/api/hardware/estimate",
                params={"model_id": self.model_id, "mode": "run_shell"},
            ).status_code,
            422,
        )

    @patch("hardware.psutil.disk_usage", side_effect=OSError("disk unavailable"))
    def test_failed_disk_probe_is_not_a_zero_disk_result(self, _: object) -> None:
        resources = system_resources(Path.cwd(), [])
        self.assertIsNone(resources["disk_available_gb"])


if __name__ == "__main__":
    unittest.main()
