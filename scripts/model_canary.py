"""Fixed, low-cost quality canaries for Radar narrative models."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cost_governance import CostLedger, ledger_root, sha256_text

BEIJING = timezone(timedelta(hours=8))
CANARY_VERSION = "radar-model-canary-v1"
CANARIES = {
    "deep_review": {
        "sentinel": "DEEP_REVIEW_COMPLETE",
        "prompt": (
            "Return JSON only. Evidence: paper_id=canary-paper; verified claim="
            "'System A improved exact match from 40% to 50%'; official citation="
            "https://example.org/paper#table-1. Required schema: schema_version=1, "
            "paper_id, claim, citation, sentinel. Copy only the verified claim and "
            "citation; sentinel must be DEEP_REVIEW_COMPLETE. Do not use tools."
        ),
        "expected": {
            "schema_version": 1,
            "paper_id": "canary-paper",
            "claim": "System A improved exact match from 40% to 50%",
            "citation": "https://example.org/paper#table-1",
            "sentinel": "DEEP_REVIEW_COMPLETE",
        },
    },
    "daily_report": {
        "sentinel": "REPORT_TASK_COMPLETE",
        "prompt": (
            "Return JSON only. Fact skeleton: date=2026-08-10; measured baseline="
            "'40/100'; allowed recommendation='test one variable'; citation="
            "https://example.org/run#baseline. Required schema: schema_version=1, "
            "date, fact, recommendation, citation, sentinel. Do not invent facts; "
            "sentinel must be REPORT_TASK_COMPLETE. Do not use tools."
        ),
        "expected": {
            "schema_version": 1,
            "date": "2026-08-10",
            "fact": "40/100",
            "recommendation": "test one variable",
            "citation": "https://example.org/run#baseline",
            "sentinel": "REPORT_TASK_COMPLETE",
        },
    },
}


def certification_path() -> Path:
    return ledger_root() / "model-canary.json"


def parse_result(output: str) -> dict[str, Any]:
    outer = json.loads(output.strip())
    result = str(outer.get("result", "")).strip()
    if result.startswith("```"):
        result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(result)
    if not isinstance(value, dict):
        raise ValueError("canary result is not an object")
    return value


def run_one(agent: Path, workspace: Path, model: str, name: str) -> dict[str, Any]:
    spec = CANARIES[name]
    ledger = CostLedger()
    input_hash = sha256_text(f"{CANARY_VERSION}\0{model}\0{name}\0{spec['prompt']}")
    reservation = ledger.reserve(
        pipeline="radar", stage=f"model_canary_{name}", pool="radar_review_report",
        model=model, chat_session="", attempt=1, reservation_usd=0.5,
        input_hash=input_hash)
    process = subprocess.run([
        str(agent), "--print", "--mode", "ask", "--trust",
        "--workspace", str(workspace), "--model", model,
        "--output-format", "json", spec["prompt"],
    ], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180)
    output = process.stdout or process.stderr
    reconciled = ledger.reconcile(
        reservation.call_id, output, failed=process.returncode != 0,
        error=f"exit code {process.returncode}" if process.returncode else "")
    if process.returncode:
        raise RuntimeError(f"{name} canary Agent failed with exit {process.returncode}")
    value = parse_result(output)
    missing = {}
    for key, expected in spec["expected"].items():
        actual = value.get(key)
        if key == "fact":
            matches = expected in str(actual)
        else:
            matches = actual == expected
        if not matches:
            missing[key] = expected
    if missing:
        raise ValueError(f"{name} canary schema/fact/citation mismatch: {sorted(missing)}")
    if reconciled["tool_calls"]:
        raise ValueError(f"{name} canary unexpectedly used tools")
    return {
        "status": "passed", "input_hash": input_hash,
        "result_hash": reconciled["result_hash"],
        "usage_source": reconciled["usage_source"],
        "actual_usd": reconciled["actual_usd"],
    }


def run(agent: Path, workspace: Path, model: str) -> int:
    models = subprocess.run(
        [str(agent), "--list-models"], text=True, encoding="utf-8",
        errors="replace", capture_output=True, timeout=60, check=True).stdout
    available = {
        line.split(" - ", 1)[0].strip() for line in models.splitlines()
        if " - " in line
    }
    if model not in available:
        raise RuntimeError(f"canary model unavailable: {model}")
    results = {}
    status = "passed"
    error = ""
    try:
        for name in CANARIES:
            results[name] = run_one(agent, workspace, model, name)
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    path = certification_path()
    existing = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    models_status = existing.get("models", {})
    models_status[model] = {
        "status": status, "canary_version": CANARY_VERSION,
        "checked_at": datetime.now(BEIJING).isoformat(),
        "checks": results, "error": error,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "models": models_status,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(models_status[model], ensure_ascii=False))
    return 0 if status == "passed" else 1


def verify(model: str) -> int:
    path = certification_path()
    value = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    row = value.get("models", {}).get(model, {})
    ok = row.get("status") == "passed" and row.get("canary_version") == CANARY_VERSION
    if not ok:
        print(json.dumps({
            "status": "missing_or_failed", "model": model,
            "reason": "run fixed canaries; no automatic expensive fallback is permitted",
        }))
        return 1
    print(json.dumps({"status": "passed", "model": model}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--agent", type=Path, required=True)
    run_parser.add_argument("--workspace", type=Path, required=True)
    run_parser.add_argument("--model", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--model", required=True)
    args = parser.parse_args()
    return (
        run(args.agent, args.workspace, args.model)
        if args.command == "run" else verify(args.model)
    )


if __name__ == "__main__":
    raise SystemExit(main())
