"""Offline recovery for the Qwen2.5 0.5B interrupted Studio download.

A legacy download may have copied every file but been stopped before it
wrote its final receipt. Never trust total byte count alone: validate every
Hugging Face local-dir sidecar against the actual file content hash.

This command makes NO HTTP requests. It creates the Studio receipt ONLY
after a complete verified manifest match and explicit --repair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from downloads import JOBS, STORAGE, allowed_file

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
EXPECTED_FILES = frozenset(
    {
        "config.json",
        "generation_config.json",
        "merges.txt",
        "model.safetensors",
        "README.md",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    }
)
EXPECTED_TOTAL_BYTES = 999_591_264
REVISION = re.compile(r"[0-9a-f]{40}\Z")
ETAG = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
CHUNK_SIZE = 4 * 1024 * 1024


class RecoveryError(Exception):
    """Fail closed without changing downloaded model files."""


def _ensure_regular(path: Path, root: Path) -> None:
    if not path.is_file():
        raise RecoveryError(f"Fichier manquant : {path.name}")
    current = path
    while current != root:
        if current.is_symlink():
            raise RecoveryError("Lien symbolique interdit dans le modèle local.")
        if current == current.parent:
            raise RecoveryError("Fichier situé hors du dossier du modèle.")
        current = current.parent


def _actual_etag(path: Path, declared: str) -> str:
    # HF LFS files have SHA256 ETags, regular Git blobs have Git SHA1 ETags.
    if len(declared) == 64:
        digest = hashlib.sha256()
        prefix = b""
    else:
        digest = hashlib.sha1()
        prefix = f"blob {path.stat().st_size}\0".encode()
    digest.update(prefix)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matching_job(total_bytes: int, file_count: int, jobs_root: Path) -> bool:
    if not jobs_root.is_dir() or jobs_root.is_symlink():
        return False
    for job_file in jobs_root.glob("*.json"):
        if job_file.is_symlink() or job_file.name.startswith("chat-"):
            continue
        try:
            record = json.loads(job_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        if (
            record.get("total_bytes") == total_bytes
            and record.get("total_files") == file_count
            and isinstance(record.get("completed_files"), int)
            and 0 <= record["completed_files"] <= file_count
            and record.get("state") in {"downloading", "failed", "completed"}
        ):
            return True
    return False


def verify_snapshot(
    storage: Path = STORAGE, jobs_root: Path = JOBS
) -> dict[str, Any]:
    """Offline SHA checks. No writes, no model import, no internet access."""
    if storage.is_symlink():
        raise RecoveryError("Le dossier de modèles est un lien symbolique.")
    model_root = storage / MODEL_ID.replace("/", "--")
    if not model_root.is_dir() or model_root.is_symlink():
        raise RecoveryError("Dossier local Qwen introuvable.")

    candidates = [
        child
        for child in model_root.iterdir()
        if child.is_dir() and not child.is_symlink() and REVISION.fullmatch(child.name)
    ]
    if len(candidates) != 1:
        raise RecoveryError("Il faut exactement une révision locale Qwen à récupérer.")
    snapshot = candidates[0]
    revision = snapshot.name
    receipt = snapshot / "heretic-studio-snapshot.json"
    if receipt.exists() or receipt.is_symlink():
        raise RecoveryError(
            "Ce snapshot possède déjà un reçu. Utilise le chat local ou vérifie le reçu."
        )

    actual_files: set[str] = set()
    total = 0
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise RecoveryError("Lien symbolique interdit dans les fichiers téléchargés.")
        if path.is_file():
            relative = path.relative_to(snapshot).as_posix()
            if relative.startswith(".cache/"):
                continue
            if not allowed_file(relative):
                raise RecoveryError(f"Fichier non autorisé : {relative}")
            actual_files.add(relative)
            total += path.stat().st_size

    if actual_files != EXPECTED_FILES:
        missing = ", ".join(sorted(EXPECTED_FILES - actual_files)) or "aucun"
        extra = ", ".join(sorted(actual_files - EXPECTED_FILES)) or "aucun"
        raise RecoveryError(
            f"Fichiers incomplets ou inattendus (manquants : {missing} ; autres : {extra})."
        )
    if total != EXPECTED_TOTAL_BYTES:
        raise RecoveryError(
            f"Taille différente : {total} octets au lieu de {EXPECTED_TOTAL_BYTES}."
        )
    if not _matching_job(total, len(EXPECTED_FILES), jobs_root):
        raise RecoveryError(
            "Aucune trace locale de téléchargement Studio correspondant aux 8 fichiers."
        )

    config_path = snapshot / "config.json"
    _ensure_regular(config_path, snapshot)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecoveryError("Configuration du modèle illisible.") from exc
    if not isinstance(config, dict) or config.get("model_type") != "qwen2":
        raise RecoveryError("Le modèle n'a pas l'architecture Qwen2 attendue.")
    if "auto_map" in config:
        raise RecoveryError("Configuration contenant du code distant : refus.")

    verified: list[str] = []
    for name in sorted(EXPECTED_FILES):
        path = snapshot / name
        _ensure_regular(path, snapshot)
        meta = snapshot / ".cache" / "huggingface" / "download" / f"{name}.metadata"
        if not meta.is_file() or meta.is_symlink():
            raise RecoveryError(f"Métadonnées Hugging Face manquantes : {name}.")
        try:
            lines = meta.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RecoveryError(f"Métadonnées illisibles : {name}.") from exc
        if len(lines) < 3 or lines[0] != revision:
            raise RecoveryError(f"Révision Hugging Face invalide : {name}.")
        etag = lines[1].strip()
        if not ETAG.fullmatch(etag):
            raise RecoveryError(f"Empreinte Hugging Face invalide : {name}.")
        if _actual_etag(path, etag) != etag:
            raise RecoveryError(f"Empreinte incorrecte, fichier corrompu : {name}.")
        verified.append(name)

    return {
        "model_id": MODEL_ID,
        "revision": revision,
        "path": snapshot,
        "files": verified,
        "total_bytes": total,
        "verified": True,
    }


def repair_snapshot(storage: Path = STORAGE, jobs_root: Path = JOBS) -> Path:
    """Write the missing receipt atomically, AFTER successful full verification."""
    data = verify_snapshot(storage, jobs_root)
    directory = data["path"]
    receipt = directory / "heretic-studio-snapshot.json"
    content = {
        "model_id": data["model_id"],
        "revision": data["revision"],
        "files": data["files"],
    }
    fd, name = tempfile.mkstemp(dir=directory, prefix=".studio-receipt-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(content, stream, ensure_ascii=False)
        if receipt.exists() or receipt.is_symlink():
            raise RecoveryError("Un reçu existe déjà ; aucune modification effectuée.")
        os.replace(name, receipt)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérification intégrale hors ligne de Qwen 0.5B."
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Créer le reçu uniquement si tous les fichiers et SHA sont validés.",
    )
    args = parser.parse_args()
    try:
        if args.repair:
            destination = repair_snapshot()
            print(f"SUCCÈS : modèle récupéré et reçu enregistré : {destination}")
        else:
            state = verify_snapshot()
            print(
                "VÉRIFICATION RÉUSSIE : "
                f"{len(state['files'])} fichiers, {state['total_bytes']} octets, "
                "empreintes cryptographiques correctes."
            )
            print("Aucun fichier modifié. Utilise --repair pour enregistrer le reçu.")
    except RecoveryError as exc:
        print(f"VÉRIFICATION REFUSÉE : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
