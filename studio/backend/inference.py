"""Single-session, local-only model chat orchestration.

No model loading in the API process. The resident inference child is optional:
users install the heavy dependencies separately and explicitly start a session.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from catalog import CURATED_MODELS
from downloads import JOBS, STORAGE, allowed_file
from hardware import GIB, system_resources

SUPPORTED_MODELS = {
    "meta-llama/Llama-3.2-3B-Instruct": "llama",
    "meta-llama/Meta-Llama-3.1-8B-Instruct": "llama",
    "Qwen/Qwen3-4B-Instruct-2507": "qwen3",
    "mistralai/Mistral-7B-Instruct-v0.3": "mistral",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_PROMPT_CHARS = 6000
MAX_MESSAGES = 12
MAX_NEW_TOKENS = 192

_lock = threading.RLock()
_session: dict[str, Any] | None = None


class InferenceError(Exception):
    """Error text may be returned to the local UI."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _check_snapshot(model_id: str, revision: str) -> Path | None:
    """Accept only snapshots created by the completed downloader receipt."""
    if model_id not in SUPPORTED_MODELS or SHA.fullmatch(revision) is None:
        return None
    folder = STORAGE / model_id.replace("/", "--")
    path = folder / revision
    if (
        STORAGE.is_symlink()
        or folder.is_symlink()
        or not path.is_dir()
        or path.is_symlink()
    ):
        return None
    receipt = path / "heretic-studio-snapshot.json"
    if receipt.is_symlink() or not receipt.is_file():
        return None
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("model_id") != model_id or data.get("revision") != revision:
        return None
    names = data.get("files")
    if not isinstance(names, list) or not 1 <= len(names) <= 350:
        return None
    if len(names) != len(set(x for x in names if isinstance(x, str))):
        return None
    if "config.json" not in names or not any(
        isinstance(x, str) and x.endswith(".safetensors") for x in names
    ):
        return None
    for name in names:
        if not isinstance(name, str) or not allowed_file(name):
            return None
        item = path / name
        # No symlink in any filename component, even if its target is local.
        parent = item
        while parent != path:
            if parent.is_symlink():
                return None
            parent = parent.parent
        if not item.is_file():
            return None
    try:
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(config, dict) or "auto_map" in config:
        return None
    if config.get("model_type") != SUPPORTED_MODELS[model_id]:
        return None
    return path


def downloaded_models() -> list[dict[str, str]]:
    """Inspect only curated snapshot directories; never run model code."""
    found: list[dict[str, str]] = []
    for model in CURATED_MODELS:
        model_id = model["id"]
        if model_id not in SUPPORTED_MODELS:
            continue
        folder = STORAGE / model_id.replace("/", "--")
        if not folder.is_dir() or folder.is_symlink():
            continue
        for revision in sorted(folder.iterdir()):
            if _check_snapshot(model_id, revision.name) is not None:
                found.append({"model_id": model_id, "revision": revision.name})
    return found[:50]


def _read_status(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(value, dict) and value.get("state") in {
        "loading", "ready", "failed", "generating", "completed",
    }:
        return value
    return None


def _current_status(session: dict[str, Any]) -> dict[str, object]:
    status = _read_status(Path(session["status_file"]))
    process: subprocess.Popen[str] = session["process"]
    if process.poll() is not None and (status is None or status.get("state") in {"loading", "ready", "generating"}):
        state = "stopped"
        message = "Le processus du modèle s'est arrêté. Vérifie la mémoire disponible."
    else:
        state = status.get("state", "loading") if status else "loading"
        message = status.get("message") if status else None
    return {
        "session_id": session["session_id"],
        "model_id": session["model_id"],
        "revision": session["revision"],
        "device": session["device"],
        "state": state,
        "message": message,
    }


def _enough_resources(model_id: str, device: str) -> None:
    from app import inspect_nvidia_gpus

    info = system_resources(STORAGE, inspect_nvidia_gpus())
    model = next(m for m in CURATED_MODELS if m["id"] == model_id)
    params_billions = float(model["parameters"].rstrip("B"))
    if device == "cpu":
        # Inference on CPU uses fp32, not the fp16 UI heuristic.
        needed_gib = params_billions * 4 * 10**9 / GIB * 1.4 + 5
        ram = info.get("ram_available_gb")
        if not isinstance(ram, (int, float)) or ram < needed_gib:
            raise InferenceError(
                "RAM disponible trop faible pour le chargement CPU expérimental.", 422
            )
    else:
        gpus = info.get("nvidia_gpus")
        if not isinstance(gpus, list) or not gpus:
            raise InferenceError("Aucun GPU NVIDIA détecté pour CUDA.", 422)
        recommended = params_billions * 2 * 10**9 / GIB * 1.3 + 2
        best_free = max(
            (
                float(gpu.get("memory_free_gb", 0))
                for gpu in gpus
                if isinstance(gpu, dict)
            ),
            default=0,
        )
        if best_free < recommended:
            raise InferenceError("VRAM NVIDIA libre inférieure au budget estimé.", 422)


def start_session(model_id: str, revision: str, device: str) -> dict[str, object]:
    global _session

    if device not in {"cpu", "cuda"}:
        raise InferenceError("Périphérique inconnu.", 422)
    model_dir = _check_snapshot(model_id, revision)
    if model_dir is None:
        raise InferenceError(
            "Modèle local absent ou snapshot non vérifié. Télécharge-le depuis Studio.", 404
        )
    with _lock:
        if _session is not None and _session["process"].poll() is None:
            raise InferenceError("Une autre session de modèle est déjà ouverte.", 409)
        _enough_resources(model_id, device)

        session_id = uuid.uuid4().hex
        status_file = JOBS / f"chat-{session_id}-status.json"
        JOBS.mkdir(parents=True, exist_ok=True)
        worker_file = Path(__file__).with_name("inference_worker.py")
        # Local-only transport + offline model loading; never run repository code.
        env = os.environ.copy()
        env.update({
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        })
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", str(worker_file)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                env=env,
            )
            if proc.stdin is None:
                raise OSError("Missing worker stdin")
            proc.stdin.write(
                json.dumps({
                    "model_dir": str(model_dir),
                    "status_file": str(status_file),
                    "device": device,
                }) + "\n"
            )
            proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            if "proc" in locals() and proc.poll() is None:
                proc.terminate()
            raise InferenceError("Démarrage du modèle impossible.", 503) from exc

        _session = {
            "session_id": session_id,
            "model_id": model_id,
            "revision": revision,
            "device": device,
            "status_file": str(status_file),
            "process": proc,
            "request_id": None,
        }
        return _current_status(_session)


def session_status(session_id: str) -> dict[str, object]:
    with _lock:
        if _session is None or not secrets.compare_digest(
            _session["session_id"], session_id
        ):
            raise InferenceError("Session de modèle introuvable.", 404)
        return _current_status(_session)


def _validate_messages(messages: object) -> list[dict[str, str]]:
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise InferenceError("Historique trop long ou vide.", 422)
    validated: list[dict[str, str]] = []
    total = 0
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise InferenceError("Format de message invalide.", 422)
        role = message["role"]
        content = message["content"]
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise InferenceError("Rôle ou contenu non autorisé.", 422)
        if not content.strip() or len(content) > 2000 or "\x00" in content:
            raise InferenceError("Message trop long, vide ou invalide.", 422)
        total += len(content)
        if total > MAX_PROMPT_CHARS:
            raise InferenceError("Conversation trop longue pour ce premier test.", 422)
        validated.append({"role": role, "content": content})
    if validated[-1]["role"] != "user":
        raise InferenceError("Le dernier message doit provenir de l'utilisateur.", 422)
    return validated


def generate(
    session_id: str, messages: object, max_new_tokens: int
) -> dict[str, object]:
    if not isinstance(max_new_tokens, int) or not 1 <= max_new_tokens <= MAX_NEW_TOKENS:
        raise InferenceError("Longueur de réponse hors limites.", 422)
    validated = _validate_messages(messages)
    with _lock:
        if _session is None or _session["session_id"] != session_id:
            raise InferenceError("Session introuvable.", 404)
        state = _current_status(_session)
        if state["state"] != "ready":
            raise InferenceError("Modèle occupé ou pas encore chargé.", 409)
        if _session["request_id"] is not None:
            raise InferenceError("Une génération est déjà en cours.", 409)

        request_id = uuid.uuid4().hex
        output = JOBS / f"chat-{session_id}-{request_id}.json"
        process: subprocess.Popen[str] = _session["process"]
        try:
            if process.stdin is None:
                raise OSError("Missing worker pipe")
            process.stdin.write(
                json.dumps({
                    "command": "generate",
                    "request_id": request_id,
                    "output": str(output),
                    "messages": validated,
                    "max_new_tokens": max_new_tokens,
                }) + "\n"
            )
            process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise InferenceError("Processus de génération indisponible.", 503) from exc
        _session["request_id"] = request_id
        return {"request_id": request_id, "state": "generating"}


def generation_status(session_id: str, request_id: str) -> dict[str, object]:
    if HEX_ID.fullmatch(request_id) is None:
        raise InferenceError("Identifiant de réponse invalide.", 404)
    with _lock:
        if _session is None or _session["session_id"] != session_id:
            raise InferenceError("Session introuvable.", 404)
        if _session["request_id"] != request_id:
            raise InferenceError("Réponse introuvable.", 404)
        path = JOBS / f"chat-{session_id}-{request_id}.json"
        state = _read_status(path)
        if state is None:
            if _session["process"].poll() is None:
                return {"state": "generating", "request_id": request_id}
            return {"state": "failed", "message": "Le modèle a cessé de répondre."}
        if state["state"] in {"completed", "failed"}:
            _session["request_id"] = None
        result: dict[str, object] = {
            "state": state["state"],
            "request_id": request_id,
        }
        if state["state"] == "completed":
            answer = state.get("answer")
            result["answer"] = answer if isinstance(answer, str) else ""
            tokens = state.get("generated_tokens")
            result["generated_tokens"] = tokens if isinstance(tokens, int) else 0
        if state["state"] == "failed":
            result["message"] = "La génération a échoué. Essaie une question plus courte."
        return result


def stop_session(session_id: str) -> dict[str, str]:
    global _session

    with _lock:
        if _session is None or _session["session_id"] != session_id:
            raise InferenceError("Session introuvable.", 404)
        proc: subprocess.Popen[str] = _session["process"]
        _session = None
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    return {"state": "stopped", "session_id": session_id}
