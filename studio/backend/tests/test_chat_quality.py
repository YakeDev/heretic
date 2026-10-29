"""Safe, deterministic tests for chat answer settings and performance reports."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inference
from app import ChatGenerateRequest
from inference_worker import (
    CHAT_STYLES,
    chat_messages,
    finish_reason,
    validate_request,
)


class ChatQualityTests(unittest.TestCase):
    def test_style_presets_are_internal_and_preserve_user_history(self) -> None:
        original = [{"role": "user", "content": "Trois phrases, s'il te plaît."}]
        for style in CHAT_STYLES:
            history = chat_messages(original, style)
            self.assertEqual(history[0]["role"], "system")
            self.assertIn("français", history[0]["content"])
            self.assertEqual(history[1:], original)
            self.assertEqual(len(original), 1)

    def test_only_authorized_answer_styles_are_accepted(self) -> None:
        cmd = {
            "command": "generate",
            "messages": [{"role": "user", "content": "Bonjour."}],
            "max_new_tokens": 384,
            "style": "pedagogical",
        }
        self.assertTrue(validate_request(cmd))
        self.assertTrue(validate_request({**cmd, "style": "concise"}))
        self.assertFalse(validate_request({**cmd, "style": "system"}))
        self.assertFalse(validate_request({**cmd, "style": ""}))
        self.assertFalse(validate_request({**cmd, "max_new_tokens": 513}))
        self.assertFalse(validate_request({**cmd, "max_new_tokens": True}))

    def test_unknown_style_is_rejected_by_http_schema(self) -> None:
        with self.assertRaises(ValidationError):
            ChatGenerateRequest(
                messages=[{"role": "user", "content": "Bonjour."}],
                max_new_tokens=256,
                style="user-defined",
            )

    def test_eos_has_priority_over_token_limit(self) -> None:
        self.assertEqual(finish_reason(256, 256, 2, 2), "eos")
        self.assertEqual(finish_reason(256, 256, 5, [2, 3]), "length")
        self.assertEqual(finish_reason(16, 256, 4, 2), "unknown")
        self.assertEqual(finish_reason(11, 256, 3, [2, 3]), "eos")

    def test_reply_statistics_are_transmitted_and_private_file_removed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            job_root = Path(root)
            session_id = "a" * 32
            request_id = "b" * 32
            result = job_root / f"chat-{session_id}-{request_id}.json"
            result.write_text(
                json.dumps(
                    {
                        "state": "completed",
                        "answer": "Réponse locale",
                        "generated_tokens": 80,
                        "elapsed_seconds": 5.1,
                        "tokens_per_second": 15.7,
                        "finish_reason": "length",
                        "max_new_tokens": 80,
                    }
                ),
                encoding="utf-8",
            )
            session = {
                "session_id": session_id,
                "request_id": request_id,
                "process": Mock(),
            }
            with (
                patch.object(inference, "JOBS", job_root),
                patch.object(inference, "_session", session),
            ):
                response = inference.generation_status(session_id, request_id)
                self.assertEqual(response["state"], "completed")
                self.assertEqual(response["finish_reason"], "length")
                self.assertEqual(response["generated_tokens"], 80)
                self.assertEqual(response["tokens_per_second"], 15.7)
                self.assertEqual(response["elapsed_seconds"], 5.1)
                self.assertEqual(session["request_id"], None)
                self.assertFalse(result.exists())


if __name__ == "__main__":
    unittest.main()
