#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the generated automation guide."""
import os
import json
import re
import sys
import tempfile
import unittest
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_automation
import build_site


class AutomationPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = cls.temp.name
        cls.count = build_automation.build(cls.root)
        cls.snapshot = build_automation.load_snapshot(ROOT)
        cls.docs = os.path.join(cls.root, "docs")
        cls.pages = {}
        for slug in build_automation.PAGES:
            relative = ("automation/index.html" if slug == "index"
                        else f"automation/{slug}/index.html")
            with open(os.path.join(cls.docs, *relative.split("/")),
                      encoding="utf-8") as stream:
                cls.pages[slug] = stream.read()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_pages_are_generated(self):
        self.assertEqual(self.count, 9)
        self.assertEqual(
            set(self.pages),
            {"index", "research", "reports", "candidates", "h20",
             "selection", "publishing", "limitations", "case-hybrid-c"})

    def test_renderer_escapes_dynamic_text(self):
        rendered = build_automation.pair("<script>x</script>", '" onload="x')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&quot; onload=&quot;x", rendered)

    def test_research_stage_is_mixed_not_mislabeled(self):
        overview = build_automation.overview(self.snapshot)
        research = build_automation.research(self.snapshot)
        self.assertEqual(build_automation.STAGES[0][-1], "mixed")
        self.assertIn("混合：脚本 + Cursor", overview)
        self.assertIn("脚本抓取/评分 + Cursor 全文精读", overview)
        self.assertNotIn("纯脚本", overview + research)
        self.assertIn("Mixed ownership", research)

    def test_dynamic_counts_match_source_data(self):
        with open(os.path.join(ROOT, "data", "review_history.json"),
                  encoding="utf-8") as stream:
            history = json.load(stream)["entries"]
        valid = [
            row for row in history
            if row.get("review_status") == "editorial"
            and row.get("source_depth") == "fulltext"
            and re.match(r"^\d{4}-\d{2}-\d{2}$",
                         str(row.get("review_date", "")))
        ]
        self.assertEqual(self.snapshot["history_count"], len(valid))
        self.assertEqual(self.snapshot["fulltext_count"], len(valid))
        rendered = build_automation.research(self.snapshot)
        for key in ("total_items", "paper_count", "fulltext_count",
                    "abstract_count", "history_count"):
            self.assertIn(f"<b>{self.snapshot[key]}</b>", rendered)
        latest = self.snapshot["latest_review_date"]
        self.assertIn(
            f"<b>{latest} · {self.snapshot['latest_review_count']}</b>",
            rendered)

    def test_real_artifact_links_resolve_to_generated_files(self):
        self.assertGreaterEqual(len(self.snapshot["latest_papers"]), 3)
        research = build_automation.research(self.snapshot)
        self.assertIn(f"{build_automation.BASE}/reviews.html", research)
        latest_day = self.snapshot["latest_day"]
        self.assertTrue(os.path.isfile(
            os.path.join(ROOT, "docs", "days", latest_day + ".html")))
        self.assertIn(f"/days/{latest_day}.html", research)
        for paper in self.snapshot["latest_papers"][:3]:
            self.assertTrue(os.path.isfile(
                os.path.join(ROOT, "docs", "items", paper["id"] + ".html")))
            self.assertIn(f"/items/{paper['id']}.html", research)
            self.assertIn(paper["paper_url"], research)
        for kind in ("detail", "daily"):
            report = self.snapshot["latest_reports"][kind]
            filename = report["href"].rsplit("/", 1)[-1]
            self.assertTrue(os.path.isfile(
                os.path.join(ROOT, "docs", "reports", filename)))
            self.assertIn(report["href"], research)
        self.assertIn(f"{build_automation.BASE}/reports/", research)

    def test_missing_and_malformed_data_falls_back(self):
        missing = build_automation.load_snapshot(self.root)
        self.assertFalse(missing["available"])
        self.assertIn("<b>—</b>", build_automation.research(missing))
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            with open(os.path.join(root, "data", "items.json"), "w",
                      encoding="utf-8") as stream:
                stream.write("{bad json")
            self.assertFalse(build_automation.load_snapshot(root)["available"])

    def test_dynamic_titles_are_html_escaped(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            item = {"id": "safe-id", "kind": "paper",
                    "title": "<script>alert(1)</script>",
                    "url": "https://example.com/paper",
                    "found": "2026-08-06T02:00:00+08:00"}
            payloads = {
                "items.json": {"items": [item],
                               "generated": "2026-08-06T02:00:00+08:00"},
                "explanations.json": {
                    "safe-id": {"review_status": "editorial",
                                "source_depth": "fulltext"}},
                "review_history.json": {"entries": [{
                    "id": "safe-id", "title": item["title"],
                    "paper_url": item["url"], "review_date": "2026-08-06",
                    "reviewed_at": "2026-08-06T02:00:00+08:00",
                    "review_status": "editorial", "source_depth": "fulltext",
                }]},
            }
            for name, payload in payloads.items():
                with open(os.path.join(root, "data", name), "w",
                          encoding="utf-8") as stream:
                    json.dump(payload, stream)
            rendered = build_automation.research(
                build_automation.load_snapshot(root))
            self.assertNotIn("<script>alert(1)</script>", rendered)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)

    def test_required_facts_and_status_are_present(self):
        all_html = "\n".join(self.pages.values())
        for fact in ("99.56%", "81.64%", "1241.6ms", "1195ms", "975ms",
                     "24 / 31", "0 / 31", "GPU 4/5", "GPU 6/7",
                     "188xx", "189xx", "452", "122", "pure audio"):
            with self.subTest(fact=fact):
                self.assertIn(fact, all_html)
        self.assertIn("首次 00:30 定时实跑", self.pages["index"])
        self.assertIn("待验证", self.pages["index"])
        self.assertNotIn("已稳定无人值守运行", self.pages["index"])

    def test_limitations_audits_baselines_and_claim_boundaries(self):
        page = self.pages["limitations"]
        for fact in (
                "B pure-audio", "grouped MoE", "紧凑回执", "确定性确认",
                "Relay", "4/4", "24/31", "31-case", "122",
                "0.7s VAD", "工具名命中不等于参数", "0/31",
                "冻结 holdout", "危险误控为 0", "置信区间",
                "真实车内回放", "系统自我批评页"):
            with self.subTest(fact=fact):
                self.assertIn(fact, page)
        self.assertIn("452 条同口径可比结果属于 B", page)
        self.assertIn("尚无同口径 452 全量结果", page)
        self.assertIn("定性，不是百分比", page)
        self.assertNotIn("Hybrid C 在 452 条评测中", page)
        self.assertIn("禁止表述", page)
        self.assertIn("452 条同口径可比结果属于 B pure-audio 组合", page)

    def test_limitations_links_real_paper_evidence(self):
        page = self.pages["limitations"]
        evidence = {
            "5e1773f2f1": "https://arxiv.org/abs/2603.23346v1",
            "3bebe83725": "https://arxiv.org/abs/2607.26410v1",
            "c8d10ef1c8": "https://huggingface.co/papers/2607.28227",
            "386ec68e80": "https://arxiv.org/abs/2608.01881v1",
            "f474b60b71": "https://arxiv.org/abs/2607.11157v1",
        }
        for iid, source in evidence.items():
            with self.subTest(iid=iid):
                self.assertIn(f"/items/{iid}.html", page)
                self.assertIn(source, page)
                self.assertTrue(os.path.isfile(
                    os.path.join(ROOT, "docs", "items", iid + ".html")))
        self.assertIn("它不提出 typed action 或工具轨迹", page)
        self.assertIn("工程组合是本项目的编辑判断与实验假设", page)

    def test_selection_defines_source_aligned_tiers_and_statuses(self):
        page = self.pages["selection"]
        for fact in (
                "research_eligible", "production_eligible", "pure_audio",
                "full stage", "至少 452 条", "严格 expected-tool",
                "≥99%", "≤1600ms", "复杂集成功≥95%",
                "参数 + 最终车态真值覆盖率=100%",
                "qualified", "pareto", "partial_improvement",
                "rejected", "invalid", "commit_to_call P95 门为 None"):
            with self.subTest(fact=fact):
                self.assertIn(fact, page)
        self.assertIn("多 seed 和置信区间尚未成为当前源码硬门", page)
        self.assertIn("production 才可谈部署", page)

    def test_selection_interactive_tree_is_accessible(self):
        page = self.pages["selection"]
        self.assertIn('class="decision-tree" role="tree"', page)
        self.assertGreaterEqual(page.count('role="treeitem"'), 5)
        self.assertGreaterEqual(page.count('summary tabindex="0"'), 5)
        self.assertIn('aria-label="Decision outcomes"', page)
        self.assertIn("prefers-reduced-motion:reduce", page)
        for gate in ("基础设施与口径有效", "安全门通过", "相对同口径基线有收益",
                     "全部研究/生产硬门通过"):
            self.assertIn(gate, page)

    def test_selection_links_real_registries_and_scoped_verdicts(self):
        page = self.pages["selection"]
        branch = ("https://github.com/ISS-2030Lab/StreamingModelHarness/"
                  "blob/automation/agent-h20-loop/evolution/")
        for path in ("retained_components.json", "RETAINED_COMPONENTS.md",
                     "experiments/registry.json"):
            self.assertIn(branch + path, page)
        for fact in ("99.56%", "81.64%", "1241.6ms", "1818.7ms",
                     "2 条 infrastructure errors", "4 / 4", "1195ms",
                     "975.2ms", "0 / 31"):
            self.assertIn(fact, page)
        self.assertIn("partial_improvement，不是 qualified", page)
        self.assertIn("不能 full qualified", page)
        self.assertNotIn("Hybrid C · 4-case smoke · qualified", page)

    def test_accessibility_responsive_and_reduced_motion(self):
        for slug, text in self.pages.items():
            with self.subTest(slug=slug):
                self.assertIn('name="viewport"', text)
                self.assertIn("@media(max-width:480px)", text)
                self.assertIn("prefers-reduced-motion:reduce", text)
                self.assertIn('aria-label="Site"', text)
                self.assertIn(":focus-visible", text)
                self.assertIn("toggleLang()", text)

    def test_no_external_runtime_resources(self):
        for slug, text in self.pages.items():
            with self.subTest(slug=slug):
                self.assertNotRegex(text, r'<(?:script|img|link)\b[^>]+(?:src|href)="https?://')
                self.assertNotIn("cdn.", text.lower())

    def test_pages_have_sequence_navigation_and_case_crosslinks(self):
        for slug, text in self.pages.items():
            with self.subTest(slug=slug):
                self.assertIn("/automation/", text)
                if slug != "index":
                    self.assertIn('aria-label="Guide sequence"', text)
        for slug in ("research", "reports", "candidates", "h20", "selection",
                     "limitations"):
            self.assertIn("/automation/case-hybrid-c/", self.pages[slug])
        for slug in ("research", "reports", "candidates", "h20",
                     "selection", "publishing", "limitations"):
            self.assertIn(f"/automation/{slug}/", self.pages["case-hybrid-c"])
        for slug in ("index", "candidates", "h20", "selection",
                     "case-hybrid-c"):
            self.assertIn("/automation/limitations/", self.pages[slug])
        for slug in ("candidates", "h20", "selection", "case-hybrid-c"):
            self.assertIn(f"/automation/{slug}/", self.pages["limitations"])

    def test_global_site_navigation_exposes_automation(self):
        rendered = build_site.shell("test", "<p>body</p>", page="index")
        self.assertIn(f'{build_site.BASE}/automation/', rendered)
        self.assertIn(f'{build_site.BASE}/reviews.html', rendered)
        self.assertIn(f'{build_site.BASE}/reports/', rendered)

    def test_internal_automation_links_resolve(self):
        routes = {"/automation/"}
        routes.update(f"/automation/{slug}/" for slug in build_automation.PAGES
                      if slug != "index")
        hrefs = set()
        for text in self.pages.values():
            hrefs.update(re.findall(r'href="([^"]+)"', text))
        for href in hrefs:
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != "piiiiiig.github.io":
                continue
            path = parsed.path
            if path.startswith("/cockpit-agent-radar/automation/"):
                path = path[len("/cockpit-agent-radar"):]
                self.assertIn(path, routes, href)


if __name__ == "__main__":
    unittest.main()
