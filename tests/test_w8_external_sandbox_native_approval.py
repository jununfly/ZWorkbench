from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_external_sandbox_native_approval" / "v1"
sys.path.insert(0, str(REPO_ROOT / "evaluation" / "runner"))

from run_w8_external_sandbox_native_approval import (  # noqa: E402
    PROVIDER_NAME,
    command_for,
    command_output,
    parse_json_output,
    sandbox_profile,
    setup_case,
)


class W8ExternalSandboxNativeApprovalTests(unittest.TestCase):
    def test_fixture_contains_pinned_probe_scripts(self) -> None:
        for name in ("README.md", "codex_exec_wrapper.py", "direct_write.py"):
            self.assertTrue((FIXTURE / name).is_file(), name)

    def test_command_binds_case_handshake_and_absolute_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = setup_case(Path(temporary) / "case", "host_profile_denied", 1)
            command = json.loads(command_for(case, case["outside"]))["cmd"]
            self.assertIn(str(FIXTURE / "direct_write.py"), command)
            self.assertIn(str(case["probe_ready_file"]), command)
            self.assertIn(str(case["probe_release_file"]), command)
            self.assertIn(str(case["probe_pid_file"]), command)

    def test_profile_denies_only_case_targets_and_allows_provider_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = sandbox_profile(root / "outside.txt", root / "secret", 43123)
            self.assertIn('(deny file-write* (subpath "' + str(root / "outside.txt") + '"))', profile)
            self.assertIn('(deny file-read-data (subpath "' + str(root / "secret") + '"))', profile)
            self.assertIn('(allow network-outbound (remote tcp "localhost:43123"))', profile)

    def test_output_accepts_real_command_output_delta_and_aggregated_output(self) -> None:
        delta = {"method": "item/commandExecution/outputDelta", "params": {"delta": '{"status":"host_denied"}\n'}}
        self.assertEqual(parse_json_output(command_output([delta]))["status"], "host_denied")
        completed = {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "commandExecution",
                    "aggregatedOutput": '{"status":"written"}\n',
                }
            },
        }
        self.assertEqual(parse_json_output(command_output([completed]))["status"], "written")

    def test_loopback_provider_identity_is_explicit(self) -> None:
        self.assertEqual(PROVIDER_NAME, "w8-loopback")


if __name__ == "__main__":
    unittest.main()
