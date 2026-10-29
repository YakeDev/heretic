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
MAX_TOKENS = 512
CHAT_STYLES = {
    "neutral": (
        "Tu es un assistant en français. Réponds directement à la question, "
        "respecte le nombre de phrases demandé et signale ton incertitude "
        "plutôt que d'inventer."
    ),
    "concise": (
        "Réponds en français, de façon brève et précise. Respecte strictement "
        "les contraintes de longueur et le nombre de phrases demandé. "
        "Si tu n'es pas certain, dis-le."
    ),
    "pedagogical": (
        "Explique en français avec des termes exacts et des exemples simples. "
        "Respecte toute limite de longueur ou de phrases donnée par l'utilisateur. "
        "N'invente pas les faits dont tu n'es pas certain."
    ),
}



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
    style = command.get("style", "neutral")
    if style not in CHAT_STYLES:
        return False
    if type(tokens) is not int or not 1 <= tokens <= MAX_TOKENS:
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


def prepare_chat_inputs(
    tokenizer: Any, messages: list[dict[str, str]], device: Any
) -> tuple[Any, int]:
    """Prepare named model inputs for Transformers 4.x *and* 5.x.

    Transformers 5 returns a BatchEncoding by default. Treating it as a
    tensor (reading .shape or passing it positionally to generate) fails.
    """
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )
    if "input_ids" not in inputs:
        raise ValueError("Missing input_ids")
    length = inputs["input_ids"].shape[-1]
    if length > 1536:
        raise ValueError("Context too long")
    return inputs.to(device), length


def finish_reason(
    count: int, maximum: int, last_token: int, eos_ids: object
) -> str:
    """Distinguish reaching the generation cap from EOS termination."""
    if isinstance(eos_ids, int):
        endings = {eos_ids}
    elif isinstance(eos_ids, (list, tuple)):
        endings = {x for x in eos_ids if isinstance(x, int)}
    else:
        endings = set()
    if last_token in endings:
        return "eos"
    if count >= maximum:
        return "length"
    return "unknown"


def chat_messages(messages: list[dict[str, str]], style: str) -> list[dict[str, str]]:
    """Prepend a fixed, local instruction; never accept arbitrary system roles."""
    return [{"role": "system", "content": CHAT_STYLES[style]}, *messages]


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
            phase = "tokenisation"
            try:
                inputs, prompt_length = prepare_chat_inputs(
                    tokenizer,
                    chat_messages(command["messages"], command.get("style", "neutral")),
                    model.device
                )
                phase = "génération"
                beginning = time.monotonic()
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        max_new_tokens=command["max_new_tokens"],
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                phase = "décodage"
                new_tokens = generated[0, prompt_length:]
                answer = tokenizer.decode(new_tokens, skip_special_tokens=True)
                elapsed = time.monotonic() - beginning
                count = len(new_tokens)
                ending = getattr(model.generation_config, "eos_token_id", None)
                if ending is None:
                    ending = tokenizer.eos_token_id
                reason = finish_reason(
                    count, command["max_new_tokens"], new_tokens[-1].item(), ending
                ) if count else "unknown"
                _status(
                    output,
                    {
                        "state": "completed",
                        "answer": answer[:12000],
                        "generated_tokens": count,
                        "elapsed_seconds": round(elapsed, 2),
                        "tokens_per_second": round(count / elapsed, 1) if elapsed > 0 else 0,
                        "finish_reason": reason,
                        "max_new_tokens": command["max_new_tokens"],
                    },
                )
            except Exception as exc:
                # Only controlled phase and exception class, never raw exception
                # strings, model content, user prompts or local filesystem paths.
                error_name = type(exc).__name__[:64]
                _status(
                    output,
                    {
                        "state": "failed",
                        "phase": phase,
                        "error_type": error_name,
                        "message": (
                            f"Échec à l'étape {phase} ({error_name}). "
                            "Réessaie ou vérifie l'environnement local."
                        ),
                    },
                )
            finally:
                _status(status_path, {"state": "ready"})
        except (ValueError, TypeError, KeyError, OSError):
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
