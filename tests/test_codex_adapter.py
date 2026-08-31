from __future__ import annotations

from pathlib import Path
import tempfile
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


if __name__ == "__main__":
    unittest.main()
