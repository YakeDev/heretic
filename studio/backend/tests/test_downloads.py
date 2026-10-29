"""Fully offline tests of download preflight, authorization and worker."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import downloads
from app import app
from download_worker import main as worker_main
from fastapi.testclient import TestClient


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(app)
        self.model = "Qwen/Qwen3-4B-Instruct-2507"
        self.origin = "http://127.0.0.1:5173"
        self.headers = {"Origin": self.origin, "X-Heretic-Token": downloads.nonce()}
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(downloads, "STORAGE", self.root / "models"),
            patch.object(downloads, "JOBS", self.root / "jobs"),
        ]
        for patched in self.patches:
            patched.start()
            self.addCleanup(patched.stop)
        downloads._plans.clear()
        downloads._jobs.clear()
        downloads._active_id = None

    def _info(self, files: list[tuple[str, int | None]] | None = None) -> SimpleNamespace:
        if files is None:
            files = [
                ("model.safetensors", 1000),
                ("config.json", 100),
                ("evil.py", 100),
                ("pytorch_model.bin", 100),
            ]
        return SimpleNamespace(
            sha="a" * 40,
            gated=False,
            siblings=[
                SimpleNamespace(rfilename=name, size=size) for name, size in files
            ],
        )

    @patch("downloads.HfApi")
    def test_preview_filters_executable_and_pinned_revision(self, api: Mock) -> None:
        api.return_value.model_info.return_value = self._info()
        result = self.client.post(
            "/api/downloads/preview",
            headers=self.headers,
            json={"model_id": self.model},
        )
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["file_count"], 2)
        self.assertEqual(body["revision"], "a" * 40)
        self.assertEqual(body["total_bytes"], 1100)
        files = downloads._plans[body["plan_id"]]["files"]
        self.assertEqual({item["path"] for item in files}, {"model.safetensors", "config.json"})
        api.return_value.model_info.assert_called_once_with(
            self.model, files_metadata=True, timeout=15
        )

    def test_only_curated_model_ids_allowed(self) -> None:
        r = self.client.post(
            "/api/downloads/preview",
            headers=self.headers,
            json={"model_id": "attacker/untrusted"},
        )
        self.assertEqual(r.status_code, 404)

    def test_rejects_cross_site_origin_and_csrf(self) -> None:
        response = self.client.get(
            "/api/downloads/session", headers={"Origin": "https://bad.example"}
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/api/downloads/preview",
            headers={"Origin": self.origin, "X-Heretic-Token": "wrong"},
            json={"model_id": self.model},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/api/downloads/preview",
            headers={"X-Heretic-Token": downloads.nonce()},
            json={"model_id": self.model},
        )
        self.assertEqual(response.status_code, 403)

    def test_session_allows_only_trusted_origin(self) -> None:
        result = self.client.get(
            "/api/downloads/session", headers={"Origin": self.origin}
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["token"], downloads.nonce())

    @patch("downloads.HfApi")
    def test_missing_file_size_is_blocked(self, api: Mock) -> None:
        api.return_value.model_info.return_value = self._info(
            [("model.safetensors", None), ("config.json", 100)]
        )
        result = self.client.post(
            "/api/downloads/preview",
            headers=self.headers,
            json={"model_id": self.model},
        )
        self.assertEqual(result.status_code, 422)

    @patch("downloads.HfApi")
    def test_no_safetensors_rejected(self, api: Mock) -> None:
        api.return_value.model_info.return_value = self._info(
            [("model.bin", 1000), ("config.json", 100)]
        )
        result = self.client.post(
            "/api/downloads/preview",
            headers=self.headers,
            json={"model_id": self.model},
        )
        self.assertEqual(result.status_code, 422)

    def test_traversal_and_remote_code_names_are_rejected(self) -> None:
        for value in ("../model.safetensors", "/root/model.safetensors", "x\\evil.safetensors", ".git/config.json", "remote.py", "pytorch_model.bin"):
            self.assertFalse(downloads.allowed_file(value), value)
        self.assertTrue(downloads.allowed_file("model-00001-of-00003.safetensors"))

    def test_confirmation_required_before_worker(self) -> None:
        downloads._plans["sample"] = {
            "id": "sample",
            "expires": float("inf"),
            "destination": str(self.root / "models" / "safe"),
            "model_id": self.model,
            "revision": "a" * 40,
            "files": [{"path": "model.safetensors", "size": 1000}],
            "total_bytes": 1000,
        }
        with patch("downloads.subprocess.Popen") as popen:
            response = self.client.post(
                "/api/downloads/start",
                headers=self.headers,
                json={"plan_id": "sample", "license_accepted": False},
            )
        self.assertEqual(response.status_code, 422)
        popen.assert_not_called()

    def test_start_and_status_are_bounded_to_active_job(self) -> None:
        downloads._plans["sample"] = {
            "id": "sample",
            "expires": float("inf"),
            "destination": str(self.root / "models" / "safe"),
            "model_id": self.model,
            "revision": "a" * 40,
            "files": [{"path": "model.safetensors", "size": 1000}],
            "total_bytes": 1000,
        }
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        with patch("downloads.subprocess.Popen", return_value=process) as popen:
            response = self.client.post(
                "/api/downloads/start",
                headers=self.headers,
                json={"plan_id": "sample", "license_accepted": True},
            )
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job_id"]
        self.assertEqual(popen.call_args.args[0][0], sys.executable)
        self.assertEqual(popen.call_args.args[0][1], "-I")
        self.assertNotIn("shell", popen.call_args.kwargs)
        status = self.client.get("/api/downloads/" + job_id, headers=self.headers)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "downloading")
        response = self.client.post(
            "/api/downloads/start",
            headers=self.headers,
            json={"plan_id": "sample", "license_accepted": True},
        )
        self.assertEqual(response.status_code, 422)

    def test_worker_uses_only_pinned_revision_and_static_assets(self) -> None:
        destination = self.root / "model"
        status_file = self.root / "progress.json"
        payload = {
            "model_id": self.model,
            "revision": "a" * 40,
            "destination": str(destination),
            "status_file": str(status_file),
            "total_bytes": 1000,
            "files": [{"path": "model.safetensors", "size": 1000}],
        }
        with (
            patch("download_worker.sys.stdin", io.StringIO(json.dumps(payload))),
            patch("download_worker.hf_hub_download", return_value="/cache/file") as fetch,
        ):
            result = worker_main()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(status_file.read_text())["state"], "completed")
        fetch.assert_called_once_with(
            repo_id=self.model,
            filename="model.safetensors",
            revision="a" * 40,
            local_dir=destination,
            token=None,
        )


if __name__ == "__main__":
    unittest.main()
