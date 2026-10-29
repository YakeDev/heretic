"""Run bounded quality probes against an ALREADY LOADED local Studio chat.

This tool never downloads models, starts a model, or calls a remote service.
Its factual references are for human review; automatic checks are structural.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "http://127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:5173"
SUITE = Path(__file__).with_name("benchmarks") / "french_quality_v1.json"
# Bypass environment/system proxies so no prompt can be routed away from loopback.
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api_request(
    path: str, token: str = "", payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Only call the fixed local backend; never accept a custom remote URL."""
    if not path.startswith("/api/") or "://" in path or ".." in path:
        raise ValueError("Invalid API path")
    headers = {"Origin": ORIGIN}
    if token:
        headers["X-Heretic-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        API + path,
        headers=headers,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method="POST" if payload is not None else "GET",
    )
    try:
        with LOCAL_OPENER.open(request, timeout=15) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Studio refused the request (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Backend local inaccessible on 127.0.0.1:8765.") from exc
    if not isinstance(data, dict):
        raise TypeError("Unexpected backend reply")
    return data


def normalized(value: str) -> str:
    source = unicodedata.normalize("NFD", value.casefold())
    no_accents = "".join(c for c in source if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", no_accents))


def automatic_check(check: dict[str, Any] | None, answer: str, previous: str) -> str:
    """Only deterministic, *formal* checks. No automated factual verdicts."""
    if not check:
        return "human_review"
    kind = check.get("type")
    target = check.get("value")
    if kind == "contains" and isinstance(target, str):
        return "pass" if normalized(target) in normalized(answer) else "fail"
    if kind == "number" and type(target) is int:
        return "pass" if normalized(answer) == str(target) else "fail"
    if kind == "json_fields" and isinstance(target, dict):
        try:
            parsed = json.loads(answer.strip())
        except (TypeError, ValueError):
            return "fail"
        return (
            "pass"
            if isinstance(parsed, dict)
            and all(parsed.get(k) == v for k, v in target.items())
            else "fail"
        )
    if kind == "different":
        left, right = normalized(answer), normalized(previous)
        if not left or not right:
            return "human_review"
        return "pass" if left != right else "fail"
    if kind == "max_sentences" and type(target) is int:
        # Approximation only, unsuitable as a formal linguistic evaluation.
        count = len([part for part in re.split(r"[.!?]+", answer) if part.strip()])
        return "pass" if 0 < count <= target else "fail"
    raise ValueError("Unknown benchmark check")


def load_cases(path: Path = SUITE) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unrecognized benchmark version")
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValueError("Invalid benchmark size")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise TypeError("Missing benchmark case id")
        name = case["id"]
        if not re.fullmatch(r"[a-z0-9-]{3,64}", name) or name in ids:
            raise ValueError("Invalid or duplicate benchmark case id")
        ids.add(name)
        turns = case.get("turns")
        if not isinstance(turns, list) or not 1 <= len(turns) <= 4:
            raise ValueError("Invalid benchmark turn count")
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("prompt"), str):
                raise TypeError("Invalid benchmark prompt")
            if not turn["prompt"].strip() or len(turn["prompt"]) > 2000:
                raise ValueError("Benchmark prompt outside API limits")
            if not isinstance(turn.get("review"), str):
                raise TypeError("Missing human-review instructions")
    return cases


def wait_for_reply(
    session_id: str, request_id: str, token: str, timeout: float = 180
) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status = api_request(f"/api/chat/{session_id}/responses/{request_id}", token)
        if status.get("state") in {"completed", "failed"}:
            return status
        time.sleep(1.5)
    raise RuntimeError(
        "Generation timed out. Stop the model manually in Studio before retrying."
    )


def run_cases(
    cases: list[dict[str, Any]], session_id: str, token: str, mode: str, max_tokens: int
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for number, case in enumerate(cases, 1):
        print(f"[{number}/{len(cases)}] {case['id']}", flush=True)
        history: list[dict[str, str]] = []
        turns: list[dict[str, Any]] = []
        previous = ""
        for turn in case["turns"]:
            outgoing = [*history[-8:], {"role": "user", "content": turn["prompt"]}]
            if sum(len(item["content"]) for item in outgoing) > 6000:
                raise RuntimeError("Benchmark history exceeded API context limit")
            started = api_request(
                f"/api/chat/{session_id}/generate",
                token,
                {
                    "messages": outgoing,
                    "max_new_tokens": max_tokens,
                    "style": "concise",
                    "generation_mode": mode,
                },
            )
            request_id = started.get("request_id")
            if not isinstance(request_id, str) or not re.fullmatch(
                r"[a-f0-9]{32}", request_id
            ):
                raise RuntimeError("Invalid generation request ID")
            reply = wait_for_reply(session_id, request_id, token)
            answer = (
                reply.get("answer", "") if reply.get("state") == "completed" else ""
            )
            checked = (
                automatic_check(turn.get("check"), answer, previous)
                if answer
                else "no_answer"
            )
            turns.append(
                {
                    "prompt": turn["prompt"],
                    "answer": answer,
                    "human_review_reference": turn["review"],
                    "automatic_form_check": checked,
                    "finish_reason": reply.get("finish_reason"),
                    "tokens": reply.get("generated_tokens"),
                    "elapsed_seconds": reply.get("elapsed_seconds"),
                    "tokens_per_second": reply.get("tokens_per_second"),
                    "error": reply.get("message")
                    if reply.get("state") != "completed"
                    else None,
                }
            )
            if reply.get("state") != "completed":
                break
            history = [
                *history,
                {"role": "user", "content": turn["prompt"]},
                {"role": "assistant", "content": answer},
            ]
            previous = answer
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "title": case["title"],
                "turns": turns,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline Qwen/Heretic Studio quality checks"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run the full suite instead of the first 5 cases",
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of cases for a short run (1 to 50)"
    )
    parser.add_argument("--mode", choices=("stable", "varied"), default="stable")
    parser.add_argument("--max-tokens", type=int, default=128, choices=(64, 128, 256))
    parser.add_argument(
        "--output", type=Path, help="Local JSON report path (contains model answers)"
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    cases = load_cases()
    selected = cases if args.all else cases[: args.limit]
    try:
        token = api_request("/api/downloads/session")["token"]
        session = api_request("/api/chat/current", token).get("session")
        if not isinstance(session, dict) or session.get("state") != "ready":
            raise RuntimeError(
                "Load Qwen from the Chat local interface and wait for 'Modèle prêt à répondre'."
            )
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not re.fullmatch(
            r"[a-f0-9]{32}", session_id
        ):
            raise RuntimeError("No valid local model session")
        print(f"Local loaded model: {session.get('model_id', '?')}")
        results = run_cases(selected, session_id, token, args.mode, args.max_tokens)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Benchmark interrupted: {exc}\n")
    grades = [
        turn["automatic_form_check"] for case in results for turn in case["turns"]
    ]
    report = {
        "dataset": str(SUITE.name),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": session.get("model_id"),
        "revision": session.get("revision"),
        "mode": args.mode,
        "max_new_tokens": args.max_tokens,
        "warning": (
            "These are formal/structural checks ONLY, not factual-accuracy scores. "
            "Human review is required for each answer."
        ),
        "summary": {
            "cases_run": len(results),
            "turns_run": len(grades),
            "formal_pass": grades.count("pass"),
            "formal_fail": grades.count("fail"),
            "human_review": grades.count("human_review"),
            "no_answer": grades.count("no_answer"),
        },
        "results": results,
    }
    output = args.output or Path.home() / ".cache" / "heretic-studio" / "benchmarks" / (
        "french-quality-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + ".json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.exit(1, "Output path already exists. Choose a fresh path.\n")
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Report saved locally: {output}")
    print("Formal checks:", report["summary"])
    print(
        "Factual correctness: NOT scored automatically; review the references in the JSON."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
