"""Resident, bounded, local-only Transformers inference worker.

No cloud model calls, no user-selected file paths, no HF remote-code trust.
Execution happens only after an explicit start request.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

MAX_MESSAGES = 12
MAX_CHARACTERS = 6000
MAX_TOKENS = 192


def resolve_transformer_factories() -> tuple[Any, Any]:
    """Resolve classes through module attributes (Transformers is lazy-loaded).

    Accessing vars(transformers) bypasses its __getattr__ hook and can
    raise KeyError even when Transformers is correctly installed.
    """
    module = importlib.import_module("transformers")
    model_name, tokenizer_name = "AutoModelForCausalLM", "AutoTokenizer"
    return getattr(module, model_name), getattr(module, tokenizer_name)


def _status(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="reply-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_request(command: object) -> bool:
    if not isinstance(command, dict) or command.get("command") != "generate":
        return False
    messages = command.get("messages")
    tokens = command.get("max_new_tokens")
    if not isinstance(tokens, int) or not 1 <= tokens <= MAX_TOKENS:
        return False
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        return False
    total = 0
    for item in messages:
        if not isinstance(item, dict) or set(item) != {"role", "content"}:
            return False
        if item["role"] not in {"user", "assistant"}:
            return False
        content = item["content"]
        if not isinstance(content, str) or not content.strip() or len(content) > 2000:
            return False
        total += len(content)
    return total <= MAX_CHARACTERS and messages[-1]["role"] == "user"


def main() -> int:
    # The parent explicitly sets offline mode; repeat for stand-alone safety.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    line = sys.stdin.readline()
    try:
        request = json.loads(line)
        model_dir = Path(request["model_dir"])
        status_path = Path(request["status_file"])
        device = request["device"]
        if device not in {"cpu", "cuda"}:
            return 2
    except (ValueError, TypeError, KeyError, OSError):
        return 2

    _status(status_path, {"state": "loading", "message": "Chargement du modèle local…"})
    phase = "dépendances"
    try:
        # Optional heavy dependencies: intentionally installed separately from Studio.
        torch = importlib.import_module("torch")
        AutoModelForCausalLM, AutoTokenizer = resolve_transformer_factories()

        phase = "CUDA"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")

        phase = "tokenizer"
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            local_files_only=True,
            trust_remote_code=False,
        )
        phase = "poids du modèle"
        model = AutoModelForCausalLM.from_pretrained(
            model_dir,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="cuda:0" if device == "cuda" else "cpu",
        )
        model.eval()
        phase = "modèle de conversation"
        if tokenizer.chat_template is None:
            raise RuntimeError("Missing chat template")
    except Exception as exc:
        # Expose only the phase and the exception class, never local paths
        # or raw dependency exceptions that could contain sensitive text.
        _status(
            status_path,
            {
                "state": "failed",
                "message": (
                    f"Chargement échoué à l'étape {phase} "
                    f"({type(exc).__name__}). "
                    "Vérifie la compatibilité de l'environnement local."
                ),
            },
        )
        return 1

    _status(
        status_path, {"state": "ready", "message": "Modèle prêt pour le chat local."}
    )
    for line in sys.stdin:
        try:
            command = json.loads(line)
            if not validate_request(command):
                continue
            output = Path(command["output"])
            _status(status_path, {"state": "generating"})
            try:
                tokenized = tokenizer.apply_chat_template(
                    command["messages"],
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                )
                if tokenized.shape[-1] > 1536:
                    raise ValueError("Context too long")
                ids = tokenized.to(model.device)
                beginning = time.monotonic()
                with torch.inference_mode():
                    generated = model.generate(
                        ids,
                        max_new_tokens=command["max_new_tokens"],
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                new_tokens = generated[0, ids.shape[-1] :]
                answer = tokenizer.decode(new_tokens, skip_special_tokens=True)
                _status(
                    output,
                    {
                        "state": "completed",
                        "answer": answer[:12000],
                        "generated_tokens": len(new_tokens),
                        "elapsed_seconds": round(time.monotonic() - beginning, 2),
                    },
                )
            except Exception:
                _status(
                    output,
                    {
                        "state": "failed",
                        "message": "Génération impossible ou mémoire épuisée.",
                    },
                )
            finally:
                _status(status_path, {"state": "ready"})
        except (ValueError, TypeError, KeyError, OSError):
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
