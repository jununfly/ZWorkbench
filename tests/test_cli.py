from __future__ import annotations

import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout

from zworkbench.cli import CLI_SCHEMA, main
from zworkbench.composition import CompositionOwner


FAKE_CODEX = """
import json
import sys

THREAD_ID = "cli-fixture-thread"
TURN_ID = "cli-fixture-turn"


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    request_id = message["id"]
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "thread/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    elif method == "turn/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        send({"jsonrpc": "2.0", "method": "item/agentMessage/delta", "params": {"turnId": TURN_ID, "delta": "fixture-ok"}})
        send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
    elif method == "thread/read":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown method"}})
"""


class ZWorkbenchCliTests(unittest.TestCase):
    def _fake_codex(self, root: Path, source: str = FAKE_CODEX) -> Path:
        executable = root / "fake-codex"
        executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(source)), encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def _run(self, arguments: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(arguments)
        return status, json.loads(output.getvalue())

    def test_run_completes_real_adapter_protocol_and_writes_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)
            export_path = root / "export" / "owner.json"
            backup_path = root / "backup"
            summary_path = root / "summary.json"

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "inspect the fixture and return fixture-ok",
                    "--codex",
                    str(codex),
                    "--run-id",
                    "cli-run-1",
                    "--export",
                    str(export_path),
                    "--backup",
                    str(backup_path),
                    "--summary",
                    str(summary_path),
                ]
            )

            self.assertEqual(status, 0)
            self.assertEqual(payload["schema"], CLI_SCHEMA)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["run_id"], "cli-run-1")
            self.assertEqual(payload["execution"]["text"], "fixture-ok")
            self.assertEqual(payload["owner"]["run_status"], "completed")
            self.assertTrue(payload["owner"]["database_present"])
            self.assertTrue(payload["owner"]["recorded_view_present"])
            self.assertGreaterEqual(payload["owner"]["event_count"], 4)
            self.assertTrue(export_path.is_file())
            self.assertTrue((backup_path / "manifest.json").is_file())
            self.assertTrue((backup_path / "composition.sqlite3").is_file())
            self.assertEqual(json.loads(summary_path.read_text(encoding="utf-8")), payload)

            with CompositionOwner(root / "state" / "composition.sqlite3") as owner:
                run = owner.get_run("cli-run-1")
                self.assertEqual(run["status"], "completed")
                self.assertEqual(owner.state_digest(), payload["owner"]["state_digest"])
                self.assertEqual(len(run["effects"]), 0)

    def test_remote_provider_is_denied_before_owner_or_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "must not execute",
                    "--codex",
                    str(codex),
                    "--endpoint",
                    "https://ark.cn-beijing.volces.com/api/coding/v3",
                ]
            )

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertEqual(payload["preflight"]["status"], "deny")
            self.assertIn("provider_not_loopback", {item["code"] for item in payload["preflight"]["violations"]})
            self.assertFalse((root / "state" / "composition.sqlite3").exists())

    def test_case_local_output_boundary_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "must not write outside the case",
                    "--codex",
                    str(codex),
                    "--summary",
                    str(Path(external) / "summary.json"),
                ]
            )

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertEqual(payload["violations"][0]["code"], "cli_path_outside_case_root")
            self.assertFalse((root / "state" / "composition.sqlite3").exists())

    def test_credential_like_prompt_is_rejected_without_creating_owner_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "please use api_key=sk-12345678901234567890",
                    "--codex",
                    str(codex),
                ]
            )

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertEqual(payload["violations"][0]["code"], "prompt_contains_credential_pattern")
            self.assertNotIn("sk-12345678901234567890", json.dumps(payload))
            self.assertFalse((root / "state" / "composition.sqlite3").exists())

    def test_artifact_path_cannot_overwrite_owner_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)
            database = root / "state" / "composition.sqlite3"

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "must not overwrite owner state",
                    "--codex",
                    str(codex),
                    "--export",
                    str(database),
                ]
            )

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertEqual(payload["violations"][0]["code"], "cli_path_conflict")
            self.assertFalse(database.exists())

    def test_unknown_app_server_request_is_denied_and_owner_is_safe_stopped(self) -> None:
        source = FAKE_CODEX.replace(
            'send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})',
            'send({"jsonrpc": "2.0", "id": 99, "method": "future/server-request.v1", "params": {}})\n'
            '        send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})',
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root, source)

            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(root),
                    "--workspace",
                    str(workspace),
                    "--prompt",
                    "trigger an unknown server request",
                    "--codex",
                    str(codex),
                    "--run-id",
                    "cli-unknown-1",
                ]
            )

            self.assertEqual(status, 1)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["owner"]["run_status"], "safe_stopped")
            self.assertGreaterEqual(payload["owner"]["event_count"], 4)


if __name__ == "__main__":
    unittest.main()
