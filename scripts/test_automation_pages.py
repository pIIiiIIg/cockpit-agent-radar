#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the generated automation guide."""
import os
import re
import sys
import tempfile
import unittest
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_automation


class AutomationPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = cls.temp.name
        cls.count = build_automation.build(cls.root)
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
        self.assertEqual(self.count, 8)
        self.assertEqual(
            set(self.pages),
            {"index", "research", "reports", "candidates", "h20",
             "selection", "publishing", "case-hybrid-c"})

    def test_renderer_escapes_dynamic_text(self):
        rendered = build_automation.pair("<script>x</script>", '" onload="x')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&quot; onload=&quot;x", rendered)

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
        for slug in ("research", "reports", "candidates", "h20", "selection"):
            self.assertIn("/automation/case-hybrid-c/", self.pages[slug])
        for slug in ("research", "reports", "candidates", "h20",
                     "selection", "publishing"):
            self.assertIn(f"/automation/{slug}/", self.pages["case-hybrid-c"])

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
