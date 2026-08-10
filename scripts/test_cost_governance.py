import json
import tempfile
import unittest
from pathlib import Path

import build_agent_packet
import build_deterministic_daily
from cost_governance import CostLedger, sha256_text


class RadarCostGovernanceTests(unittest.TestCase):
    def test_packet_caps_canonical_papers_and_groups_mirrors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            items = []
            explanations = {}
            for index in range(8):
                item_id = f"paper-{index}"
                items.append({
                    "id": item_id, "kind": "paper", "title": f"Paper {index}",
                    "canonical_id": f"canonical-{index}", "score": 9,
                    "url": f"https://example.test/{index}",
                })
                explanations[item_id] = {"review_status": "abstract_backfill"}
            items.append({
                "id": "paper-0-mirror", "kind": "paper", "title": "Paper 0 mirror",
                "canonical_id": "canonical-0", "score": 8,
                "url": "https://example.test/mirror",
            })
            explanations["paper-0-mirror"] = {"review_status": "abstract_backfill"}
            (root / "data/items.json").write_text(
                json.dumps({"items": items}), encoding="utf-8")
            (root / "data/explanations.json").write_text(
                json.dumps(explanations), encoding="utf-8")
            packet = build_agent_packet.deep_review(root, 6, 6)
            self.assertEqual(packet["selected_canonical_papers"], 6)
            self.assertEqual(packet["queued_canonical_papers"], 2)
            self.assertIn("paper-0-mirror", packet["papers"][0]["mirror_ids"])

    def test_same_fact_skeleton_has_stable_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data/handoff/candidates").mkdir(parents=True)
            (root / "project_status").mkdir()
            (root / "data/items.json").write_text(
                json.dumps({"items": []}), encoding="utf-8")
            status = root / "project_status/StreamingModelHarness.md"
            status.write_text("# Status\n生成时间：first\nsame facts\n", encoding="utf-8")
            first = build_agent_packet.daily_report(root, "2026-08-10")
            status.write_text("# Status\n生成时间：second\nsame facts\n", encoding="utf-8")
            second = build_agent_packet.daily_report(root, "2026-08-10")
            self.assertEqual(
                sha256_text(json.dumps(first, sort_keys=True)),
                sha256_text(json.dumps(second, sort_keys=True)))

    def test_shared_ledger_public_status_contains_queue_counts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = CostLedger(root)
            path = root / "public.json"
            ledger.write_public_status(path, extra={
                "queued_fulltext_papers": 4,
                "queued_harness_candidates": 1,
            })
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["queued_fulltext_papers"], 4)
            self.assertEqual(value["queued_harness_candidates"], 1)
            self.assertNotIn("input_hash", value)

    def test_retry_script_uses_two_attempts_and_same_chat(self):
        script = Path(__file__).with_name("automation_common.ps1").read_text(
            encoding="utf-8")
        self.assertIn("[int]$Attempts = 2", script)
        self.assertIn("--resume $chatId", script)
        self.assertIn("--output-format json", script)
        self.assertNotIn("--model \"gpt-5.6-sol-xhigh\"", script)

    def test_deterministic_daily_is_zero_agent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            packet = {
                "schema_version": 1, "kind": "daily_report",
                "target_date": "2026-08-11",
                "project_status": "# Status\n- measured fact",
                "latest_items": [{
                    "id": "p1", "title": "Verified paper",
                    "url": "https://example.test/p1", "score": 9,
                    "summary_zh": "结构化摘要",
                }],
            }
            checked = build_deterministic_daily.validate_packet(
                packet, "2026-08-11")
            first = build_deterministic_daily.render(root, checked, "2026-08-11")
            second = build_deterministic_daily.render(root, checked, "2026-08-11")
            self.assertTrue(first["reports_changed"])
            self.assertFalse(second["reports_changed"])
            self.assertTrue(
                (root / "reports/每日调研日报-2026-08-11.md").is_file())
            candidate = json.loads((root /
                "data/handoff/candidates/2026-08-11.json").read_text(encoding="utf-8"))
            self.assertEqual(candidate["generation"], "deterministic_no_agent")
            self.assertEqual(candidate["candidates"], [])

    def test_uncovered_daily_schema_has_deterministic_queue_fallback(self):
        with self.assertRaisesRegex(ValueError, "unsupported packet schema"):
            build_deterministic_daily.validate_packet({
                "schema_version": 2, "kind": "daily_report",
            }, "2026-08-11")


if __name__ == "__main__":
    unittest.main()
