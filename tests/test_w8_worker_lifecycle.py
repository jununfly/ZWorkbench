from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner import run_w8_worker_lifecycle as runner


class W8WorkerLifecycleRunnerTests(unittest.TestCase):
    def test_h4_runner_passes_all_lifecycle_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = runner.run_suite(Path(temporary) / "evidence")

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["passed_scenarios"], 6)
        self.assertTrue(summary["checks"]["orphan_processes_zero"])
        self.assertTrue(summary["checks"]["status_loss_zero"])
        self.assertTrue(summary["checks"]["unauthorized_effects_zero"])


if __name__ == "__main__":
    unittest.main()
