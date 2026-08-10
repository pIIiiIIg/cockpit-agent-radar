"""Build minimal, deterministic Radar Agent inputs without scanning generated docs."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BEIJING = timezone(timedelta(hours=8))


def load(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def canonical_key(item: dict[str, Any]) -> str:
    for key in ("canonical_id", "arxiv_id", "paper_id"):
        if item.get(key):
            return str(item[key]).strip().lower()
    title = " ".join(str(item.get("title", "")).lower().split())
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def deep_review(repo: Path, limit: int, min_score: float) -> dict[str, Any]:
    items_value = load(repo / "data/items.json", [])
    items = items_value.get("items", items_value) if isinstance(items_value, dict) else items_value
    explanations = load(repo / "data/explanations.json", {})
    explanation_rows = explanations.get("items", explanations)
    pending = []
    selected: dict[str, dict[str, Any]] = {}
    eligible_keys = set()
    for item in sorted(
        (row for row in items if isinstance(row, dict)),
        key=lambda row: (
            -float(row.get("score", 0) or 0),
            str(row.get("date") or row.get("found") or ""),
        ),
    ):
        item_id = str(item.get("id", ""))
        explanation = explanation_rows.get(item_id, {}) if isinstance(explanation_rows, dict) else {}
        if explanation.get("review_status") not in {"abstract_backfill", "pending", None}:
            continue
        if float(item.get("score", 0) or 0) < min_score:
            continue
        key = canonical_key(item)
        eligible_keys.add(key)
        if key in selected:
            selected[key]["mirror_ids"].append(item_id)
            continue
        if len(pending) >= limit:
            continue
        row = {
            "id": item_id,
            "canonical_key": key,
            "mirror_ids": [],
            "title": item.get("title"),
            "url": item.get("url"),
            "found": item.get("found") or item.get("date"),
            "score": item.get("score"),
            "summary": item.get("summary") or item.get("summary_zh"),
            "current_explanation": explanation,
        }
        selected[key] = row
        pending.append(row)
    return {
        "schema_version": 1,
        "kind": "deep_review",
        "canonical_paper_limit": limit,
        "minimum_score": min_score,
        "selected_canonical_papers": len(pending),
        "queued_canonical_papers": max(0, len(eligible_keys) - len(pending)),
        "papers": pending,
        "instructions": {
            "only_these_ids": True,
            "do_not_scan": ["docs/", "docs/items/"],
            "mirror_ids_do_not_count_against_limit": True,
        },
    }


def daily_report(repo: Path, target_date: str) -> dict[str, Any]:
    status_path = repo / "project_status/StreamingModelHarness.md"
    status_text = status_path.read_text(
        encoding="utf-8", errors="replace") if status_path.is_file() else ""
    status_text = "\n".join(
        line for line in status_text.splitlines()
        if not line.startswith(("生成时间：", "Generated at:")))
    items_value = load(repo / "data/items.json", [])
    items = items_value.get("items", items_value) if isinstance(items_value, dict) else items_value
    candidates = load(repo / f"data/handoff/candidates/{target_date}.json", {})
    latest = sorted(
        (row for row in items if isinstance(row, dict)),
        key=lambda row: str(row.get("found") or row.get("date") or ""),
        reverse=True,
    )[:20]
    return {
        "schema_version": 1,
        "kind": "daily_report",
        "target_date": target_date,
        "project_status": status_text,
        "latest_items": [{
            key: row.get(key) for key in (
                "id", "title", "url", "found", "date", "score", "summary_zh")
        } for row in latest],
        "existing_candidates": candidates,
        "instructions": {
            "fact_skeleton_only": True,
            "do_not_scan": ["docs/", "docs/items/", "reports/ except previous report"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--kind", choices=("deep-review", "daily-report"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--min-score", type=float, default=6.0)
    parser.add_argument("--target-date", default="")
    args = parser.parse_args()
    if args.limit < 1:
        raise ValueError("limit must be positive")
    value = (
        deep_review(args.repo, min(args.limit, 6), args.min_score)
        if args.kind == "deep-review"
        else daily_report(args.repo, args.target_date)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(text, encoding="utf-8")
    print(json.dumps({
        "path": str(args.output),
        "input_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "selected_canonical_papers": value.get("selected_canonical_papers"),
        "queued_canonical_papers": value.get("queued_canonical_papers"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
