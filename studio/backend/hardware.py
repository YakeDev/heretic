"""Cautious resource estimates for catalogued open-weight models.

This module NEVER loads, downloads, or executes a model. It cannot prove
architectural compatibility, CUDA support, or actual GPU memory use.
"""

from __future__ import annotations

import math
import platform
import re
from pathlib import Path
from typing import Any

import psutil

from catalog import CURATED_MODELS

GIB = 1024**3
BILLION = 1_000_000_000
PARAMETERS = re.compile(r"(\d+(?:\.\d+)?)B\Z")
VALID_MODES = {"inference", "optimization"}
VALID_PRECISIONS = {"fp16", "bnb_4bit"}


def system_resources(root: Path, nvidia_gpus: list[dict[str, object]]) -> dict[str, object]:
    """Probe local OS resources; non-NVIDIA accelerators are NOT ruled out."""
    ram = psutil.virtual_memory()
    try:
        disk_available = round(psutil.disk_usage(str(root)).free / GIB, 1)
    except OSError:
        disk_available = None

    return {
        "os": platform.system(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or platform.machine() or "Non identifié",
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_total_gb": round(ram.total / GIB, 1),
        "ram_available_gb": round(ram.available / GIB, 1),
        "disk_available_gb": disk_available,
        "nvidia_gpus": nvidia_gpus,
        "gpu_detection_note": (
            "Seuls les GPU NVIDIA accessibles via nvidia-smi sont sondés. "
            "Un résultat vide ne signifie pas qu'aucun GPU ne fonctionne."
        ),
        "apple_silicon_possible": (
            platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
        ),
    }


def _number(value: object) -> float | None:
    if (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    return None


def _available_gpus(info: dict[str, object]) -> list[dict[str, object]]:
    raw = info.get("nvidia_gpus")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, object]] = []
    for gpu in raw:
        if not isinstance(gpu, dict):
            continue
        if _number(gpu.get("memory_free_gb")) is not None:
            result.append(gpu)
    return result


def estimate_resources(
    model_id: str,
    mode: str,
    precision: str,
    info: dict[str, object],
) -> dict[str, Any] | None:
    """Estimate memory for a *curated* model, otherwise return None.

    Memory calculations are rough planning heuristics (not benchmarks).
    Comparing against the most-free SINGLE GPU deliberately avoids
    pretending that VRAM from multiple GPUs can be simply pooled.
    """
    if mode not in VALID_MODES or precision not in VALID_PRECISIONS:
        raise ValueError("Unsupported mode or precision")

    selected = next((m for m in CURATED_MODELS if m["id"] == model_id), None)
    if selected is None:
        return None
    match = PARAMETERS.fullmatch(selected["parameters"])
    if match is None:
        return None
    parameters = float(match.group(1))
    weight_gib = parameters * BILLION * (2 if precision == "fp16" else 0.5) / GIB

    # Coarse *whole-process* VRAM thresholds; a real run can use more or less.
    if mode == "inference":
        recommended_gpu_gib = weight_gib * (1.3 if precision == "fp16" else 1.5) + (
            2 if precision == "fp16" else 3
        )
    else:
        recommended_gpu_gib = weight_gib * (2.0 if precision == "fp16" else 2.5) + 6

    # Storage budget for downloaded weights and temporary/cache overhead.
    # Actual repository size, sharding and tokenizer artifacts vary.
    estimated_disk_gib = weight_gib * 1.5 + 3
    required_ram_gib = max(8, weight_gib * 1.3 + 4)

    gpus = _available_gpus(info)
    best_free = max((free for g in gpus if (free := _number(g.get("memory_free_gb"))) is not None), default=None)
    best_total = max((total for g in gpus if (total := _number(g.get("memory_total_gb"))) is not None), default=None)
    ram_available = info.get("ram_available_gb")
    disk_available = info.get("disk_available_gb")

    status = "indeterminate"
    reasons: list[str] = []
    if isinstance(disk_available, (int, float)) and disk_available < estimated_disk_gib:
        status = "probably_insufficient"
        reasons.append("L'espace disque disponible est inférieur au budget de stockage estimé.")
    if best_free is None:
        reasons.append(
            "VRAM NVIDIA non détectée : le mode CPU, AMD, Apple ou déporté n'est pas évalué."
        )
    elif best_free < recommended_gpu_gib:
        status = "probably_insufficient"
        reasons.append("La VRAM libre d'un GPU NVIDIA est inférieure à l'estimation prudente.")
    elif status != "probably_insufficient":
        status = "candidate_only"
        reasons.append("La VRAM libre paraît suffisante selon cette estimation, sans garantie.")
    if isinstance(ram_available, (int, float)) and ram_available < required_ram_gib:
        reasons.append(
            "La RAM disponible est basse pour cette estimation : risque de lenteur ou d'échec."
        )
        if status == "candidate_only":
            status = "indeterminate"
    if mode == "optimization":
        reasons.append(
            "ARA/LoRA peut ajouter des pics mémoire importants ; aucun chargement n'a été testé."
        )
    if precision == "bnb_4bit":
        reasons.append(
            "Le mode bitsandbytes 4 bits exige une pile logicielle compatible ; non vérifiée."
        )
    reasons.append(
        "Compatibilité d'architecture, licence, pilotes, dépendances et vitesse non vérifiées."
    )

    return {
        "model_id": model_id,
        "mode": mode,
        "precision": precision,
        "parameters_billions": parameters,
        "weight_memory_gib": round(weight_gib, 1),
        "estimated_gpu_gib": round(recommended_gpu_gib, 1),
        "estimated_ram_gib": round(required_ram_gib, 1),
        "estimated_disk_gib": round(estimated_disk_gib, 1),
        "best_single_nvidia_free_gib": best_free,
        "best_single_nvidia_total_gib": best_total,
        "status": status,
        "reasons": reasons,
        "method": "heuristic_v1",
        "guaranteed": False,
    }
