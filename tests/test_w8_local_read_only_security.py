from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner.run_w8_local_read_only_security import (
    network_tripwire,
    run_security_suite,
)


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


class W8NetworkTripwireTests(unittest.TestCase):
    def test_tripwire_allows_local_unix_socket_but_blocks_inet(self) -> None:
        import os
        import socket
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            sock_path = os.path.join(temporary, "local.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(sock_path)
            server.listen(1)
            try:
                with network_tripwire() as attempts:
                    # A local Unix-domain socket is local IPC, not network egress:
                    # the tripwire must let it through and must NOT record it.
                    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    client.connect(sock_path)
                    client.close()
                    # A real network (AF_INET) connect must be recorded as a
                    # forbidden attempt and must never reach the wire.
                    inet = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    with self.assertRaises(AssertionError):
                        inet.connect(("127.0.0.1", 9))
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0]["operation"], "socket.connect")
            finally:
                server.close()
