"""Read-only local diagnostics API for Heretic Studio.

This module does not load models or modify Heretic settings.
Launch it on loopback only: uvicorn app:app --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

from catalog import HubUnavailable, curated_catalog, search_hugging_face
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from hardware import estimate_resources, system_resources

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="Heretic Studio (local)", version="0.1.0", docs_url=None, redoc_url=None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


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
    return {"status": "ok", "mode": "diagnostic-only", "version": "0.1.0"}


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
