from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner import run_w8_evidence_replay as runner


class W8EvidenceReplayRunnerTests(unittest.TestCase):
    def test_h5_runner_passes_modes_and_negative_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = runner.run_suite(Path(temporary) / "evidence")

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["passed_cases"], 7)
        self.assertTrue(summary["checks"]["recorded_view_read_only"])
        self.assertTrue(summary["checks"]["simulated_replay_cassette_only"])
        self.assertTrue(summary["checks"]["live_replay_default_deny"])
        self.assertTrue(summary["checks"]["unknown_inputs_safe_stop"])
        self.assertTrue(summary["checks"]["external_execution_zero"])


if __name__ == "__main__":
    unittest.main()
