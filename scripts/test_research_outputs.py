import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_research_outputs import sanitize

ROOT = Path(__file__).resolve().parents[1]


def output(**updates):
    value = {
        "id": "p1", "title_zh": "研究", "title_en": "Research",
        "status": "preliminary", "experiments": ["e1"],
        "evidence_completeness": 0.5,
        "paper_url": "https://example.org/paper",
        "wechat_url": "https://example.org/wechat",
        "patent_drafting": "in_progress", "patent_filed": False,
        "human_approved": False, "public_release_allowed": False,
        "updated_at": "2026-08-09T00:00:00Z",
    }
    value.update(updates)
    return value


class ResearchOutputsTests(unittest.TestCase):
    def test_unfiled_or_unapproved_links_are_stripped(self):
        clean = sanitize({"schema_version": 1, "outputs": [output()]})
        self.assertIsNone(clean["outputs"][0]["paper_url"])
        self.assertIsNone(clean["outputs"][0]["wechat_url"])

    def test_release_requires_both_gates(self):
        clean = sanitize({"schema_version": 1, "outputs": [output(
            patent_filed=True, human_approved=True, public_release_allowed=True)]})
        self.assertEqual(clean["outputs"][0]["paper_url"], "https://example.org/paper")

    def test_private_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "private"):
            sanitize({"schema_version": 1, "outputs": [output(
                title_zh="C:\\private_ip\\claims.md")]})

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            sanitize({"schema_version": 1, "outputs": [output(), output()]})

    def test_site_build_contains_research_outputs_page(self):
        subprocess.run([sys.executable, "scripts/build_site.py"], cwd=ROOT, check=True)
        page = ROOT / "docs/research-outputs/index.html"
        self.assertTrue(page.is_file())
        text = page.read_text(encoding="utf-8")
        self.assertIn("Research Outputs", text)
        self.assertNotIn("private_ip", text)


if __name__ == "__main__":
    unittest.main()
