from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_host_boundary_min_permissions" / "v1"
sys.path.insert(0, str(REPO_ROOT / "evaluation" / "runner"))

from run_w8_host_boundary_min_permissions import (  # noqa: E402
    PROBE_SCHEMA,
    observe_process_tree,
    output_metadata,
    parse_json_output,
    profile_for,
)


class W8HostBoundaryMinimumPermissionTests(unittest.TestCase):
    def test_fixture_contains_only_case_local_probe_scripts(self) -> None:
        self.assertTrue((FIXTURE / "README.md").is_file())
        self.assertTrue((FIXTURE / "probe.py").is_file())
        self.assertTrue((FIXTURE / "process_tree_probe.py").is_file())

    def test_profile_has_narrow_denial_for_each_surface(self) -> None:
        secret = Path("/private/tmp/w8-fake-secret")
        child = Path("/bin/echo")
        self.assertIn("deny file-read-data", profile_for("secret_read", secret, child))
        self.assertIn("deny network-outbound", profile_for("network_connect", secret, child))
        self.assertIn("deny network-outbound", profile_for("dns_lookup", secret, child))
        self.assertIn("deny process-exec", profile_for("child_exec", secret, child))

    def test_secret_is_never_promoted_from_raw_output(self) -> None:
        secret = "W8_FAKE_SECRET_MUST_NOT_LEAK"
        safe = output_metadata('{"status":"host_denied"}\n', "", secret)
        leaked = output_metadata(secret, "", secret)
        self.assertEqual(safe["raw_secret_matches"], 0)
        self.assertTrue(safe["raw_output_redacted"])
        self.assertEqual(leaked["raw_secret_matches"], 1)
        self.assertFalse(leaked["raw_output_redacted"])

    def test_probe_parser_requires_probe_schema(self) -> None:
        parsed = parse_json_output('{"schema":"other","status":"host_denied"}\n')
        self.assertEqual(parsed, {})
        parsed = parse_json_output('{"schema":"%s","status":"host_denied"}\n' % PROBE_SCHEMA)
        self.assertEqual(parsed["status"], "host_denied")

    def test_process_tree_observation_requires_live_codex_pid_in_chain(self) -> None:
        records = {
            101: (101, 202, "probe.py"),
            202: (202, 303, "sh"),
            303: (303, 404, "codex"),
            404: (404, 0, "runner"),
        }
        with patch("run_w8_host_boundary_min_permissions.ps_record", side_effect=records.get):
            observed = observe_process_tree(101, 303)
        self.assertEqual(observed["status"], "observed")
        self.assertTrue(observed["codex_pid_observed"])

    def test_process_tree_observation_does_not_infer_from_missing_ps(self) -> None:
        with patch("run_w8_host_boundary_min_permissions.ps_record", return_value=None):
            unobserved = observe_process_tree(101, 303)
        self.assertEqual(unobserved["status"], "unobserved")
        self.assertFalse(unobserved["codex_pid_observed"])


if __name__ == "__main__":
    unittest.main()
