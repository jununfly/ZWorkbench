from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from zworkbench.codex_adapter import CodexAppServerAdapter
from zworkbench.composition import CompositionOwner


class CodexAdapterShapeTests(unittest.TestCase):
    def test_command_and_environment_are_explicit_and_shell_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    root / "workspace",
                    provider_identity={"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"},
                    event_log=root / "events.jsonl",
                )
                self.assertEqual(adapter.command()[:4], [str(executable.resolve()), "app-server", "--listen", "stdio://"])
                self.assertIn("--disable", adapter.command())
                environment = adapter._build_environment()
                self.assertEqual(environment["CODEX_HOME"], str((root / "codex-home").resolve()))
                self.assertEqual(environment["CODEX_CI"], "1")
                self.assertNotIn("OPENAI_API_KEY", environment)

    def test_owner_metadata_is_not_written_until_an_owner_backed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(owner, executable, root / "codex-home", root / "workspace")
                self.assertEqual(owner.snapshot()["runs"], [])
                self.assertTrue(adapter.environment_digest())

    def test_binary_jsonl_transport_consumes_completion_buffered_with_turn_response(self) -> None:
        fake_codex = """
        import json
        import sys

        THREAD_ID = "adapter-buffered-thread"
        TURN_ID = "adapter-buffered-turn"

        def send(message):
            sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
            sys.stdout.flush()

        for line in sys.stdin:
            message = json.loads(line)
            if "id" not in message:
                continue
            request_id = message["id"]
            method = message.get("method")
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "thread/start":
                send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
            elif method == "turn/start":
                # Force notifications and the matching RPC response into the
                # same pipe batch, with completion arriving first.
                send({"jsonrpc": "2.0", "method": "item/completed", "params": {"threadId": THREAD_ID, "turnId": TURN_ID, "item": {"type": "agentMessage", "text": "fixture-ok"}}})
                send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
                send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake-codex"
            executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(fake_codex)), encoding="utf-8")
            executable.chmod(0o755)
            workspace = root / "workspace"
            workspace.mkdir()
            with CompositionOwner(root / "owner.sqlite3") as owner:
                with CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    workspace,
                    provider_identity={"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"},
                    event_log=root / "events.jsonl",
                ) as adapter:
                    execution = adapter.execute("run-buffered", "return fixture-ok", timeout=2.0)
                self.assertEqual(execution.status, "completed")
                self.assertEqual(execution.text, "fixture-ok")
                self.assertEqual(owner.get_run("run-buffered")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
