#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文讲解 schema 与静态 HTML 安全回归（零第三方依赖）。"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_site
import fetch_rank
from paper_context import MAX_CONTEXT, PaperHTML, _select_context


class ExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "data", "items.json"),
                  encoding="utf-8") as stream:
            cls.items = json.load(stream)["items"]
        with open(os.path.join(ROOT, "data", "explanations.json"),
                  encoding="utf-8") as stream:
            cls.explanations = json.load(stream)
        cls.ids = {item["id"] for item in cls.items}

    def test_explanations_reference_real_papers(self):
        paper_ids = {item["id"] for item in self.items if item["kind"] == "paper"}
        self.assertTrue(self.explanations)
        self.assertEqual(set(self.explanations) - paper_ids, set())

    def test_required_schema(self):
        for iid, row in self.explanations.items():
            with self.subTest(iid=iid):
                for key in ("tl_dr", "problem", "method"):
                    self.assertIsInstance(row.get(key), str)
                    self.assertGreater(len(row[key]), 8)
                for key in ("workflow", "findings", "project_fit", "limitations"):
                    self.assertIsInstance(row.get(key), list)
                    self.assertTrue(all(isinstance(value, str) for value in row[key]))
                opened = row.get("open_source")
                self.assertIsInstance(opened, dict)
                self.assertIn(opened.get("status"),
                              {"open", "partial", "unavailable", "unknown"})
                for key in ("code_url", "model_url"):
                    url = opened.get(key, "")
                    self.assertTrue(not url or url.startswith("https://"))

    def test_all_july30_papers_have_explanations(self):
        expected = {item["id"] for item in self.items
                    if item["kind"] == "paper"
                    and item["found"].startswith("2026-07-30")}
        self.assertEqual(expected - set(self.explanations), set())
        self.assertEqual(self.explanations["6c53ea8835"]["review_status"],
                         "editorial")

    def test_render_escapes_model_text(self):
        row = {
            "tl_dr": "<script>alert(1)</script>",
            "problem": "problem text",
            "method": "method text",
            "workflow": ["<img src=x onerror=alert(1)>"],
            "findings": [],
            "project_fit": [],
            "limitations": [],
            "open_source": {"status": "unknown", "note": "", "code_url": "",
                            "model_url": ""},
        }
        rendered = build_site.explanation_block(row)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img ", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_paper_parser_keeps_text_and_trusted_links(self):
        parser = PaperHTML()
        parser.feed("""
        <html><script>bad()</script><h2>Method</h2><p>Useful result.</p>
        <a href="https://github.com/example/repo">code</a>
        <a href="javascript:alert(1)">bad</a></html>
        """)
        text, links = parser.result()
        self.assertIn("Method", text)
        self.assertIn("Useful result.", text)
        self.assertNotIn("bad()", text)
        self.assertEqual(links, ["https://github.com/example/repo"])

    def test_multimodal_agent_and_vla_are_radar_topics(self):
        agent_score, _ = fetch_rank.score(
            "A realtime multimodal agent with native audio", "")
        vla_score, _ = fetch_rank.score(
            "Streaming vision-language-action model", "")
        self.assertGreaterEqual(agent_score, fetch_rank.THRESH["arxiv"])
        self.assertGreaterEqual(vla_score, fetch_rank.THRESH["arxiv"])

    def test_long_paper_context_keeps_results(self):
        text = "Introduction\n" + ("background " * 4000)
        text += "\nResults\nThe measured latency is 240 ms.\n"
        selected = _select_context(text)
        self.assertLessEqual(len(selected), MAX_CONTEXT)
        self.assertIn("The measured latency is 240 ms.", selected)

    def test_new_item_limit_applies_after_existing_dedup(self):
        existing = [{
            "url": f"https://example.com/old-{index}",
            "score": 99 - index,
            "found": "2026-07-30T09:00:00+08:00",
            "stars": None,
        } for index in range(20)]
        fresh = [dict(row, score=100) for row in existing]
        fresh += [{
            "url": f"https://example.com/new-{index}",
            "score": 10 - index,
            "found": "2026-07-31T09:00:00+08:00",
            "stars": None,
        } for index in range(3)]
        merged, added, updated, candidates = fetch_rank.merge_items(
            existing, fresh, new_limit=2)
        urls = {row["url"] for row in merged}
        self.assertEqual(added, 2)
        self.assertEqual(updated, 20)
        self.assertEqual(candidates, 3)
        self.assertIn("https://example.com/new-0", urls)
        self.assertIn("https://example.com/new-1", urls)

    def test_empty_scan_day_has_visible_status(self):
        rendered = build_site.no_updates()
        self.assertIn("本日扫描已完成", rendered)
        self.assertIn("Scan completed", rendered)

    def test_report_markdown_is_escaped_and_structured(self):
        rendered = build_site.markdown_to_html(
            "# 标题\n\n- **重点** `code`\n\n"
            "| 指标 | 值 |\n|---|---|\n| recall | 99% |\n\n"
            "<script>alert(1)</script>")
        self.assertIn("<h1>标题</h1>", rendered)
        self.assertIn("<strong>重点</strong>", rendered)
        self.assertIn("<table>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
