import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import handoff_ledger


class HandoffLedgerTests(unittest.TestCase):
    def test_two_day_catchup_and_partial_failure_resume(self):
        ledger = handoff_ledger.empty()
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "fulltext_review", "complete",
            input_commit="a", output_commit="b")
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "problem_report", "failed",
            error="transient", next_stage="problem_report")
        self.assertEqual(
            handoff_ledger.missing_dates(
                ledger, "2026-08-08", "2026-08-09"),
            ["2026-08-08", "2026-08-09"])
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "problem_report", "complete", retry=True)
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "duplex_report", "complete")
        self.assertEqual(
            handoff_ledger.missing_dates(
                ledger, "2026-08-08", "2026-08-09"),
            ["2026-08-09"])

    def test_terminal_stage_is_idempotent(self):
        ledger = handoff_ledger.empty()
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "problem_report", "complete")
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "problem_report", "running")
        self.assertEqual(
            ledger["days"]["2026-08-08"]["stages"]["problem_report"]["status"],
            "complete")

    def test_atomic_roundtrip_and_result_writeback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            ledger = handoff_ledger.empty()
            handoff_ledger.update_stage(
                ledger, "2026-08-08", "result_manifest", "complete",
                artifact="public/results/candidate.json")
            handoff_ledger.atomic_write(path, ledger)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                loaded["days"]["2026-08-08"]["stages"]["result_manifest"][
                    "status"],
                "complete")

    def test_stale_alert_and_secret_scan(self):
        ledger = handoff_ledger.empty()
        handoff_ledger.update_stage(
            ledger, "2026-08-08", "fulltext_review", "complete")
        alerts = handoff_ledger.stale_alerts(
            ledger, datetime(2026, 8, 10, tzinfo=timezone.utc))
        self.assertTrue(any(row["stage"] == "problem_report" for row in alerts))
        for value in (
                {"ssh_key": "x"},
                {"note": "10.0.0.1"},
                {"note": "-----BEGIN PRIVATE KEY-----"}):
            with self.assertRaises(ValueError):
                handoff_ledger.assert_public_safe(value)


if __name__ == "__main__":
    unittest.main()
