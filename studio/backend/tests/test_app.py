"""Fast, model-free API smoke tests."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from fastapi.testclient import TestClient


class StudioApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def test_health_is_explicitly_read_only(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "local-download-alpha")

    def test_project_reads_existing_package_metadata(self) -> None:
        response = self.client.get("/api/project")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "heretic-llm")

    def test_system_without_nvidia_is_not_reported_as_incompatible(self) -> None:
        with patch("app.inspect_nvidia_gpus", return_value=[]):
            response = self.client.get("/api/system")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nvidia_gpus"], [])
        self.assertIn("NVIDIA", response.json()["gpu_detection_note"])


if __name__ == "__main__":
    unittest.main()
