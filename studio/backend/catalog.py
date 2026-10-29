"""Read-only Hugging Face catalogue for Heretic Studio.

Model metadata is *not* evidence that an architecture is supported by Heretic.
No model files are downloaded and no model repository code is executed.
"""

from __future__ import annotations

import re

import httpx

# Always use a fixed upstream; never accept a user-supplied URL.
HUB_SEARCH_ENDPOINT = "https://huggingface.co/api/models"
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
MAX_RESULTS = 12

CURATED_MODELS: tuple[dict[str, str], ...] = (
    {
        "id": "Qwen/Qwen2.5-0.5B-Instruct",
        "family": "Qwen",
        "parameters": "0.5B",
        "description": "Petit modèle adapté à un premier essai local sur CPU.",
        "access": "Vérifier la fiche du modèle",
    },
    {
        "id": "meta-llama/Llama-3.2-3B-Instruct",
        "family": "Llama",
        "parameters": "3B",
        "description": "Modèle Meta relativement léger pour les premiers essais.",
        "access": "Conditions Meta et demande d'accès",
    },
    {
        "id": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "family": "Llama",
        "parameters": "8B",
        "description": "Modèle Meta plus important pour comparer les comportements.",
        "access": "Conditions Meta et demande d'accès",
    },
    {
        "id": "Qwen/Qwen3-4B-Instruct-2507",
        "family": "Qwen",
        "parameters": "4B",
        "description": "Modèle de dialogue Qwen cité dans la documentation Heretic.",
        "access": "Vérifier la fiche du modèle",
    },
    {
        "id": "google/gemma-3-4b-it",
        "family": "Gemma",
        "parameters": "4B",
        "description": "Modèle Google pour des comparaisons entre familles.",
        "access": "Vérifier la fiche du modèle",
    },
    {
        "id": "mistralai/Mistral-7B-Instruct-v0.3",
        "family": "Mistral",
        "parameters": "7B",
        "description": "Modèle Mistral pour un autre point de comparaison.",
        "access": "Vérifier la fiche du modèle",
    },
)


class HubUnavailable(Exception):
    """Hugging Face search could not be completed reliably."""


def curated_catalog() -> list[dict[str, str]]:
    """Return safe display metadata only, without contacting the Hub."""
    return [
        {
            **item,
            "url": f"https://huggingface.co/{item['id']}",
            "compatibility": "non_vérifiée",
        }
        for item in CURATED_MODELS
    ]


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def search_hugging_face(query: str) -> list[dict[str, object]]:
    """Search public HF metadata (bounded, no credentials, no downloads)."""
    try:
        response = httpx.get(
            HUB_SEARCH_ENDPOINT,
            params={
                "search": query,
                "limit": MAX_RESULTS,
                "sort": "downloads",
                "direction": -1,
            },
            headers={"Accept": "application/json"},
            timeout=5.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HubUnavailable from exc

    if not isinstance(payload, list):
        raise HubUnavailable("Unexpected response shape")

    models: list[dict[str, object]] = []
    for entry in payload[:MAX_RESULTS]:
        if not isinstance(entry, dict) or entry.get("private"):
            continue
        repo_id = entry.get("id")
        if not isinstance(repo_id, str) or not MODEL_ID.fullmatch(repo_id):
            continue
        pipeline = entry.get("pipeline_tag")
        models.append(
            {
                "id": repo_id,
                "url": f"https://huggingface.co/{repo_id}",
                "gated": bool(entry.get("gated")),
                "task": pipeline if isinstance(pipeline, str) else None,
                "downloads": _nonnegative_int(entry.get("downloads")),
                "likes": _nonnegative_int(entry.get("likes")),
            }
        )
    return models
