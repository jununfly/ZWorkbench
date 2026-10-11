from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner import run_w8_worker_lifecycle as runner


class W8OrphanEvidenceClassificationTests(unittest.TestCase):
    """Orphan accounting must distinguish proven-zero from un-enumerable.

    ``orphan_processes`` is ``UNKNOWN`` whenever the bridge cannot enumerate
    processes (for example when ``ps`` is unavailable).  That is not evidence
    of orphans and not evidence of zero, so it must be classified separately
    and never folded into either claim.
    """

    def test_classification(self) -> None:
        self.assertEqual(runner.classify_orphan_evidence(0), "zero")
        self.assertEqual(runner.classify_orphan_evidence(3), "nonzero")
        self.assertEqual(runner.classify_orphan_evidence("unknown"), "unknown")
        self.assertEqual(runner.classify_orphan_evidence(None), "unknown")

    def test_scenario_status_is_fail_closed(self) -> None:
        clean = {"thread_stopped": True, "orphan_processes_zero": True}
        # A proven orphan leak is a failure, not an unknown.
        self.assertEqual(
            runner.scenario_status({**clean, "orphan_processes_zero": False}, "nonzero"),
            "fail",
        )
        # A failed hard check fails even when orphan evidence looks clean.
        self.assertEqual(
            runner.scenario_status({**clean, "thread_stopped": False}, "zero"),
            "fail",
        )
        # Un-enumerable orphans are declared unknown and never pass.
        self.assertEqual(
            runner.scenario_status({**clean, "orphan_processes_zero": False}, "unknown"),
            "unknown",
        )
        self.assertEqual(runner.scenario_status(clean, "zero"), "pass")


class W8WorkerLifecycleRunnerTests(unittest.TestCase):
    def test_h4_runner_passes_all_lifecycle_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = runner.run_suite(Path(temporary) / "evidence")

        failed = [case["scenario"] for case in summary["scenarios"] if case["status"] == "fail"]
        self.assertEqual(failed, [])
        self.assertEqual(summary["scenario_count"], 6)
        # Every scenario is either proven pass or explicitly declared unknown;
        # an unknown may never be counted as a pass.
        self.assertEqual(
            summary["passed_scenarios"] + len(summary["unknown_scenarios"]),
            summary["scenario_count"],
        )
        for case in summary["scenarios"]:
            with self.subTest(scenario=case["scenario"]):
                self.assertIn(case["orphan_evidence"], ("zero", "unknown"))
                if case["orphan_evidence"] == "unknown":
                    self.assertEqual(case["status"], "unknown")
                    self.assertFalse(case["checks"]["orphan_processes_zero"])
                    self.assertIn(case["scenario"], summary["unknown_scenarios"])
                else:
                    self.assertEqual(case["status"], "pass")
                    self.assertTrue(case["checks"]["orphan_processes_zero"])
        # The human-readable status must not claim verification when the suite
        # did not verify every scenario.
        if summary["status"] == "pass":
            self.assertIn("verified", summary["formal_h4_status"])
        else:
            self.assertNotIn("verified", summary["formal_h4_status"])

    def test_h4_runner_keeps_lifecycle_status_and_effects_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = runner.run_suite(Path(temporary) / "evidence")

        self.assertTrue(summary["checks"]["status_loss_zero"])
        self.assertTrue(summary["checks"]["unauthorized_effects_zero"])


if __name__ == "__main__":
    unittest.main()
