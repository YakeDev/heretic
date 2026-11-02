"""Opt-in diagnostics for the *backend Python environment*, not a model.

The probe never downloads models, imports model repository code, or modifies
the environment. PyTorch is imported only in a time-bounded child process.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys

PACKAGES: tuple[tuple[str, str], ...] = (
    ("torch", "PyTorch"),
    ("transformers", "Transformers"),
    ("accelerate", "Accelerate"),
    ("peft", "PEFT / LoRA"),
    ("bitsandbytes", "bitsandbytes"),
    ("huggingface-hub", "Hugging Face Hub"),
    ("optuna", "Optuna"),
)

# Hardcoded and executed in Python isolated mode. Never accepts user code.
TORCH_PROBE = """
import json
try:
    import torch
    cuda = bool(torch.cuda.is_available())
    mps = bool(torch.backends.mps.is_available())
    device_count = int(torch.cuda.device_count()) if cuda else 0
    print(json.dumps({
        "cuda_available": cuda,
        "mps_available": mps,
        "cuda_devices": device_count,
        "cuda_build": torch.version.cuda,
        "rocm_build": torch.version.hip,
    }))
except Exception:
    print(json.dumps({"error": "torch_probe_failed"}))
"""


def installed_packages() -> list[dict[str, str | None]]:
    """Read installed package versions without importing the packages."""
    result: list[dict[str, str | None]] = []
    for package, label in PACKAGES:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = None
        result.append({"package": package, "label": label, "version": version})
    return result


def nvidia_driver() -> dict[str, object]:
    """Driver metadata only; nvidia-smi absence is not proof of no GPU."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"status": "not_detected", "gpus": []}

    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "probe_failed", "gpus": []}

    if completed.returncode != 0:
        return {"status": "probe_failed", "gpus": []}

    gpus: list[dict[str, object]] = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            continue
        name, driver, vram = fields
        try:
            memory_gib = round(int(vram) / 1024, 1)
        except ValueError:
            continue
        gpus.append(
            {
                "name": name,
                "driver_version": driver,
                "memory_total_gib": memory_gib,
            }
        )
    return {"status": "detected" if gpus else "not_detected", "gpus": gpus}


def torch_runtime() -> dict[str, object]:
    """Time-bound, isolated local PyTorch runtime probe (no model loading)."""
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", TORCH_PROBE],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except OSError:
        return {"status": "probe_failed"}

    if completed.returncode != 0:
        return {"status": "probe_failed"}
    try:
        result = json.loads(completed.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {"status": "probe_failed"}
    if not isinstance(result, dict):
        return {"status": "probe_failed"}
    if result.get("error"):
        return {"status": "probe_failed"}

    cuda_available = result.get("cuda_available")
    mps_available = result.get("mps_available")
    cuda_devices = result.get("cuda_devices")
    cuda_build = result.get("cuda_build")
    rocm_build = result.get("rocm_build")
    if not isinstance(cuda_available, bool) or not isinstance(mps_available, bool):
        return {"status": "probe_failed"}
    if (
        not isinstance(cuda_devices, int)
        or isinstance(cuda_devices, bool)
        or not 0 <= cuda_devices <= 128
    ):
        return {"status": "probe_failed"}
    return {
        "status": "checked",
        "cuda_available": cuda_available,
        "mps_available": mps_available,
        "cuda_devices": cuda_devices,
        "cuda_build": cuda_build if isinstance(cuda_build, str) else None,
        "rocm_build": rocm_build if isinstance(rocm_build, str) else None,
    }


def inspect_software() -> dict[str, object]:
    packages = installed_packages()
    installed = {p["package"] for p in packages if p["version"] is not None}
    runtime = (
        torch_runtime() if "torch" in installed else {"status": "torch_not_installed"}
    )
    driver = nvidia_driver()

    warnings = [
        "Diagnostic du Python exécutant le backend Studio uniquement ; un autre environnement Heretic peut différer.",
        "Les versions installées ne prouvent pas que les modules peuvent fonctionner ensemble.",
        "Les modèles et leur code distant ne sont jamais téléchargés ni exécutés.",
        "Les pilotes, l'architecture et la compatibilité avec Heretic ne sont pas certifiés.",
    ]
    if "torch" not in installed:
        warnings.append("PyTorch absent de cet environnement Python.")
    if "bitsandbytes" in installed:
        warnings.append(
            "bitsandbytes installé ne garantit pas le fonctionnement du mode 4 bits."
        )
    if runtime.get("status") in {"timeout", "probe_failed"}:
        warnings.append("La sonde PyTorch a échoué ; aucun verdict de compatibilité.")
    if driver["status"] != "detected":
        warnings.append(
            "Le pilote NVIDIA n'a pas été identifié ; AMD et Apple ne sont pas exclus."
        )

    return {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "driver_nvidia": driver,
        "torch_runtime": runtime,
        "notes": warnings,
        "compatibility": "not_verified",
        "read_only": True,
    }
