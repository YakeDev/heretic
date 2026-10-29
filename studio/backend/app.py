"""Read-only local diagnostics API for Heretic Studio.

This module does not load models or modify Heretic settings.
Launch it on loopback only: uvicorn app:app --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

from catalog import HubUnavailable, curated_catalog, search_hugging_face
from downloads import (
    DownloadError,
    cancel_download,
    download_status,
    nonce,
    preview_download,
    start_download,
)
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from hardware import estimate_resources, system_resources
from inference import (
    InferenceError,
    current_session,
    downloaded_models,
    generate,
    generation_status,
    session_status,
    start_session,
    stop_session,
)
from pydantic import BaseModel
from software import inspect_software
from starlette.middleware.trustedhost import TrustedHostMiddleware

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
TRUSTED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}

app = FastAPI(
    title="Heretic Studio (local)", version="0.3.0", docs_url=None, redoc_url=None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-Heretic-Token"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


def inspect_nvidia_gpus() -> list[dict[str, object]]:
    """Best-effort NVIDIA GPU detection; absence is not proof of no GPU."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return []
    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    gpus: list[dict[str, object]] = []
    for row in completed.stdout.splitlines():
        parts = [value.strip() for value in row.split(",")]
        if len(parts) != 3:
            continue
        name, total, free = parts
        try:
            gpus.append(
                {
                    "name": name,
                    "memory_total_gb": round(int(total) / 1024, 1),
                    "memory_free_gb": round(int(free) / 1024, 1),
                }
            )
        except ValueError:
            continue
    return gpus


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local-inference-alpha", "version": "0.3.0"}


@app.get("/api/system")
def system_info() -> dict[str, object]:
    return system_resources(ROOT, inspect_nvidia_gpus())


@app.get("/api/project")
def project_info() -> dict[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as fp:
        project = tomllib.load(fp)["project"]
    return {
        "name": project["name"],
        "version": project["version"],
        "python": project["requires-python"],
        "mode": "Lecture seule : aucun modèle n'est chargé ou modifié.",
    }


@app.get("/api/models")
def models_catalog() -> dict[str, object]:
    return {
        "models": curated_catalog(),
        "notice": "Catalogue indicatif. Compatibilité, licences et accès non vérifiés.",
    }


@app.get("/api/models/search")
def models_search(
    q: Annotated[
        str,
        Query(
            min_length=2,
            max_length=64,
            pattern=r"^[A-Za-z0-9_. /-]+$",
        ),
    ],
) -> dict[str, object]:
    try:
        results = search_hugging_face(q)
    except HubUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Recherche Hugging Face indisponible. Réessayez plus tard.",
        ) from exc
    return {
        "models": results,
        "notice": "Métadonnées publiques uniquement ; aucune compatibilité garantie.",
    }


@app.get("/api/hardware/estimate")
def hardware_estimate(
    model_id: Annotated[
        str,
        Query(
            min_length=5, max_length=120, pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$"
        ),
    ],
    mode: Literal["inference", "optimization"] = "inference",
    precision: Literal["fp16", "bnb_4bit"] = "fp16",
) -> dict[str, object]:
    estimate = estimate_resources(
        model_id=model_id,
        mode=mode,
        precision=precision,
        info=system_info(),
    )
    if estimate is None:
        raise HTTPException(
            status_code=404,
            detail="Modèle absent du catalogue : aucune estimation fiable disponible.",
        )
    return estimate


@app.get("/api/hardware/software")
def software_compatibility() -> dict[str, object]:
    """Run explicit, bounded local diagnostics without loading a model."""
    return inspect_software()


class PreviewDownloadRequest(BaseModel):
    model_id: str


class StartDownloadRequest(BaseModel):
    plan_id: str
    license_accepted: bool


def _trusted_origin(request: Request) -> None:
    if request.headers.get("origin") not in TRUSTED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origine non autorisée.")


def _download_authorization(request: Request) -> None:
    _trusted_origin(request)
    supplied = request.headers.get("x-heretic-token", "")
    if not secrets.compare_digest(supplied, nonce()):
        raise HTTPException(
            status_code=403, detail="Session de téléchargement non autorisée."
        )


@app.get("/api/downloads/session")
def download_session(request: Request) -> dict[str, str]:
    _trusted_origin(request)
    return {"token": nonce(), "scope": "local-downloads"}


@app.post("/api/downloads/preview")
def download_preview(
    request: Request, payload: PreviewDownloadRequest
) -> dict[str, object]:
    _download_authorization(request)
    try:
        return preview_download(payload.model_id)
    except DownloadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/downloads/start")
def download_start(
    request: Request, payload: StartDownloadRequest
) -> dict[str, object]:
    _download_authorization(request)
    try:
        return start_download(payload.plan_id, payload.license_accepted)
    except DownloadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/downloads/{job_id}")
def download_get_status(request: Request, job_id: str) -> dict[str, object]:
    _download_authorization(request)
    try:
        return download_status(job_id)
    except DownloadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/downloads/{job_id}/cancel")
def download_cancel(request: Request, job_id: str) -> dict[str, object]:
    _download_authorization(request)
    try:
        return cancel_download(job_id)
    except DownloadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class StartChatRequest(BaseModel):
    model_id: str
    revision: str
    device: Literal["cpu", "cuda"] = "cuda"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatGenerateRequest(BaseModel):
    messages: list[ChatMessage]
    max_new_tokens: int = 256
    style: Literal["neutral", "concise", "pedagogical"] = "neutral"


@app.get("/api/chat/models")
def chat_models(request: Request) -> dict[str, object]:
    """Only show previously completed local curated model snapshots."""
    _download_authorization(request)
    return {
        "models": downloaded_models(),
        "notice": "Seuls les modèles locaux validés par le gestionnaire sont proposés.",
    }


@app.get("/api/chat/current")
def chat_current(request: Request) -> dict[str, object]:
    _download_authorization(request)
    return {"session": current_session()}


@app.post("/api/chat/start")
def chat_start(request: Request, payload: StartChatRequest) -> dict[str, object]:
    _download_authorization(request)
    try:
        return start_session(payload.model_id, payload.revision, payload.device)
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/chat/{session_id}")
def chat_status(request: Request, session_id: str) -> dict[str, object]:
    _download_authorization(request)
    try:
        return session_status(session_id)
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/chat/{session_id}/generate")
def chat_generate(
    request: Request, session_id: str, payload: ChatGenerateRequest
) -> dict[str, object]:
    _download_authorization(request)
    try:
        return generate(
            session_id,
            [message.model_dump() for message in payload.messages],
            payload.max_new_tokens,
            payload.style,
        )
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/chat/{session_id}/responses/{request_id}")
def chat_response(
    request: Request, session_id: str, request_id: str
) -> dict[str, object]:
    _download_authorization(request)
    try:
        return generation_status(session_id, request_id)
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/chat/{session_id}/stop")
def chat_stop(request: Request, session_id: str) -> dict[str, str]:
    _download_authorization(request)
    try:
        return stop_session(session_id)
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
