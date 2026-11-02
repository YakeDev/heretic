"""Isolated subprocess for explicit Hugging Face downloads; never imports models."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath

from huggingface_hub import hf_hub_download


def _write_status(path: Path, value: dict[str, object]) -> None:
    """Atomic progress updates: frontend sees last *completed* file only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix="progress-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main() -> int:
    # stdin is supplied by the trusted local API, never by the browser.
    try:
        job = json.loads(sys.stdin.read(262144))
        repo_id = job["model_id"]
        sha = job["revision"]
        items = job["files"]
        destination = Path(job["destination"])
        status_file = Path(job["status_file"])
        total_bytes = job["total_bytes"]
    except (ValueError, KeyError, TypeError):
        return 2

    completed_bytes = 0
    completed_files = 0
    count = len(items)
    _write_status(
        status_file,
        {
            "state": "downloading",
            "completed_files": 0,
            "completed_bytes": 0,
            "total_files": count,
            "total_bytes": total_bytes,
        },
    )
    try:
        for item in items:
            filename = item["path"]
            # Defense in depth: paths must always stay relative.
            relative = PurePosixPath(filename)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in filename
                or any(part.startswith(".") for part in relative.parts)
            ):
                raise ValueError("Invalid snapshot entry")
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=sha,
                local_dir=destination,
                token=None,
            )
            completed_files += 1
            completed_bytes += item["size"]
            _write_status(
                status_file,
                {
                    "state": "downloading",
                    "completed_files": completed_files,
                    "completed_bytes": completed_bytes,
                    "total_files": count,
                    "total_bytes": total_bytes,
                },
            )
    except Exception:
        _write_status(
            status_file,
            {
                "state": "failed",
                "completed_files": completed_files,
                "completed_bytes": completed_bytes,
                "message": (
                    "Téléchargement interrompu : vérifie le réseau, les droits d'accès "
                    "et l'espace disque. Aucun modèle n'a été exécuté."
                ),
            },
        )
        return 1

    # Receipt is written only after all pinned assets are downloaded.
    # The local chat loader only accepts snapshots with this receipt.
    _write_status(
        destination / "heretic-studio-snapshot.json",
        {
            "model_id": repo_id,
            "revision": sha,
            "files": [item["path"] for item in items],
        },
    )
    _write_status(
        status_file,
        {
            "state": "completed",
            "completed_files": count,
            "completed_bytes": completed_bytes,
            "total_files": count,
            "total_bytes": total_bytes,
            "message": "Fichiers téléchargés. Le modèle n'a pas été chargé.",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
