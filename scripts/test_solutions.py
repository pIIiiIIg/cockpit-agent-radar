#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solution synchronization, filtering, safety, and page regressions."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_site
import build_solutions
import sync_harness_solutions as syncer


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fixture_source(root: Path, malicious: bool = False) -> None:
    name = "<script>bad()</script>" if malicious else "Fixture component"
    components = {
        "schema_version": 1,
        "components": [
            {
                "id": "fixture-component",
                "name": name,
                "status": "conditional",
                "sources": ["docs/FIXTURE.md#evidence"],
                "experiments": ["fixture-experiment"],
                "runtime": {
                    "switch": "--host 10.0.0.8 --token secret-value",
                    "files": ["src/component.py", r"C:\secret\config.json"],
                    "api_key": "do-not-copy",
                },
                "improvement": {
                    "attribution": "combined",
                    "component_evidence": "Scoped positive evidence",
                    "metrics": [{
                        "name": "repair",
                        "value": "3/4",
                        "unit": "",
                        "direction": "higher_is_better",
                        "sample_scope": "fixture bucket",
                        "sample_count": 4,
                        "shared": True,
                    }],
                },
                "evidence_scope": "fixture only",
                "compatibility": "test",
                "dependencies": ["fixture"],
                "risks": ["not full scale"],
                "retention_reason": "positive scoped result",
                "next_validation_gate": "run full holdout",
                "updated_at": "2026-08-07",
                "human_review": {
                    "decision": "conditional",
                    "reviewed_at": "2026-08-07",
                    "notes": "reviewed",
                },
            },
            {
                "id": "retained-component",
                "name": "Retained",
                "status": "retained",
                "sources": [],
                "experiments": [],
                "runtime": {"switch": "", "files": []},
                "improvement": {"attribution": "direct", "metrics": []},
                "updated_at": "2026-08-06",
            },
            {
                "id": "rejected-component",
                "name": "Rejected",
                "status": "rejected",
                "sources": [],
                "experiments": ["rejected-experiment"],
                "runtime": {"switch": "", "files": []},
                "improvement": {
                    "attribution": "direct",
                    "component_evidence": "no gain",
                    "metrics": [{
                        "name": "fixed", "value": "0/31", "unit": "",
                        "direction": "higher_is_better",
                        "sample_scope": "error bucket", "sample_count": 31,
                    }],
                },
                "updated_at": "2026-08-07",
            },
        ],
    }
    registry = {
        "schema_version": 1,
        "experiments": [
            {
                "id": "fixture-experiment",
                "status": "partial_improvement",
                "safety": {"passed": True, "dangerous_miscalls": 0},
                "sample_count": 4,
                "metrics": {"accuracy": 0.75},
                "delta": {"accuracy": 0.75},
                "buckets": {"scope": "fixture"},
                "branch": "experiment/fixture",
                "known_limitations": "fixture",
                "reproduce": "--host internal.example --key private",
                "artifacts": [{
                    "path": "evolution/experiments/artifacts/fixture/summary.json",
                    "hash": "sha256:fixture",
                    "source": r"C:\private\run.json",
                }],
            },
            {
                "id": "rejected-experiment",
                "status": "rejected",
                "safety": {"passed": True, "dangerous_miscalls": 0},
                "sample_count": 31,
                "metrics": {"accuracy": 0.0},
                "delta": {"fixed": 0},
                "single_variable": "description",
                "conclusion": "0/31",
                "artifacts": [],
            },
        ],
    }
    summary = {
        "samples": 4, "completed": 4, "accuracy": 0.75,
        "host": "private.internal", "log_path": r"C:\private\run.log",
    }
    write_json(root / syncer.COMPONENT_PATH, components)
    write_json(root / syncer.REGISTRY_PATH, registry)
    write_json(
        root / "evolution/experiments/artifacts/fixture/summary.json", summary)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/FIXTURE.md").write_text("fixture", encoding="utf-8")
    (root / "src").mkdir(exist_ok=True)
    (root / "src/component.py").write_text("pass\n", encoding="utf-8")


def test_shell(title: str, body: str, page: str = "") -> str:
    return (
        '<!doctype html><html data-lang="zh"><head><title>' + title + '</title>'
        '<meta name="description" content="' + title + '"><style>'
        '@media(prefers-reduced-motion:reduce){*{transition:none}}'
        '</style></head><body data-page="' + page + '">'
        + body + "</body></html>")


class SolutionSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.snapshot = self.root / "data/harness_solutions.json"
        fixture_source(self.source)
        self.now = datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def sync(self):
        return syncer.sync(
            self.source, "", self.snapshot, fetch=False, now=self.now)

    def test_sync_is_idempotent_and_uses_source_numbers(self):
        first, changed = self.sync()
        self.assertTrue(changed)
        second, changed = self.sync()
        self.assertFalse(changed)
        self.assertEqual(first, second)
        row = next(row for row in first["components"]
                   if row["id"] == "fixture-component")
        self.assertEqual(
            row["improvement"]["metrics"][0]["value"], "3/4")
        self.assertEqual(
            row["experiment_records"][0]["metrics"]["accuracy"], 0.75)
        self.assertEqual(first["schema_version"], 2)
        evidence = row["evidence"][0]
        self.assertEqual(evidence["current"]["value"], "3/4")
        self.assertEqual(evidence["sample_count"], 4)
        self.assertEqual(evidence["attribution"], "combined")
        self.assertEqual(evidence["evidence"]["branch"], "experiment/fixture")

    def test_sync_redacts_secrets_hosts_and_local_paths(self):
        payload, _ = self.sync()
        rendered = json.dumps(payload, ensure_ascii=False)
        for forbidden in (
                "do-not-copy", "secret-value", "10.0.0.8",
                r"C:\secret", r"C:\private", "internal.example"):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("[redacted]", rendered)

    def test_status_filter_and_combination_attribution(self):
        payload, _ = self.sync()
        rows = {row["id"]: row for row in payload["components"]}
        self.assertTrue(rows["fixture-component"]["recommended"])
        self.assertTrue(rows["retained-component"]["recommended"])
        self.assertFalse(rows["rejected-component"]["recommended"])
        self.assertEqual(
            rows["fixture-component"]["improvement"]["metrics"][0]["attribution"],
            "combination_only")
        self.assertEqual(
            {row["id"] for row in payload["negative_results"]},
            {"rejected-experiment"})

    def test_stale_failure_preserves_previous_snapshot(self):
        fresh, _ = self.sync()
        stale, changed = syncer.sync(
            self.root / "missing", "", self.snapshot,
            fetch=False, now=self.now)
        self.assertTrue(changed)
        self.assertEqual(stale["source"]["status"], "stale")
        self.assertEqual(stale["components"], fresh["components"])
        self.assertEqual(stale["negative_results"], fresh["negative_results"])

    def test_unsafe_id_does_not_publish(self):
        components = json.loads(
            (self.source / syncer.COMPONENT_PATH).read_text(encoding="utf-8"))
        components["components"][0]["id"] = "../escape"
        write_json(self.source / syncer.COMPONENT_PATH, components)
        payload, _ = self.sync()
        self.assertEqual(payload["source"]["status"], "stale")
        self.assertEqual(payload["components"], [])

    def test_history_uses_reviewed_beijing_date(self):
        payload, _ = self.sync()
        row = next(row for row in payload["components"]
                   if row["id"] == "fixture-component")
        self.assertEqual(row["history"], [{
            "date": "2026-08-07", "kind": "added",
            "summary": "Initial public solution snapshot",
        }])

    def test_component_update_preserves_history(self):
        self.sync()
        components = json.loads(
            (self.source / syncer.COMPONENT_PATH).read_text(encoding="utf-8"))
        components["components"][0]["retention_reason"] = "new scoped evidence"
        components["components"][0]["updated_at"] = "2026-08-08"
        write_json(self.source / syncer.COMPONENT_PATH, components)
        payload, changed = syncer.sync(
            self.source, "", self.snapshot, fetch=False,
            now=datetime(2026, 8, 8, 2, 0, tzinfo=timezone.utc))
        self.assertTrue(changed)
        row = next(row for row in payload["components"]
                   if row["id"] == "fixture-component")
        self.assertEqual(
            [(event["date"], event["kind"]) for event in row["history"]],
            [("2026-08-07", "added"), ("2026-08-08", "updated")])

    def test_dynamic_text_is_escaped_in_pages(self):
        fixture_source(self.source, malicious=True)
        payload, _ = self.sync()
        build_solutions.build(
            self.root, self.root / "docs",
            "https://example.test", test_shell)
        page = (self.root / "docs/solutions/index.html").read_text(
            encoding="utf-8")
        self.assertNotIn("<script>bad()</script>", page)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", page)
        self.assertEqual(len(build_solutions.recommended(payload)), 2)

    def test_unknown_evidence_fallback_and_bilingual_status(self):
        self.sync()
        build_solutions.build(
            self.root, self.root / "docs",
            "https://example.test", test_shell)
        detail = (self.root / "docs/solutions/retained-component.html").read_text(
            encoding="utf-8")
        self.assertIn("证据未知", detail)
        self.assertIn("Evidence unknown", detail)
        self.assertIn("保留", detail)
        self.assertIn("Retained", detail)

    def test_build_fails_when_candidate_day_has_no_activity(self):
        root = self.root / "coverage"
        write_json(root / "data/harness_solutions.json", {"components": []})
        write_json(root / "data/experiment_activity.json", {"days": {}})
        write_json(root / "data/handoff/ledger.json", {"days": {
            "2026-08-10": {"stages": {
                "candidate_publish": {"status": "complete"}}}}})
        with self.assertRaisesRegex(ValueError, "no activity record"):
            build_solutions.build(
                root, root / "docs", "https://example.test", test_shell)

    def test_combined_evidence_is_not_component_attributed(self):
        self.sync()
        build_solutions.build(
            self.root, self.root / "docs",
            "https://example.test", test_shell)
        page = (self.root / "docs/solutions/index.html").read_text(
            encoding="utf-8")
        self.assertIn("组合实验有收益，单组件提升未知", page)
        self.assertNotIn("fixture bucket 3/4 →", page)


class PublishedSolutionPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = build_solutions.load_snapshot(ROOT)
        cls.temp = tempfile.TemporaryDirectory()
        cls.docs = Path(cls.temp.name) / "docs"
        cls.result = build_solutions.build(
            ROOT, cls.docs, build_site.BASE, test_shell)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_current_snapshot_has_required_first_batch(self):
        rows = {row["id"]: row for row in self.snapshot["components"]}
        expected = {
            "grouped-mm-hopper", "terse-execution-receipt",
            "deterministic-post-execution-ack", "relay-safe-prefix",
            "audio-derived-asr-prefetch", "voice-memory-rules",
            "candidate-authorized-typed-resolver",
        }
        self.assertEqual(expected - set(rows), set())
        self.assertTrue(all(rows[item]["recommended"] for item in expected))
        self.assertTrue(all(
            rows[item].get("conditional_reason") or rows[item].get("retention_reason")
            for item in expected))
        self.assertFalse(rows["tool-description-enhancement"]["recommended"])

    def test_index_daily_and_detail_pages_exist(self):
        self.assertEqual(self.result["recommended"], 7)
        expected_negative = sum(
            isinstance(row, dict) and row.get("status") in {"rejected", "invalid"}
            for row in self.snapshot.get("negative_results", []))
        self.assertEqual(self.result["negative"], expected_negative)
        self.assertGreaterEqual(self.result["negative"], 1)
        self.assertTrue((self.docs / "solutions/index.html").is_file())
        for date in ("2026-08-08", "2026-08-09", "2026-08-10"):
            self.assertTrue(
                (self.docs / f"solutions/days/{date}.html").is_file())
        for component in build_solutions.recommended(self.snapshot):
            self.assertTrue(
                (self.docs / "solutions" / f"{component['id']}.html").is_file())
        self.assertTrue(
            (self.docs / "solutions/tool-description-enhancement.html").is_file())

    def test_daily_workbench_does_not_impersonate_solutions(self):
        index = (self.docs / "solutions/index.html").read_text(encoding="utf-8")
        day = (self.docs / "solutions/days/2026-08-10.html").read_text(
            encoding="utf-8")
        for fact in (
                "第一层：正式保留 / 高收益组件", "第二层：每日实验工作台",
                "候选实验不会冒充好方案", "今日实验活动=", "查看全部每日实验"):
            self.assertIn(fact, index)
        for fact in (
                "OmniVoice 16-step", "complex_control_cases v2",
                "full canary 已通过", "H20 complex122 + full452 canary",
                "strict 43/122", "4d84220",
                "当天产出", "Pairwise 修正 / 退化"):
            self.assertIn(fact, day)

    def test_candidate_ledger_days_have_activity(self):
        activity = build_solutions.load_activity(ROOT)
        build_solutions.validate_activity_coverage(ROOT, activity)
        for date in ("2026-08-08", "2026-08-09", "2026-08-10"):
            self.assertTrue(build_solutions.activities_on(activity, date))

    def test_detail_pages_have_required_sections_and_source_numbers(self):
        page = (self.docs / "solutions/voice-memory-rules.html").read_text(
            encoding="utf-8")
        for fact in (
                "它解决什么", "What it solves", "改了哪段链路",
                "Pipeline change", "怎么实现", "Implementation",
                "开关", "Metrics, delta, and scope", "24/31", "31",
                "组合上下文，不能归因", "风险、兼容性与未改善项",
                "证据表", "Evidence table", "基线", "当前", "delta",
                "是否独立", "下一验证门", "Version and change history"):
            with self.subTest(fact=fact):
                self.assertIn(fact, page)
        self.assertIn("prefers-reduced-motion", page)
        self.assertIn("<details>", page)
        self.assertIn('summary tabindex="0"', page)

    def test_index_comparisons_match_snapshot_and_format_directions(self):
        page = (self.docs / "solutions/index.html").read_text(encoding="utf-8")
        self.assertIn("0/31", page)
        self.assertIn("24/31", page)
        self.assertIn("组合实验有收益，单组件提升未知", page)
        for component in self.snapshot["components"]:
            for evidence in component.get("evidence", []):
                self.assertIn(
                    evidence.get("direction"),
                    {"higher_is_better", "lower_is_better", "unknown"})
                delta = evidence.get("delta", {}).get("value")
                if isinstance(delta, (int, float)) and delta > 0:
                    detail = (self.docs / "solutions" /
                              f"{component['id']}.html")
                    if detail.exists():
                        self.assertIn(f"+{delta:g}", detail.read_text(encoding="utf-8"))

    def test_rejected_detail_explains_zero_gain(self):
        page = (self.docs / "solutions/tool-description-enhancement.html").read_text(
            encoding="utf-8")
        self.assertIn("拒绝原因", page)
        self.assertIn("0/31", page)
        rejected = next(row for row in self.snapshot["components"]
                        if row["id"] == "tool-description-enhancement")
        self.assertEqual(rejected["evidence"][0]["delta"]["value"], 0)

    def test_internal_solution_links_resolve_and_no_runtime_cdn(self):
        pages = list((self.docs / "solutions").rglob("*.html"))
        hrefs = set()
        for path in pages:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text, r'<(?:script|img|link)\b[^>]+(?:src|href)="https?://')
            self.assertNotIn("cdn.", text.lower())
            hrefs.update(re.findall(r'href="([^"]+)"', text))
        for href in hrefs:
            parsed = urlparse(href)
            prefix = "/cockpit-agent-radar/solutions/"
            if parsed.path.startswith(prefix):
                name = parsed.path[len(prefix):] or "index.html"
                self.assertTrue((self.docs / "solutions" / name).is_file(), href)

    def test_activity_dates_sort_newest_first_and_use_stable_urls(self):
        activity = build_solutions.load_activity(ROOT)
        self.assertEqual(
            build_solutions.activity_dates(activity),
            ["2026-08-10", "2026-08-09", "2026-08-08"])
        index = (self.docs / "solutions/index.html").read_text(encoding="utf-8")
        positions = [
            index.index(f"/solutions/days/{date}.html")
            for date in build_solutions.activity_dates(activity)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("/solutions/days/2026-08-10.html", index)

    def test_prev_next_boundaries_and_research_links(self):
        newest = (self.docs / "solutions/days/2026-08-10.html").read_text(
            encoding="utf-8")
        middle = (self.docs / "solutions/days/2026-08-09.html").read_text(
            encoding="utf-8")
        oldest = (self.docs / "solutions/days/2026-08-08.html").read_text(
            encoding="utf-8")
        self.assertIn('aria-disabled="true"', newest)
        self.assertIn("/solutions/days/2026-08-09.html", newest)
        self.assertIn("/solutions/days/2026-08-08.html", middle)
        self.assertIn("/solutions/days/2026-08-10.html", middle)
        self.assertIn('aria-disabled="true"', oldest)
        for date, page in (("2026-08-10", newest), ("2026-08-08", oldest)):
            self.assertIn(f"/days/{date}.html", page)
            self.assertIn(f"<title>{date}", page)
            self.assertIn(f'<meta name="description" content="{date}', page)

    def test_exhausted_day_without_experiments_is_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "data/harness_solutions.json", {"components": []})
            write_json(root / "data/experiment_activity.json", {"days": {
                "2026-08-11": {
                    "summary": {
                        "fulltext_reviews": 7,
                        "candidates_generated": 0,
                        "research_exhausted": True,
                    },
                    "activities": [],
                }}})
            write_json(root / "data/handoff/ledger.json", {"days": {
                "2026-08-11": {"stages": {
                    "candidate_publish": {"status": "complete"}}}}})
            build_solutions.build(
                root, root / "docs", "https://example.test", test_shell)
            page = (root / "docs/solutions/days/2026-08-11.html").read_text(
                encoding="utf-8")
            self.assertIn("当天研究已穷尽", page)
            self.assertIn("精读=7", page)
            self.assertNotIn("当日实验活动未记录", page)

    def test_build_is_idempotent_and_generated_pages_have_no_secrets(self):
        first = {
            path.relative_to(self.docs): path.read_bytes()
            for path in (self.docs / "solutions").rglob("*.html")}
        build_solutions.build(ROOT, self.docs, build_site.BASE, test_shell)
        second = {
            path.relative_to(self.docs): path.read_bytes()
            for path in (self.docs / "solutions").rglob("*.html")}
        self.assertEqual(first, second)
        rendered = b"\n".join(second.values()).decode("utf-8")
        for forbidden in ("MOONSHOT_API_KEY=", "BEGIN PRIVATE KEY",
                          r"C:\Users\\", ".moonshot_key"):
            self.assertNotIn(forbidden, rendered)

    def test_every_navigation_link_has_a_generated_file(self):
        for page in (self.docs / "solutions").rglob("*.html"):
            text = page.read_text(encoding="utf-8")
            for href in re.findall(
                    rf'href="{re.escape(build_site.BASE)}/solutions/([^"#?]+)"',
                    text):
                target = self.docs / "solutions" / (
                    href if href else "index.html")
                if href.endswith("/"):
                    target = target / "index.html"
                self.assertTrue(target.is_file(), f"{page.name}: {href}")

    def test_report_feedback_is_separate_and_date_scoped(self):
        block = build_solutions.feedback_section(
            self.snapshot, "2026-08-06", build_site.BASE)
        self.assertIn("正式保留 / 高收益组件", block)
        self.assertIn("每日实验工作台", block)
        self.assertIn("/solutions/", block)
        empty = build_solutions.feedback_section(
            self.snapshot, "2099-01-01", build_site.BASE)
        self.assertIn("新增/更新的保留组件：0", empty)

    def test_report_solution_links_resolve(self):
        for report in (ROOT / "docs" / "reports").glob("*.html"):
            text = report.read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', text):
                parsed = urlparse(href)
                prefix = "/cockpit-agent-radar/solutions/"
                if parsed.path.startswith(prefix):
                    name = parsed.path[len(prefix):] or "index.html"
                    self.assertTrue(
                        (self.docs / "solutions" / name).is_file(),
                        f"{report.name}: {href}")

    def test_global_navigation_links_solutions(self):
        rendered = build_site.shell("test", "<p>body</p>")
        self.assertIn(f'{build_site.BASE}/solutions/', rendered)


if __name__ == "__main__":
    unittest.main()
