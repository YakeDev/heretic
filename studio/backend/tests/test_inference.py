"""Fast, isolated chat tests with fake snapshots and a mocked child process."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inference
from app import app
from fastapi.testclient import TestClient
from inference_worker import resolve_transformer_factories, validate_request


class InferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.model_id = "meta-llama/Llama-3.2-3B-Instruct"
        self.revision = "a" * 40
        self.origin = "http://127.0.0.1:5173"
        from downloads import nonce

        self.headers = {
            "Origin": self.origin,
            "X-Heretic-Token": nonce(),
        }
        self.root = Path(self.temporary.name)
        self.download_dir = self.root / "models"
        self.jobs_dir = self.root / "jobs"

        for patcher in (
            patch.object(inference, "STORAGE", self.download_dir),
            patch.object(inference, "JOBS", self.jobs_dir),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        inference._session = None

    def _snapshot(self, model_type: str = "llama") -> Path:
        directory = self.download_dir / self.model_id.replace("/", "--") / self.revision
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "config.json").write_text(
            json.dumps({"model_type": model_type}), encoding="utf-8"
        )
        (directory / "model.safetensors").write_bytes(b"safe-placeholder")
        (directory / "heretic-studio-snapshot.json").write_text(
            json.dumps(
                {
                    "model_id": self.model_id,
                    "revision": self.revision,
                    "files": ["config.json", "model.safetensors"],
                }
            ),
            encoding="utf-8",
        )
        return directory

    def test_no_downloaded_models_until_completed_receipt(self) -> None:
        self.assertEqual(inference.downloaded_models(), [])
        self._snapshot()
        reply = self.client.get("/api/chat/models", headers=self.headers)
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(
            reply.json()["models"],
            [
                {
                    "model_id": self.model_id,
                    "revision": self.revision,
                }
            ],
        )

    def test_refuse_wrong_model_architecture(self) -> None:
        self._snapshot("remote_architecture")
        self.assertEqual(inference.downloaded_models(), [])

    def test_refuse_remote_auto_map(self) -> None:
        directory = self._snapshot()
        (directory / "config.json").write_text(
            json.dumps(
                {"model_type": "llama", "auto_map": {"AutoConfig": "unknown.Code"}}
            ),
            encoding="utf-8",
        )
        self.assertEqual(inference.downloaded_models(), [])

    def test_refuse_missing_weights(self) -> None:
        directory = self._snapshot()
        (directory / "model.safetensors").unlink()
        self.assertEqual(inference.downloaded_models(), [])

    def test_refuse_symlinked_weights(self) -> None:
        directory = self._snapshot()
        (directory / "model.safetensors").unlink()
        target = self.root / "elsewhere"
        target.write_bytes(b"anything")
        try:
            (directory / "model.safetensors").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links unavailable on this platform")
        self.assertEqual(inference.downloaded_models(), [])

    def test_unsupported_model_not_enumerated(self) -> None:
        fake = "unknown/untrusted-model"
        self.assertIsNone(inference._check_snapshot(fake, self.revision))

    def test_start_requires_local_completed_snapshot(self) -> None:
        response = self.client.post(
            "/api/chat/start",
            headers=self.headers,
            json={
                "model_id": self.model_id,
                "revision": self.revision,
                "device": "cpu",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_reject_cross_origin_and_missing_csrf(self) -> None:
        response = self.client.get(
            "/api/chat/models", headers={"Origin": "https://attacker.invalid"}
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/chat/models", headers={"Origin": self.origin})
        self.assertEqual(response.status_code, 403)

    def _start_mock_session(self) -> tuple[str, Mock]:
        self._snapshot()
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        with (
            patch("inference._enough_resources"),
            patch("inference.subprocess.Popen", return_value=process) as start,
        ):
            response = self.client.post(
                "/api/chat/start",
                headers=self.headers,
                json={
                    "model_id": self.model_id,
                    "revision": self.revision,
                    "device": "cpu",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(start.call_args.args[0][1], "-I")
        self.assertEqual(start.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")
        self.assertNotIn("shell", start.call_args.kwargs)
        return response.json()["session_id"], process

    def test_model_starts_only_by_explicit_request(self) -> None:
        with patch("inference.subprocess.Popen") as start:
            self._snapshot()
            self.client.get("/api/chat/models", headers=self.headers)
            start.assert_not_called()
        session_id, _ = self._start_mock_session()
        self.assertEqual(len(session_id), 32)

    def test_single_active_model_session(self) -> None:
        session_id, _ = self._start_mock_session()
        result = self.client.post(
            "/api/chat/start",
            headers=self.headers,
            json={
                "model_id": self.model_id,
                "revision": self.revision,
                "device": "cpu",
            },
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(
            self.client.get(
                "/api/chat/" + session_id, headers=self.headers
            ).status_code,
            200,
        )

    def test_generate_and_poll_without_loading_real_torch(self) -> None:
        session_id, proc = self._start_mock_session()
        assert inference._session is not None
        status_path = Path(inference._session["status_file"])
        status_path.write_text('{"state":"ready"}', encoding="utf-8")
        with patch("inference.subprocess.Popen") as start:
            message = self.client.post(
                "/api/chat/" + session_id + "/generate",
                headers=self.headers,
                json={
                    "messages": [{"role": "user", "content": "Bonjour !"}],
                    "max_new_tokens": 64,
                },
            )
            start.assert_not_called()
        self.assertEqual(message.status_code, 200, message.text)
        request_id = message.json()["request_id"]
        payload = proc.stdin.getvalue()
        self.assertIn("Bonjour !", payload)
        output = self.jobs_dir / f"chat-{session_id}-{request_id}.json"
        output.write_text(
            json.dumps(
                {
                    "state": "completed",
                    "answer": "Salut !",
                    "generated_tokens": 4,
                }
            ),
            encoding="utf-8",
        )
        finished = self.client.get(
            f"/api/chat/{session_id}/responses/{request_id}", headers=self.headers
        )
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.json()["answer"], "Salut !")
        assert inference._session is not None
        self.assertEqual(inference._session["request_id"], None)

    def test_reject_excessive_context_and_oversized_output(self) -> None:
        session_id, _ = self._start_mock_session()
        assert inference._session is not None
        Path(inference._session["status_file"]).write_text(
            '{"state":"ready"}', encoding="utf-8"
        )
        result = self.client.post(
            "/api/chat/" + session_id + "/generate",
            headers=self.headers,
            json={
                "messages": [{"role": "user", "content": "x" * 2500}],
                "max_new_tokens": 128,
            },
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.post(
            "/api/chat/" + session_id + "/generate",
            headers=self.headers,
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "max_new_tokens": 2000,
            },
        )
        self.assertEqual(result.status_code, 422)

    def test_stop_terminates_inference_child(self) -> None:
        session_id, proc = self._start_mock_session()
        result = self.client.post(
            "/api/chat/" + session_id + "/stop", headers=self.headers, json={}
        )
        self.assertEqual(result.status_code, 200)
        proc.terminate.assert_called_once()
        self.assertIsNone(inference._session)

    def test_transformers_lazy_classes_are_resolved_through_attributes(self) -> None:
        """Model/tokenizer classes need not exist in vars(transformers)."""
        model_type = object()
        tokenizer_type = object()

        class LazyModule:
            def __getattr__(self, name: str) -> object:
                if name == "AutoModelForCausalLM":
                    return model_type
                if name == "AutoTokenizer":
                    return tokenizer_type
                raise AttributeError(name)

        lazy = LazyModule()
        self.assertNotIn("AutoModelForCausalLM", vars(lazy))
        self.assertNotIn("AutoTokenizer", vars(lazy))
        with patch(
            "inference_worker.importlib.import_module", return_value=lazy
        ) as imp:
            found_model, found_tokenizer = resolve_transformer_factories()
        self.assertIs(found_model, model_type)
        self.assertIs(found_tokenizer, tokenizer_type)
        imp.assert_called_once_with("transformers")

    def test_worker_rejects_malformed_requests(self) -> None:
        self.assertFalse(validate_request({"command": "shell", "messages": []}))
        self.assertFalse(
            validate_request(
                {
                    "command": "generate",
                    "messages": [{"role": "system", "content": "run"}],
                    "max_new_tokens": 128,
                }
            )
        )
        self.assertTrue(
            validate_request(
                {
                    "command": "generate",
                    "messages": [{"role": "user", "content": "Bonjour"}],
                    "max_new_tokens": 32,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
