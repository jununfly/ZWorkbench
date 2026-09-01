from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_host_broker" / "v1"
sys.path.insert(0, str(REPO_ROOT / "evaluation" / "runner"))

from run_w8_host_broker_boundary import process_tree_observation  # noqa: E402


class W8HostBrokerFixtureTests(unittest.TestCase):
    def test_policy_and_fixture_scripts_are_present(self) -> None:
        for name in ("host_broker.py", "direct_write.py", "codex_exec_wrapper.py", "README.md"):
            self.assertTrue((FIXTURE / name).is_file(), name)

    def test_broker_client_denies_outside_target_without_writing(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("original\n", encoding="utf-8")
            policy = root / "policy.json"
            policy.write_text(json.dumps({"schema": "test", "workspace": str(workspace)}), encoding="utf-8")
            socket_path = root / "broker.sock"
            audit = root / "audit.jsonl"
            server = subprocess.Popen([
                "python3", str(FIXTURE / "host_broker.py"), "server",
                "--socket", str(socket_path), "--workspace", str(workspace),
                "--policy", str(policy), "--audit", str(audit),
            ])
            try:
                for _ in range(100):
                    if socket_path.exists():
                        break
                    import time
                    time.sleep(0.01)
                result = subprocess.run([
                    "python3", str(FIXTURE / "host_broker.py"), "client",
                    "--socket", str(socket_path), "--target", str(outside),
                    "--content", "must-not-write", "--request-id", "test-deny",
                ], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 23)
                self.assertEqual(outside.read_text(encoding="utf-8"), "original\n")
                records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(records[0]["decision"], "deny")
                self.assertEqual(records[0]["reason"], "target_outside_workspace")
            finally:
                server.terminate()
                server.wait(timeout=3)

    def test_pid_linkage_does_not_promote_process_tree_inheritance(self) -> None:
        observation = process_tree_observation(
            [
                {
                    "expected_codex_pid": 101,
                    "codex_parent_observed": False,
                    "client_ancestry": [
                        {"pid": 202, "ppid": 303, "observed": False, "error_type": "PermissionError"}
                    ],
                }
            ],
            101,
        )
        self.assertEqual(observation["status"], "unobserved")
        self.assertTrue(observation["expected_codex_pid_recorded"])
        self.assertFalse(observation["client_ancestry_observed"])
        self.assertFalse(observation["codex_parent_observed"])


if __name__ == "__main__":
    unittest.main()
