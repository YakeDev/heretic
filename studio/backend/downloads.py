"""Explicit, bounded downloads of curated Hugging Face model snapshots.

Only safetensors, tokenizer and static configuration assets are allowed.
The model is NEVER imported, loaded or executed by this module.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from catalog import CURATED_MODELS
from huggingface_hub import HfApi

MAX_BYTES = 35 * 1024**3
MAX_FILES = 350
PLAN_TTL_SECONDS = 900
SHA = re.compile(r"[0-9a-f]{40}\Z")
STORAGE = Path.home() / ".cache" / "heretic-studio" / "models"
JOBS = Path.home() / ".cache" / "heretic-studio" / "jobs"

_lock = threading.Lock()
_plans: dict[str, dict[str, Any]] = {}
_jobs: dict[str, dict[str, Any]] = {}
_active_id: str | None = None


class DownloadError(Exception):
    """Safe user-facing error (no secrets or upstream error traces)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def allowed_file(name: str) -> bool:
    """Reject repository code, pickle weights, paths and hidden artifacts."""
    if not isinstance(name, str) or "\\" in name or len(name) > 240:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} or part.startswith(".") for part in path.parts
    ):
        return False
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/" for ch in name):
        return False
    return path.suffix.lower() in {
        ".safetensors", ".json", ".txt", ".model", ".tiktoken", ".jinja", ".md",
    }


def _disk_available(path: Path) -> int:
    """Measure free disk space using the nearest existing parent."""
    existing = path
    while not existing.exists():
        if existing == existing.parent:
            raise DownloadError("Impossible de déterminer le disque disponible.", 503)
        existing = existing.parent
    try:
        return shutil.disk_usage(existing).free
    except OSError as exc:
        raise DownloadError("Impossible de déterminer le disque disponible.", 503) from exc


def preview_download(model_id: str) -> dict[str, object]:
    """Validate a model and pin a manifest before any download begins."""
    if model_id not in {m["id"] for m in CURATED_MODELS}:
        raise DownloadError("Modèle non autorisé dans le catalogue.", 404)
    try:
        info = HfApi().model_info(model_id, files_metadata=True, timeout=15)
    except Exception as exc:
        raise DownloadError(
            "Métadonnées Hugging Face indisponibles. Vérifie la connexion et les accès.",
            503,
        ) from exc

    revision = getattr(info, "sha", None)
    if not isinstance(revision, str) or SHA.fullmatch(revision) is None:
        raise DownloadError("Révision du modèle indisponible.", 503)
    raw_files = getattr(info, "siblings", None)
    if not isinstance(raw_files, list):
        raise DownloadError("Liste des fichiers du modèle indisponible.", 503)

    manifest: list[dict[str, object]] = []
    total = 0
    has_weights = False
    for sibling in raw_files:
        filename = getattr(sibling, "rfilename", None)
        if not isinstance(filename, str) or not allowed_file(filename):
            continue
        size = getattr(sibling, "size", None)
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise DownloadError("Taille de certains fichiers inconnue : téléchargement bloqué.", 422)
        total += size
        if filename.endswith(".safetensors"):
            has_weights = True
        if total > MAX_BYTES:
            raise DownloadError("Modèle dépassant la limite de téléchargement de 35 Gio.", 422)
        manifest.append({"path": filename, "size": size})
        if len(manifest) > MAX_FILES:
            raise DownloadError("Modèle contenant trop de fichiers pour ce premier gestionnaire.", 422)

    if not has_weights:
        raise DownloadError(
            "Aucun poids safetensors utilisable trouvé. Formats bin/pickle exclus.",
            422,
        )
    if total <= 0:
        raise DownloadError("Le dépôt ne fournit pas une estimation de taille utilisable.", 422)

    dest = STORAGE / model_id.replace("/", "--") / revision
    available = _disk_available(dest)
    # A safety margin accommodates HTTP/cache metadata and filesystem overhead.
    required = int(total * 1.15) + 512 * 1024**2
    if available < required:
        raise DownloadError("Espace disque insuffisant pour ce téléchargement.", 422)

    plan_id = uuid.uuid4().hex
    plan: dict[str, Any] = {
        "id": plan_id,
        "model_id": model_id,
        "revision": revision,
        "files": manifest,
        "total_bytes": total,
        "expires": time.monotonic() + PLAN_TTL_SECONDS,
        "gated": bool(getattr(info, "gated", False)),
        "destination": str(dest),
    }
    with _lock:
        # Avoid unbounded accumulation of expired or abandoned plans.
        _plans.clear()
        _plans[plan_id] = plan

    return {
        "plan_id": plan_id,
        "model_id": model_id,
        "revision": revision,
        "file_count": len(manifest),
        "total_bytes": total,
        "disk_free_bytes": available,
        "gated": plan["gated"],
        "destination": str(dest),
        "expires_in_seconds": PLAN_TTL_SECONDS,
        "warning": (
            "Vérifie la licence et les autorisations sur Hugging Face. "
            "Les poids sont téléchargés, mais jamais exécutés. "
            "Aucun fichier Python ou pickle n'est accepté."
        ),
    }


def _status_from_disk(job: dict[str, Any]) -> dict[str, object]:
    status_path = Path(job["status_file"])
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {
            "state": "downloading",
            "completed_files": 0,
            "total_files": job["file_count"],
            "completed_bytes": 0,
            "total_bytes": job["total_bytes"],
        }
    if not isinstance(raw, dict) or raw.get("state") not in {
        "downloading", "completed", "failed",
    }:
        return {"state": "failed", "message": "État du téléchargement invalide."}
    return {
        "state": raw["state"],
        "completed_files": raw.get("completed_files", 0),
        "total_files": job["file_count"],
        "completed_bytes": raw.get("completed_bytes", 0),
        "total_bytes": job["total_bytes"],
        "message": raw.get("message"),
    }


def start_download(plan_id: str, license_accepted: bool) -> dict[str, object]:
    """Execute only a preflighted, pinned and explicitly confirmed plan."""
    global _active_id

    if not license_accepted:
        raise DownloadError("Confirme d'abord la licence et les conditions du modèle.", 422)

    with _lock:
        plan = _plans.get(plan_id)
        if plan is None or time.monotonic() > plan["expires"]:
            raise DownloadError("Préparation expirée. Relance l'analyse du téléchargement.", 422)
        if _active_id is not None:
            active = _jobs.get(_active_id)
            if active is not None and active["process"].poll() is None:
                raise DownloadError("Un téléchargement est déjà en cours.", 409)
            _active_id = None

        # Re-check capacity after the user confirms.
        required = int(plan["total_bytes"] * 1.15) + 512 * 1024**2
        if _disk_available(Path(plan["destination"])) < required:
            raise DownloadError("Espace disque devenu insuffisant.", 422)

        job_id = uuid.uuid4().hex
        destination = Path(plan["destination"])
        status_file = JOBS / f"{job_id}.json"
        destination.mkdir(parents=True, exist_ok=True)
        JOBS.mkdir(parents=True, exist_ok=True)

        work = {
            "model_id": plan["model_id"],
            "revision": plan["revision"],
            "destination": str(destination),
            "files": plan["files"],
            "total_bytes": plan["total_bytes"],
            "status_file": str(status_file),
        }
        worker_file = Path(__file__).with_name("download_worker.py")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", str(worker_file)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if proc.stdin is None:
                raise OSError("Missing worker stdin")
            proc.stdin.write(json.dumps(work))
            proc.stdin.close()
        except (OSError, BrokenPipeError) as exc:
            if "proc" in locals() and proc.poll() is None:
                proc.terminate()
            raise DownloadError("Impossible de démarrer le téléchargement.", 503) from exc

        job = {
            "process": proc,
            "status_file": str(status_file),
            "model_id": plan["model_id"],
            "revision": plan["revision"],
            "destination": str(destination),
            "total_bytes": plan["total_bytes"],
            "file_count": len(plan["files"]),
            "canceled": False,
        }
        _jobs[job_id] = job
        _plans.pop(plan_id, None)
        _active_id = job_id
    return {"job_id": job_id, "state": "downloading", "model_id": job["model_id"]}


def download_status(job_id: str) -> dict[str, object]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise DownloadError("Téléchargement introuvable dans cette session.", 404)
        result = _status_from_disk(job)
        if job["canceled"]:
            result["state"] = "canceled"
            result["message"] = "Téléchargement annulé. Les fichiers partiels peuvent être conservés."
        elif job["process"].poll() is not None and result["state"] == "downloading":
            result["state"] = "failed"
            result["message"] = "Le téléchargement a été interrompu."
        result.update({
            "job_id": job_id,
            "model_id": job["model_id"],
            "revision": job["revision"],
            "destination": job["destination"],
        })
        return result


def cancel_download(job_id: str) -> dict[str, object]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise DownloadError("Téléchargement introuvable.", 404)
        proc: subprocess.Popen[str] = job["process"]
        current = _status_from_disk(job)
        if current["state"] in {"completed", "failed"}:
            raise DownloadError("Téléchargement déjà terminé.", 409)
        if proc.poll() is not None:
            raise DownloadError("Téléchargement déjà interrompu.", 409)
        proc.terminate()
        job["canceled"] = True
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
    return {"job_id": job_id, "state": "canceled", "message": "Téléchargement arrêté."}


def nonce() -> str:
    """Per-process token used to reject CSRF from arbitrary websites."""
    return _NONCE


_NONCE = secrets.token_urlsafe(32)
