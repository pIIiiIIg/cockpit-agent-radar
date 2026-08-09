#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Track verified full-text editorial upgrades without counting abstract backfill."""
import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(ROOT, "data", "review_history.json")
CST = timezone(timedelta(hours=8))
BASE = "https://piiiiiig.github.io/cockpit-agent-radar"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return default


def is_fulltext_editorial(row):
    return (isinstance(row, dict)
            and row.get("review_status") == "editorial"
            and row.get("source_depth") == "fulltext")


def snapshot(explanations):
    return {
        iid: {
            "review_status": row.get("review_status"),
            "source_depth": row.get("source_depth"),
        }
        for iid, row in explanations.items() if isinstance(row, dict)
    }


def upgraded_ids(before, after):
    """IDs that entered the strict editorial/fulltext state during this run."""
    return sorted(
        iid for iid, row in after.items()
        if is_fulltext_editorial(row)
        and not is_fulltext_editorial(before.get(iid, {}))
    )


def parse_cst(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed.astimezone(CST)


def title_key(title):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (title or "").casefold())


def empty_history():
    return {
        "schema_version": 1,
        "timezone": "Asia/Shanghai",
        "description": (
            "Only transitions to review_status=editorial and source_depth=fulltext; "
            "abstract_backfill and missing explanations are never reviews."
        ),
        "entries": [],
    }


def normalize_history(history):
    if not isinstance(history, dict):
        history = empty_history()
    history.setdefault("schema_version", 1)
    history.setdefault("timezone", "Asia/Shanghai")
    history.setdefault("description", empty_history()["description"])
    history["entries"] = history.get("entries", [])
    if not isinstance(history["entries"], list):
        history["entries"] = []
    return history


def item_map(items):
    rows = items.get("items", []) if isinstance(items, dict) else []
    return {row["id"]: row for row in rows
            if isinstance(row, dict) and row.get("id")}


def make_entry(iid, item, reviewed_at, origin, backfilled=False):
    return {
        "id": iid,
        "title": item.get("title", iid),
        "paper_url": item.get("url", ""),
        "detail_url": f"{BASE}/items/{iid}.html",
        "reviewed_at": reviewed_at.isoformat(),
        "review_date": reviewed_at.date().isoformat(),
        "source_depth": "fulltext",
        "review_status": "editorial",
        "origin": origin,
        "backfilled": bool(backfilled),
        "canonical_id": iid,
        "mirror_of": None,
    }


def mark_mirrors(entries):
    canonical = {}
    for row in sorted(entries, key=lambda value: (value["reviewed_at"], value["id"])):
        key = title_key(row.get("title"))
        if key and key in canonical:
            row["canonical_id"] = canonical[key]
            row["mirror_of"] = canonical[key]
        else:
            canonical[key] = row["id"]
            row["canonical_id"] = row["id"]
            row["mirror_of"] = None


def merge_entries(history, additions):
    """Idempotently add each paper's first verified full-text editorial review."""
    history = normalize_history(history)
    known = {row.get("id") for row in history["entries"]}
    history["entries"].extend(row for row in additions if row["id"] not in known)
    history["entries"].sort(
        key=lambda row: (row.get("reviewed_at", ""), row.get("id", "")),
        reverse=True)
    mark_mirrors(history["entries"])
    return history


def atomic_write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".review-history-", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def record_upgrades(
        history, before, after, items, reviewed_at, run_id, batch,
        catchup_for=""):
    rows = item_map(items)
    origin = {
        "kind": "automation-batch", "run_id": run_id, "batch": batch,
        "catchup_for": catchup_for or None,
    }
    additions = [
        make_entry(iid, rows[iid], reviewed_at, origin)
        for iid in upgraded_ids(before, after) if iid in rows
    ]
    return merge_entries(history, additions), len(additions)


def backfill_history(history, explanations, items):
    rows = item_map(items)
    additions = []
    for iid, explanation in explanations.items():
        if not is_fulltext_editorial(explanation) or iid not in rows:
            continue
        generated_at = explanation.get("generated_at")
        try:
            reviewed_at = parse_cst(generated_at)
        except (AttributeError, TypeError, ValueError):
            # An unverifiable date is not guessed and cannot be placed on a day page.
            continue
        origin = {
            "kind": "historical-backfill",
            "run_id": None,
            "batch": None,
            "source_generated_at": generated_at,
        }
        additions.append(
            make_entry(iid, rows[iid], reviewed_at, origin, backfilled=True))
    return merge_entries(history, additions), len(additions)


def file_hash(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", required=True)
    record = sub.add_parser("record")
    record.add_argument("--before", required=True)
    record.add_argument("--reviewed-at", default="")
    record.add_argument("--run-id", default="")
    record.add_argument("--batch", default="deep-review")
    record.add_argument(
        "--catchup-for", default="",
        help="Missed schedule date; reviewed_at remains the truthful execution time")
    sub.add_parser("backfill")
    args = parser.parse_args()

    explanations_path = os.path.join(ROOT, "data", "explanations.json")
    items_path = os.path.join(ROOT, "data", "items.json")
    explanations = load_json(explanations_path, {})
    items = load_json(items_path, {"items": []})

    if args.command == "snapshot":
        atomic_write(args.output, snapshot(explanations))
        print(f"snapshot: {len(explanations)} explanations")
        return

    history = load_json(HISTORY_PATH, empty_history())
    if args.command == "backfill":
        history, count = backfill_history(history, explanations, items)
    else:
        before = load_json(args.before, {})
        reviewed_at = parse_cst(args.reviewed_at) if args.reviewed_at else datetime.now(CST)
        run_id = args.run_id or (
            reviewed_at.strftime("%Y%m%dT%H%M%S%z") + "-" + file_hash(args.before))
        history, count = record_upgrades(
            history, before, explanations, items, reviewed_at, run_id,
            args.batch, args.catchup_for)
    atomic_write(HISTORY_PATH, history)
    print(f"review history: {count} candidate entries, {len(history['entries'])} total")


if __name__ == "__main__":
    main()
