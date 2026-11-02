"""Offline verification of recovery; no Hugging Face API or model execution."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import recover_snapshot as recover


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = self.root / "models"
        self.jobs = self.root / "jobs"
        self.snapshot = self.storage / "Qwen--Qwen2.5-0.5B-Instruct" / ("a" * 40)
        self.snapshot.mkdir(parents=True)
        self.jobs.mkdir()
        self.payloads: dict[str, bytes] = {}
        for name in recover.EXPECTED_FILES:
            content = (
                b'{"model_type":"qwen2"}'
                if name == "config.json"
                else f"fake content for {name}".encode()
            )
            self.payloads[name] = content
            file_path = self.snapshot / name
            file_path.write_bytes(content)
            meta_path = (
                self.snapshot
                / ".cache"
                / "huggingface"
                / "download"
                / f"{name}.metadata"
            )
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            if name == "model.safetensors":
                etag = hashlib.sha256(content).hexdigest()
            else:
                etag = hashlib.sha1(
                    f"blob {len(content)}\0".encode() + content
                ).hexdigest()
            meta_path.write_text(f"{'a' * 40}\n{etag}\n1234.5\n", encoding="utf-8")
        self.total = sum(map(len, self.payloads.values()))
        (self.jobs / "sample.json").write_text(
            json.dumps(
                {
                    "total_bytes": self.total,
                    "total_files": 8,
                    "completed_files": 7,
                    "state": "downloading",
                }
            ),
            encoding="utf-8",
        )
        self.size_patch = patch.object(recover, "EXPECTED_TOTAL_BYTES", self.total)
        self.size_patch.start()
        self.addCleanup(self.size_patch.stop)

    def test_full_hash_verification_creates_receipt_only_when_repairing(self) -> None:
        data = recover.verify_snapshot(self.storage, self.jobs)
        self.assertEqual(len(data["files"]), 8)
        self.assertFalse((self.snapshot / "heretic-studio-snapshot.json").exists())
        receipt = recover.repair_snapshot(self.storage, self.jobs)
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(saved["revision"], "a" * 40)
        self.assertEqual(set(saved["files"]), recover.EXPECTED_FILES)

    def test_corrupted_weight_with_same_size_fails(self) -> None:
        path = self.snapshot / "model.safetensors"
        content = path.read_bytes()
        path.write_bytes(b"Z" + content[1:])
        with self.assertRaisesRegex(recover.RecoveryError, "corrompu"):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_missing_metadata_fails(self) -> None:
        metadata = (
            self.snapshot
            / ".cache"
            / "huggingface"
            / "download"
            / "model.safetensors.metadata"
        )
        metadata.unlink()
        with self.assertRaisesRegex(recover.RecoveryError, "manquantes"):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_mismatched_revision_fails(self) -> None:
        metadata = (
            self.snapshot
            / ".cache"
            / "huggingface"
            / "download"
            / "model.safetensors.metadata"
        )
        raw = metadata.read_text(encoding="utf-8")
        metadata.write_text("b" * 40 + raw[40:], encoding="utf-8")
        with self.assertRaisesRegex(recover.RecoveryError, "Révision"):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_incomplete_manifest_fails(self) -> None:
        (self.snapshot / "vocab.json").unlink()
        with self.assertRaisesRegex(recover.RecoveryError, "incomplets"):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_no_matching_job_fails(self) -> None:
        (self.jobs / "sample.json").unlink()
        with self.assertRaisesRegex(recover.RecoveryError, "trace locale"):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_unexpected_remote_code_fails(self) -> None:
        path = self.snapshot / "config.json"
        path.write_bytes(b'{"model_type":"qwen2","auto_map":{"A":"remote"}}')
        with self.assertRaises(recover.RecoveryError):
            recover.verify_snapshot(self.storage, self.jobs)

    def test_existing_receipt_is_not_overwritten(self) -> None:
        existing = self.snapshot / "heretic-studio-snapshot.json"
        existing.write_text('{"old":"data"}', encoding="utf-8")
        with self.assertRaisesRegex(recover.RecoveryError, "déjà un reçu"):
            recover.repair_snapshot(self.storage, self.jobs)
        self.assertEqual(existing.read_text(encoding="utf-8"), '{"old":"data"}')


if __name__ == "__main__":
    unittest.main()
