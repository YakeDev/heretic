"""Software compatibility checks: offline and no actual torch import."""

import importlib.metadata
import subprocess
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from fastapi.testclient import TestClient
from software import inspect_software, installed_packages, nvidia_driver, torch_runtime


class SoftwareDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")

    def test_endpoint_is_read_only(self) -> None:
        with patch(
            "app.inspect_software",
            return_value={"compatibility": "not_verified", "read_only": True},
        ):
            response = self.client.get("/api/hardware/software")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["compatibility"], "not_verified")
        self.assertTrue(response.json()["read_only"])

    def test_missing_torch_skips_runtime_subprocess(self) -> None:
        with (
            patch("software.installed_packages", return_value=[]),
            patch("software.nvidia_driver", return_value={"status": "not_detected"}),
            patch("software.torch_runtime") as probe,
        ):
            result = inspect_software()
        probe.assert_not_called()
        self.assertEqual(result["torch_runtime"], {"status": "torch_not_installed"})

    def test_runtime_probe_has_timeout_and_isolated_python(self) -> None:
        cp = Mock(
            returncode=0,
            stdout=(
                '{"cuda_available":true,"mps_available":false,"cuda_devices":1,'
                '"cuda_build":"12.8","rocm_build":null}'
            ),
        )
        with patch("software.subprocess.run", return_value=cp) as run:
            result = torch_runtime()
        self.assertEqual(result["status"], "checked")
        self.assertTrue(result["cuda_available"])
        self.assertEqual(run.call_args.kwargs["timeout"], 15)
        self.assertEqual(run.call_args.args[0][:3], [sys.executable, "-I", "-c"])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch(
        "software.subprocess.run", side_effect=subprocess.TimeoutExpired("python", 15)
    )
    def test_runtime_timeout_is_not_compatibility_failure(self, _: Mock) -> None:
        self.assertEqual(torch_runtime(), {"status": "timeout"})

    def test_non_json_torch_probe_is_rejected(self) -> None:
        with patch(
            "software.subprocess.run", return_value=Mock(returncode=0, stdout="oops")
        ):
            self.assertEqual(torch_runtime(), {"status": "probe_failed"})

    def test_unsupported_probe_values_are_rejected(self) -> None:
        cp = Mock(
            returncode=0,
            stdout='{"cuda_available":"yes","mps_available":false,"cuda_devices":1}',
        )
        with patch("software.subprocess.run", return_value=cp):
            self.assertEqual(torch_runtime(), {"status": "probe_failed"})

    def test_nvidia_probe_has_fixed_arguments(self) -> None:
        cp = Mock(returncode=0, stdout="NVIDIA RTX, 560.12, 8192\n")
        with (
            patch("software.shutil.which", return_value="/usr/bin/nvidia-smi"),
            patch("software.subprocess.run", return_value=cp) as run,
        ):
            result = nvidia_driver()
        self.assertEqual(result["status"], "detected")
        gpus = cast(list[dict[str, object]], result["gpus"])
        self.assertEqual(gpus[0]["memory_total_gib"], 8.0)
        self.assertEqual(run.call_args.kwargs["timeout"], 4)
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/nvidia-smi")

    def test_driver_absent_is_not_nvidia_incompatibility(self) -> None:
        with patch("software.shutil.which", return_value=None):
            self.assertEqual(nvidia_driver()["status"], "not_detected")

    def test_versions_read_without_module_imports(self) -> None:
        def mocked_version(package: str) -> str:
            if package == "torch":
                return "2.9.0"
            raise importlib.metadata.PackageNotFoundError

        with patch("software.importlib.metadata.version", side_effect=mocked_version):
            versions = installed_packages()
        self.assertEqual(
            next(x for x in versions if x["package"] == "torch")["version"], "2.9.0"
        )
        self.assertIsNone(
            next(x for x in versions if x["package"] == "peft")["version"]
        )


if __name__ == "__main__":
    unittest.main()
