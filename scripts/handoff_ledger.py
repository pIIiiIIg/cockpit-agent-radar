#!/usr/bin/env python3
"""Durable, public-safe Radar/Harness handoff ledger and catch-up scanner."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/handoff/ledger.json"
STAGES = (
    "fulltext_review", "problem_report", "duplex_report", "candidate_publish",
    "candidate_ack", "offline_replay", "h20_evaluation", "result_manifest",
    "radar_writeback",
)
TERMINAL = {"complete", "rejected", "not_applicable"}
STATUSES = {"pending", "running", "failed", *TERMINAL}
SECRET = re.compile(
    r"(secret|token|password|private[_-]?key|ssh[_-]?key|host|private[_-]?ip)",
    re.I,
)
PRIVATE_VALUE = re.compile(
    r"(BEGIN [A-Z ]*PRIVATE KEY|(?:\d{1,3}\.){3}\d{1,3}|"
    r"(?:ssh|scp)://|[A-Za-z]:\\Users\\[^\\]+\\\.ssh)",
    re.I,
)


def now():
    return datetime.now(timezone.utc).isoformat()


def empty():
    return {
        "schema_version": 1, "timezone": "Asia/Shanghai",
        "catchup_start": "2026-08-08", "updated_at": now(),
        "days": {}, "candidate_fingerprints": {}, "experiment_identities": {},
    }


def load(path=LEDGER):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else empty()
    except (OSError, ValueError):
        return empty()


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def assert_public_safe(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if SECRET.search(str(key)):
                raise ValueError(f"private field forbidden: {child_path}")
            assert_public_safe(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_public_safe(child, f"{path}[{index}]")
    elif isinstance(value, str) and PRIVATE_VALUE.search(value):
        raise ValueError(f"private value forbidden: {path}")


def update_stage(ledger, day, stage, status, **values):
    date.fromisoformat(day)
    if stage not in STAGES or status not in STATUSES:
        raise ValueError("invalid ledger transition")
    current = ledger.setdefault("days", {}).setdefault(day, {}).setdefault(
        "stages", {}).get(stage, {})
    if current.get("status") in TERMINAL and status == "running":
        return ledger
    retries = int(current.get("retries", 0))
    if values.pop("retry", False):
        retries += 1
    ledger["days"][day]["stages"][stage] = {
        **current, **values, "status": status, "retries": retries,
        "updated_at": now(),
    }
    ledger["updated_at"] = now()
    assert_public_safe(ledger)
    return ledger


def missing_dates(ledger, since, through):
    current, end = date.fromisoformat(since), date.fromisoformat(through)
    missing = []
    while current <= end:
        day = current.isoformat()
        stages = ledger.get("days", {}).get(day, {}).get("stages", {})
        if any(stages.get(stage, {}).get("status") not in TERMINAL for stage in (
                "fulltext_review", "problem_report", "duplex_report")):
            missing.append(day)
        current += timedelta(days=1)
    return missing


def stale_alerts(ledger, at=None):
    at = at or datetime.now(timezone.utc)
    alerts = []
    for day, value in sorted(ledger.get("days", {}).items()):
        stages = value.get("stages", {})
        for stage in STAGES:
            row = stages.get(stage, {})
            if row.get("status") in TERMINAL:
                continue
            raw = row.get("updated_at") or f"{day}T00:00:00+00:00"
            try:
                updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                updated = datetime.min.replace(tzinfo=timezone.utc)
            if at.astimezone(timezone.utc) - updated.astimezone(
                    timezone.utc) > timedelta(hours=24):
                alerts.append({
                    "date": day, "stage": stage, "status": "stale",
                    "message": f"{day} {stage} has no terminal evidence within 24h",
                })
    return alerts


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--since", required=True)
    scan.add_argument("--through", default=date.today().isoformat())
    stage = sub.add_parser("stage")
    stage.add_argument("--date", required=True)
    stage.add_argument("--stage", choices=STAGES, required=True)
    stage.add_argument("--status", choices=STATUSES, required=True)
    stage.add_argument("--input-commit", default="")
    stage.add_argument("--output-commit", default="")
    stage.add_argument("--artifact", default="")
    stage.add_argument("--error", default="")
    stage.add_argument("--next-stage", default="")
    stage.add_argument("--retry", action="store_true")
    sub.add_parser("next")
    sub.add_parser("check-stale")
    sub.add_parser("status")
    args = parser.parse_args()
    ledger = load()
    if args.command == "scan":
        print(json.dumps(
            {"missing_dates": missing_dates(ledger, args.since, args.through),
             "stale_alerts": stale_alerts(ledger)},
            ensure_ascii=False, indent=2))
    elif args.command == "next":
        missing = missing_dates(
            ledger, ledger.get("catchup_start", date.today().isoformat()),
            date.today().isoformat())
        print(missing[0] if missing else date.today().isoformat())
    elif args.command == "check-stale":
        alerts = stale_alerts(ledger)
        print(json.dumps({"stale_alerts": alerts}, ensure_ascii=False, indent=2))
        if alerts:
            raise SystemExit(2)
    elif args.command == "status":
        print(json.dumps(
            {"ledger": ledger, "stale_alerts": stale_alerts(ledger)},
            ensure_ascii=False, indent=2))
    else:
        values = {
            "input_commit": args.input_commit,
            "output_commit": args.output_commit,
            "artifact": args.artifact,
            "error": args.error,
            "next_stage": args.next_stage,
            "retry": args.retry,
        }
        atomic_write(
            LEDGER, update_stage(
                ledger, args.date, args.stage, args.status, **values))


if __name__ == "__main__":
    main()
