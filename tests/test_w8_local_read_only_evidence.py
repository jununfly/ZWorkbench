from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner.run_w8_local_read_only_evidence import run_evidence_suite


class W8LocalReadOnlyEvidenceTests(unittest.TestCase):
    def test_first_slice_evidence_passes_backup_restore_and_security_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "evidence"
            summary = run_evidence_suite(output_dir)

            self.assertEqual(summary["status"], "pass")
            self.assertTrue(summary["checks"]["backup_restore_pass"])
            self.assertTrue(summary["checks"]["network_attempts_zero"])
            self.assertEqual(summary["observed"]["security_case_count"], 3)
            self.assertEqual(summary["observed"]["security_passed_case_count"], 3)

    def test_backup_restore_evidence_has_matching_digests_and_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_evidence_suite(Path(temporary) / "evidence")
            backup = summary["controls"]["backup_restore"]

            self.assertEqual(backup["status"], "pass")
            self.assertTrue(backup["checks"]["backup_integrity_ok"])
            self.assertTrue(backup["checks"]["restore_target_replaced"])
            self.assertTrue(backup["checks"]["restore_digest_matches"])
            self.assertTrue(backup["checks"]["restore_snapshot_matches"])
            self.assertEqual(
                backup["observed"]["source_state_digest"],
                backup["observed"]["restored_state_digest"],
            )
            for path in backup["evidence_files"].values():
                self.assertTrue(Path(path).is_file(), path)

    def test_evidence_contains_no_secret_pattern_or_external_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_evidence_suite(Path(temporary) / "evidence")
            backup = summary["controls"]["backup_restore"]

            self.assertEqual(backup["observed"]["secret_scan"]["matches"], 0)
            self.assertEqual(backup["observed"]["effects_count"], 0)
            self.assertEqual(summary["observed"]["network_attempts"], [])


if __name__ == "__main__":
    unittest.main()
