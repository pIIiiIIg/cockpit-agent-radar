#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synchronize public, allowlisted Harness solution evidence into the radar.

The source worktree is never checked out or edited. When a git ref is supplied,
files are read with ``git show`` after an optional fetch. Sync failure is
non-fatal: the previous snapshot is retained and marked stale.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "harness_solutions.json"
CST = timezone(timedelta(hours=8))
COMPONENT_PATH = "evolution/retained_components.json"
REGISTRY_PATH = "evolution/experiments/registry.json"
SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SECRETISH = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|bearer\s+|token\s*[=:])")
LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:\\|/home/|/Users/|\\\\[^\\\s]+\\)")

COMPONENT_FIELDS = {
    "id", "name", "status", "sources", "experiments", "runtime",
    "improvement", "evidence_scope", "compatibility", "dependencies",
    "risks", "retention_reason", "next_validation_gate", "updated_at",
    "human_review",
}
EXPERIMENT_FIELDS = {
    "id", "parent_id", "baseline_id", "single_variable", "sources",
    "commit", "profile", "sample_count", "buckets", "metrics",
    "complex_intent", "safety", "delta", "status", "conclusion",
    "retention_reason", "known_limitations", "reproduce", "artifacts",
    "branch", "recorded_at", "qualified",
}
SUMMARY_FIELDS = {
    "sample_count", "samples", "completed", "completion_rate", "accuracy",
    "actual_execution_success_rate", "e2e_p95_ms", "call_p95_ms",
    "commit_to_call_p95_ms", "dangerous_miscalls", "errors", "profile",
}
ATTRIBUTIONS = {"direct", "component_specific", "combined", "unknown"}


def _run(args: list[str], cwd: Path, *, check: bool = True) -> str:
    result = subprocess.run(
        args, cwd=cwd, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} command failed")
    return result.stdout.strip()


def _safe_text(value: Any) -> str:
    text = str(value or "")
    if SECRETISH.search(text):
        return "[redacted]"
    text = re.sub(
        r"(?i)((?<![\w-])--(?:host|hostname|key|token|password)\s+)\S+",
        r"\1[redacted]", text)
    text = re.sub(
        r"(?<![\d.])(?:10|127|172\.(?:1[6-9]|2\d|3[01])|192\.168)"
        r"(?:\.\d{1,3}){2,3}(?::\d+)?", "[private-host]", text)
    text = LOCAL_PATH.sub("[local-path]", text)
    # Hostnames/IPs are not useful public evidence. Preserve public URLs only.
    text = re.sub(
        r"(?i)\b(?:ssh|https?)://(?!github\.com|arxiv\.org|huggingface\.co)"
        r"[^/\s]+", "[private-host]", text)
    return text[:4000]


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            _safe_text(key): sanitize(item)
            for key, item in value.items()
            if not SECRETISH.search(str(key))
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(value)


def _load_json_text(text: str, label: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


class Source:
    def __init__(self, root: Path, branch: str = "", fetch: bool = True,
                 git: str = ""):
        self.root = root
        self.branch = branch
        self.fetch = fetch
        self.ref = ""
        self.commit = ""
        self.repository = ""
        self.git = (
            git or os.environ.get("GIT_EXECUTABLE") or shutil.which("git")
            or r"C:\Program Files\Git\cmd\git.exe")

    def prepare(self) -> None:
        if not self.root.is_dir():
            raise OSError("Harness source directory unavailable")
        git_dir = self.root / ".git"
        if git_dir.exists() and self.branch:
            if self.fetch:
                _run([self.git, "fetch", "origin", self.branch], self.root)
                self.ref = "FETCH_HEAD"
            else:
                self.ref = f"origin/{self.branch}"
            self.commit = _run([self.git, "rev-parse", self.ref], self.root)
            remote = _run([self.git, "remote", "get-url", "origin"], self.root)
            match = re.search(
                r"(?:github\.com[:/])([^/\s]+/[^/\s]+?)(?:\.git)?$", remote)
            if match:
                self.repository = f"https://github.com/{match.group(1)}"
        else:
            self.commit = self._working_digest()
            self.ref = "working-tree"

    def _working_digest(self) -> str:
        digest = hashlib.sha256()
        for relative in (COMPONENT_PATH, REGISTRY_PATH):
            digest.update((self.root / relative).read_bytes())
        return digest.hexdigest()

    def read_text(self, relative: str) -> str:
        if self.ref and self.ref != "working-tree":
            return _run([self.git, "show", f"{self.ref}:{relative}"], self.root)
        return (self.root / relative).read_text(encoding="utf-8")

    def read_json(self, relative: str) -> dict[str, Any]:
        return _load_json_text(self.read_text(relative), relative)

    def github_url(self, relative: str, branch: str | None = None) -> str:
        if not self.repository:
            return ""
        ref = branch or self.branch
        if not ref or not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
            return ""
        safe_path = "/".join(quote(part, safe="") for part in relative.split("/"))
        return f"{self.repository}/blob/{ref}/{safe_path}"


def _allow(source: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    return sanitize({key: source[key] for key in fields if key in source})


def _metric_positive(metric: dict[str, Any]) -> bool:
    value = metric.get("value")
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        fraction = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
        if fraction:
            return int(fraction.group(1)) > 0 and int(fraction.group(2)) > 0
    return False


def _unknown() -> dict[str, Any]:
    return {"value": None, "label": "unknown"}


def _metric_evidence(metric: dict[str, Any],
                     improvement: dict[str, Any],
                     linked: list[dict[str, Any]],
                     experiments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Normalize one public source metric without inventing comparisons."""
    experiment = linked[0] if linked else {}
    attribution = str(improvement.get("attribution") or "unknown")
    if attribution not in ATTRIBUTIONS:
        attribution = "unknown"
    if metric.get("shared"):
        attribution = "combined"
    name = str(metric.get("name") or "unknown")
    value = metric.get("value")
    baseline: dict[str, Any] = _unknown()
    current: dict[str, Any] = {"value": value, "label": name}
    delta: dict[str, Any] = _unknown()

    # Source component metrics named as savings/avoidance are deltas, not
    # absolute measurements. Preserve that distinction in the public schema.
    if isinstance(value, (int, float)) and any(
            token in name.lower() for token in ("节省", "规避", "saving", "avoid")):
        current = _unknown()
        delta = {"value": value, "label": name}

    registry_delta = experiment.get("delta")
    if isinstance(registry_delta, dict):
        if name in {"组合修复", "修复"} and registry_delta.get("fixed_errors") is not None:
            fixed = registry_delta["fixed_errors"]
            delta = {"value": fixed, "label": "fixed_errors"}
            sample_count = metric.get("sample_count")
            current = {
                "value": f"{fixed}/{sample_count}" if sample_count else fixed,
                "label": name,
            }
            baseline_id = str(experiment.get("baseline_id") or "")
            baseline_experiment = experiments.get(baseline_id, {})
            baseline_metrics = baseline_experiment.get("metrics", {})
            baseline_rate = (
                baseline_metrics.get("actual_execution_success_rate")
                if isinstance(baseline_metrics, dict) else None)
            if baseline_rate == 0 and sample_count:
                baseline = {
                    "value": f"0/{sample_count}",
                    "label": baseline_id,
                }
        elif value == 0 and registry_delta:
            matching = next(
                (item for item in registry_delta.values()
                 if isinstance(item, (int, float)) and item == 0), None)
            if matching == 0:
                delta = {"value": 0, "label": "no_gain"}

    branch = experiment.get("branch")
    scope = metric.get("sample_scope") or (
        experiment.get("buckets", {}).get("scope")
        if isinstance(experiment.get("buckets"), dict) else None)
    hardware = "unknown"
    component_evidence = str(improvement.get("component_evidence") or "")
    hardware_match = re.search(
        r"(?i)\b(?:H20|H100|H200|Hopper|Blackwell|GPU)\b[^。.;]{0,100}",
        component_evidence)
    if hardware_match:
        hardware = hardware_match.group(0)
    return sanitize({
        "metric": name,
        "metric_definition": name,
        "baseline": baseline,
        "current": current,
        "delta": delta,
        "unit": metric.get("unit") or "",
        "direction": metric.get("direction") or "unknown",
        "sample_count": metric.get("sample_count"),
        "sample_scope": scope or "unknown",
        "hardware": hardware,
        "attribution": attribution,
        "independent_ab": False if attribution == "combined" else None,
        "evidence": {
            "experiment": experiment.get("id") or "unknown",
            "branch": branch or "unknown",
        },
        "confidence": "combined_only" if attribution == "combined" else "source_recorded",
    })


def _safe_date(value: Any, fallback: str) -> str:
    text = str(value or "")[:10]
    return text if DATE.fullmatch(text) else fallback


def _experiment_public(raw: dict[str, Any], source: Source) -> dict[str, Any]:
    row = _allow(raw, EXPERIMENT_FIELDS)
    branch = str(row.get("branch") or "")
    if branch and source.repository and re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        row["github_url"] = f"{source.repository}/tree/{branch}"
    artifacts = []
    for artifact in raw.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        path = str(artifact.get("path") or "")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or ".." in Path(path).parts:
            continue
        public = {
            "path": path,
            "hash": _safe_text(artifact.get("hash")),
            "github_url": source.github_url(path),
        }
        if path.endswith("summary.json"):
            try:
                summary = source.read_json(path)
                public["summary"] = sanitize({
                    key: summary[key] for key in SUMMARY_FIELDS if key in summary
                })
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
                pass
        artifacts.append(public)
    row["artifacts"] = artifacts
    return row


def _component_public(raw: dict[str, Any], experiments: dict[str, dict[str, Any]],
                      source: Source, fallback_date: str) -> dict[str, Any]:
    component_id = str(raw.get("id") or "")
    if not SAFE_ID.fullmatch(component_id) or ".." in component_id:
        raise ValueError(f"unsafe component id: {component_id!r}")
    row = _allow(raw, COMPONENT_FIELDS)
    row["id"] = component_id
    updated = _safe_date(raw.get("updated_at"), fallback_date)
    review = raw.get("human_review") if isinstance(raw.get("human_review"), dict) else {}
    row["updated_at"] = max(
        updated, _safe_date(review.get("reviewed_at"), updated))
    linked = [
        experiments[experiment_id]
        for experiment_id in row.get("experiments", [])
        if experiment_id in experiments
    ]
    row["experiment_records"] = linked
    runtime = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
    files = []
    for path in runtime.get("files", []):
        if (isinstance(path, str)
                and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                and ".." not in Path(path).parts):
            files.append({
                "path": path,
                "github_url": source.github_url(path),
            })
    runtime["files"] = files
    row["runtime"] = runtime
    improvement = row.get("improvement")
    if not isinstance(improvement, dict):
        improvement = {}
    metrics = []
    for metric in improvement.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        public_metric = sanitize(metric)
        public_metric["attribution"] = (
            "combination_only"
            if metric.get("shared") or improvement.get("attribution") == "combined"
            else "component")
        metrics.append(public_metric)
    improvement["metrics"] = metrics
    row["improvement"] = improvement
    status = str(row.get("status") or "")
    reason = str(row.get("retention_reason") or "")
    row["retention_reason"] = reason
    row["conditional_reason"] = reason if status == "conditional" else ""
    row["evidence"] = [
        _metric_evidence(metric, improvement, linked, experiments)
        for metric in metrics
    ]
    row["evidence_maturity"] = status or "unknown"
    safety_rows = [
        record.get("safety") for record in linked
        if isinstance(record.get("safety"), dict)]
    safety_ok = bool(safety_rows) and all(
        record.get("safety", {}).get("passed") is not False
        and record.get("safety", {}).get("dangerous_miscalls", 0) in (0, None)
        for record in linked if isinstance(record.get("safety"), dict))
    outcome_ok = any(
        record.get("status") in {
            "qualified", "pareto", "partial_improvement"}
        for record in linked)
    has_positive = any(
        _metric_positive(metric)
        and bool(metric.get("sample_scope"))
        and metric.get("sample_count") not in (None, 0)
        for metric in metrics)
    row["recommended"] = bool(
        status in {"qualified", "retained"}
        or (status in {"conditional", "partial_improvement"}
            and has_positive and safety_ok and outcome_ok
            and bool(improvement.get("component_evidence"))))
    row["selection_basis"] = {
        "status_allowed": status in {
            "qualified", "retained", "conditional", "partial_improvement"},
        "positive_metric": has_positive,
        "safety_not_regressed": safety_ok,
        "eligible_experiment_outcome": outcome_ok,
    }
    return row


def _fingerprint(row: dict[str, Any]) -> str:
    ignored = {"history"}
    value = {key: row[key] for key in row if key not in ignored}
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_snapshot(source: Source, previous: dict[str, Any] | None,
                   now: datetime) -> dict[str, Any]:
    source.prepare()
    component_data = source.read_json(COMPONENT_PATH)
    registry_data = source.read_json(REGISTRY_PATH)
    fallback_date = now.astimezone(CST).date().isoformat()
    experiment_rows = {}
    for raw in registry_data.get("experiments", []):
        if not isinstance(raw, dict) or not SAFE_ID.fullmatch(str(raw.get("id") or "")):
            continue
        public = _experiment_public(raw, source)
        experiment_rows[public["id"]] = public
    previous_rows = {
        row["id"]: row for row in (previous or {}).get("components", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    same_source_commit = (
        (previous or {}).get("source", {}).get("commit") == source.commit)
    components = []
    for raw in component_data.get("components", []):
        if not isinstance(raw, dict):
            continue
        component = _component_public(
            raw, experiment_rows, source, fallback_date)
        old = previous_rows.get(component["id"])
        history = copy.deepcopy(old.get("history", [])) if old else []
        if old is None:
            history.append({
                "date": component["updated_at"],
                "kind": "added",
                "summary": "Initial public solution snapshot",
            })
        elif not same_source_commit and _fingerprint(component) != _fingerprint(old):
            history.append({
                "date": component["updated_at"],
                "kind": "updated",
                "summary": "Source registry evidence updated",
            })
        component["history"] = history
        components.append(component)
    components.sort(key=lambda row: (row["updated_at"], row["id"]), reverse=True)
    rejected = [
        experiment for experiment in experiment_rows.values()
        if experiment.get("status") in {"rejected", "invalid"}
    ]
    previous_source = (previous or {}).get("source", {})
    same_commit = (
        previous_source.get("commit") == source.commit
        and previous_source.get("status") == "fresh")
    synced_at = (
        previous_source.get("synced_at") if same_commit
        else now.astimezone(CST).isoformat(timespec="seconds"))
    return {
        "schema_version": 2,
        "source": {
            "status": "fresh",
            "repository": source.repository,
            "branch": source.branch or "working-tree",
            "commit": source.commit,
            "synced_at": synced_at,
            "component_path": COMPONENT_PATH,
            "registry_path": REGISTRY_PATH,
        },
        "components": components,
        "negative_results": sorted(
            rejected, key=lambda row: row.get("recorded_at", ""), reverse=True),
    }


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def write_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        if path.read_text(encoding="utf-8") == rendered:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    os.replace(temp, path)
    return True


def mark_stale(previous: dict[str, Any], error: Exception,
               now: datetime) -> dict[str, Any]:
    payload = copy.deepcopy(previous) if previous else {
        "schema_version": 2, "components": [], "negative_results": []}
    source = payload.setdefault("source", {})
    source["status"] = "stale"
    source["last_attempt"] = now.astimezone(CST).isoformat(timespec="seconds")
    source["warning"] = _safe_text(type(error).__name__ + ": source unavailable")
    return payload


def sync(source_path: Path, branch: str, snapshot_path: Path = SNAPSHOT,
         *, fetch: bool = True, now: datetime | None = None,
         git: str = "") -> tuple[dict[str, Any], bool]:
    now = now or datetime.now(CST)
    previous = load_snapshot(snapshot_path)
    try:
        payload = build_snapshot(
            Source(source_path, branch=branch, fetch=fetch, git=git),
            previous, now)
    except Exception as error:  # stale is deliberately non-fatal
        payload = mark_stale(previous, error, now)
        print(f"warning: Harness solutions snapshot is stale ({type(error).__name__})",
              file=sys.stderr)
    changed = write_if_changed(snapshot_path, payload)
    return payload, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path,
        default=Path(os.environ.get(
            "HARNESS_SOLUTIONS_SOURCE", ROOT.parent / "StreamingModelHarness")))
    parser.add_argument(
        "--branch", default=os.environ.get(
            "HARNESS_SOLUTIONS_BRANCH", "automation/agent-h20-loop"))
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--git", default=os.environ.get("GIT_EXECUTABLE", ""))
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    payload, changed = sync(
        args.source, args.branch, args.snapshot, fetch=not args.no_fetch,
        git=args.git)
    recommended = sum(
        row.get("recommended") is True for row in payload.get("components", []))
    print(
        f"harness solutions: status={payload.get('source', {}).get('status', 'stale')} "
        f"recommended={recommended} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
