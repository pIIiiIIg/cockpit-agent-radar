#!/usr/bin/env python3
"""Import only public-safe research metadata; never copy private drafts."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "research_outputs.json"
ALLOWED_STATUS = {"idea", "preliminary", "submission-ready", "human-approved"}
PRIVATE = re.compile(
    r"(?i)(private_ip|private_publication|api[_-]?key|secret|password|"
    r"(?:[a-z]:\\|/home/|/mnt/)|(?:ssh|https?)://[^/\s]+@)")


def sanitize(source):
    if source.get("schema_version") != 1:
        raise ValueError("unsupported research outputs schema")
    clean = {"schema_version": 1, "outputs": []}
    ids = set()
    for item in source.get("outputs", []):
        if item.get("id") in ids:
            raise ValueError("duplicate research output id")
        ids.add(item.get("id"))
        if item.get("status") not in ALLOWED_STATUS:
            raise ValueError("invalid research output status")
        allowed = {
            key: item.get(key) for key in (
                "id", "title_zh", "title_en", "status", "experiments",
                "evidence_completeness", "paper_url", "wechat_url",
                "patent_drafting", "patent_filed", "human_approved",
                "public_release_allowed", "updated_at")
        }
        release = bool(item.get("patent_filed") and item.get("human_approved")
                       and item.get("public_release_allowed"))
        if not release:
            allowed["paper_url"] = None
            allowed["wechat_url"] = None
            if item.get("status") == "human-approved":
                allowed["status"] = "preliminary"
        blob = json.dumps(allowed, ensure_ascii=False)
        if PRIVATE.search(blob):
            raise ValueError("private path, host, or credential pattern detected")
        clean["outputs"].append(allowed)
    clean["outputs"].sort(key=lambda value: value["id"])
    return clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    clean = sanitize(json.loads(args.source.read_text(encoding="utf-8")))
    rendered = json.dumps(clean, ensure_ascii=False, indent=2) + "\n"
    if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != rendered:
        TARGET.write_text(rendered, encoding="utf-8")
    print(f"synced {len(clean['outputs'])} public-safe research outputs")


if __name__ == "__main__":
    main()
