from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner.run_w8_local_read_only_security import run_security_suite


class W8LocalReadOnlySecurityTests(unittest.TestCase):
    def test_security_controls_pass_in_isolated_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_security_suite(Path(temporary) / "security-evidence")

            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["case_count"], 3)
            self.assertEqual(summary["passed_case_count"], 3)
            self.assertTrue(summary["checks"]["network_zero_across_controls"])
            self.assertEqual(
                [item["control"] for item in summary["cases"]],
                ["identity", "redaction", "default_deny"],
            )

    def test_identity_control_checks_provider_and_run_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_security_suite(Path(temporary) / "security-evidence")
            identity = summary["cases"][0]

            self.assertTrue(identity["checks"]["run_id_present"])
            self.assertTrue(identity["checks"]["thread_id_bound_to_run"])
            self.assertTrue(identity["checks"]["turn_id_bound_to_run"])
            self.assertTrue(identity["checks"]["provider_identity_bound_to_replay"])
            self.assertEqual(identity["observed"]["network_attempts"], [])

    def test_redaction_and_default_deny_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_security_suite(Path(temporary) / "security-evidence")
            redaction = summary["cases"][1]
            default_deny = summary["cases"][2]

            self.assertEqual(redaction["observed"]["preflight_status"], "deny")
            self.assertEqual(redaction["observed"]["adapter_factory_calls"], 0)
            self.assertEqual(redaction["observed"]["secret_occurrences_in_result"], 0)
            self.assertEqual(default_deny["observed"]["owner_run_status"], "safe_stopped")
            self.assertEqual(default_deny["observed"]["responses_sent"], 1)
            self.assertNotIn("semantic", default_deny["observed"]["result_kinds"])


if __name__ == "__main__":
    unittest.main()
