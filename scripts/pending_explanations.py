#!/usr/bin/env python3
"""列出缺失或仍为摘要速读的论文，供 Cursor 自动化与人工补录使用。"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--since", default="")
    parser.add_argument("--missing-only", action="store_true")
    args = parser.parse_args()
    with open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8") as stream:
        items = json.load(stream)["items"]
    with open(os.path.join(ROOT, "data", "explanations.json"), encoding="utf-8") as stream:
        explanations = json.load(stream)
    pending = []
    for item in items:
        if item["kind"] != "paper" or item.get("found", "")[:10] < args.since:
            continue
        explanation = explanations.get(item["id"])
        status = (explanation or {}).get("review_status", "missing")
        if status == "missing" or (not args.missing_only and status == "abstract_backfill"):
            pending.append((item, status))
    pending.sort(key=lambda row: (row[0].get("found", ""), row[0].get("score", 0)),
                 reverse=True)
    if args.limit:
        pending = pending[:args.limit]
    for item, status in pending:
        print(f"{item['id']}\t{item['found'][:10]}\t{item['score']}\t{status}"
              f"\t{item['title']}\t{item['url']}")
    print(f"pending={len(pending)}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
