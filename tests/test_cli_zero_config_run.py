from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from zworkbench.cli import CLI_SCHEMA, main
from zworkbench.composition import CompositionOwner


def _fake_codex_source(marker: str) -> str:
    return '''
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
        send({"jsonrpc": "2.0", "method": "item/agentMessage/delta", "params": {"turnId": TURN_ID, "delta": "%s"}})
        send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
    elif method == "thread/read":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown method"}})
''' % marker


class ZeroConfigRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_cwd = os.getcwd()
        self._original_path = os.environ.get("PATH", "")
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._original_cwd)
        os.environ["PATH"] = self._original_path
        self._dir.cleanup()

    def _fake_codex(self, root: Path, marker: str = "fixture-ok") -> Path:
        executable = root / "fake-codex"
        executable.write_text(
            "#!{0}\n{1}".format(sys.executable, textwrap.dedent(_fake_codex_source(marker))),
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def _path_codex(self, directory: Path, marker: str) -> Path:
        """A fake `codex` placed ON PATH so shutil.which can discover it."""
        executable = directory / "codex"
        executable.write_text(
            "#!{0}\n{1}".format(sys.executable, textwrap.dedent(_fake_codex_source(marker))),
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def _run(self, arguments: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(arguments)
        return status, json.loads(output.getvalue())

    def test_run_with_only_prompt_and_codex_auto_derives_case_root_and_workspace(self) -> None:
        # Zero-config: neither --case-root nor --workspace is supplied. Both must
        # default to the current working directory, and the owner DB must land
        # under <cwd>/state to prove case-root was derived (not a crash / not a
        # stray absolute path).
        codex = self._fake_codex(self.root)
        status, payload = self._run(
            [
                "run",
                "--prompt",
                "inspect the fixture and return the marker",
                "--codex",
                str(codex),
                "--run-id",
                "zero-config-1",
            ]
        )
        self.assertEqual(status, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["execution"]["text"], "fixture-ok")
        self.assertTrue(payload["owner"]["database_present"])
        self.assertTrue(payload["owner"]["recorded_view_present"])
        # The derived case-root is the chdir'd temp dir; state lives inside it.
        self.assertTrue((self.root / "state" / "composition.sqlite3").is_file())

    def test_run_without_codex_argument_detects_codex_from_path(self) -> None:
        # --codex omitted: the runner must discover `codex` from PATH rather than
        # rejecting. A PATH-resident fake emitting a distinct marker proves the
        # auto-detection path was used (an explicitly-passed fake would emit
        # "fixture-ok" instead).
        path_dir = self.root / "bin"
        path_dir.mkdir()
        self._path_codex(path_dir, marker="path-codex-ok")
        os.environ["PATH"] = "{0}{1}{2}".format(str(path_dir), os.pathsep, self._original_path)

        status, payload = self._run(
            [
                "run",
                "--case-root",
                str(self.root),
                "--workspace",
                str(self.root),
                "--prompt",
                "inspect the fixture and return the marker",
                "--run-id",
                "zero-config-2",
            ]
        )
        self.assertEqual(status, 0)
        self.assertEqual(payload["execution"]["text"], "path-codex-ok")

    def test_run_without_codex_and_no_path_codex_fails_closed_with_clear_violation(self) -> None:
        # --codex omitted AND no `codex` on PATH: must fail-closed with a clear
        # preflight violation (codex_executable_missing), never a traceback or a
        # silent default to an unusable binary.
        os.environ["PATH"] = ""
        status, payload = self._run(
            [
                "run",
                "--case-root",
                str(self.root),
                "--workspace",
                str(self.root),
                "--prompt",
                "summarize the README",
                "--run-id",
                "zero-config-3",
            ]
        )
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "denied")
        preflight = payload.get("preflight", {})
        codes = [violation.get("code") for violation in preflight.get("violations", [])]
        self.assertIn("codex_executable_missing", codes)

    def test_run_appends_next_steps_on_completed(self) -> None:
        # 1-9-3 价值演示缝合：成功 run 末 stdout 必须附 next_steps 价值闭环数组，
        # 五项键齐全、read_only 为 bool、只读步骤引用真实 db/case_root、唯一的
        # 非只读步骤（write propose）用 <本地 git 仓库> 占位并在 precondition 注明 worktree-root。
        codex = self._fake_codex(self.root)
        status, payload = self._run(
            [
                "run",
                "--prompt",
                "inspect the fixture and return the marker",
                "--codex",
                str(codex),
                "--run-id",
                "next-steps-1",
            ]
        )
        self.assertEqual(status, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertIn("next_steps", payload)
        steps = payload["next_steps"]
        self.assertEqual(len(steps), 5)
        required_keys = {"command", "purpose_zh", "read_only", "precondition"}
        for step in steps:
            self.assertEqual(required_keys, set(step.keys()))
            self.assertIsInstance(step["read_only"], bool)
        db = str(self.root / "state" / "composition.sqlite3")
        commands = [step["command"] for step in steps]
        self.assertTrue(any(db in cmd for cmd in commands))
        propose = next(step for step in steps if step["command"].startswith("zworkbench write propose"))
        self.assertFalse(propose["read_only"])
        self.assertIn("<本地 git 仓库>", propose["command"])
        self.assertIn("worktree-root", propose["precondition"])

    def test_run_denied_has_no_next_steps(self) -> None:
        # denied（preflight/CLI 拒绝，未建 run）不附带 next_steps；失败提示由
        # 1-9-4 的 fail-closed UX 成本回收负责，此处只验证不混入价值闭环数组。
        os.environ["PATH"] = ""
        status, payload = self._run(
            [
                "run",
                "--case-root",
                str(self.root),
                "--workspace",
                str(self.root),
                "--prompt",
                "summarize the README",
                "--run-id",
                "next-steps-denied",
            ]
        )
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "denied")
        self.assertNotIn("next_steps", payload)

    def test_open_launches_read_only_ui_host_on_completed(self) -> None:
        # 1-9-3 --open：completed 后在打印 run payload 之后自动复用只读 ui-host
        # （loopback 强制、无 --db、无 run）。monkeypatch 避免阻塞，校验入参。
        from unittest import mock

        from zworkbench.cli import LOOPBACK

        codex = self._fake_codex(self.root)
        captured: dict = {}
        sentinel = object()

        def _fake_host(args: "argparse.Namespace") -> int:
            captured["args"] = args
            return 0

        with mock.patch("zworkbench.cli._ui_host_command", _fake_host):
            status, payload = self._run(
                [
                    "run",
                    "--prompt",
                    "inspect the fixture and return the marker",
                    "--codex",
                    str(codex),
                    "--run-id",
                    "open-1",
                    "--open",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertIn("args", captured)
        self.assertEqual(captured["args"].host, LOOPBACK)
        self.assertEqual(captured["args"].review, False)
        self.assertEqual(captured["args"].port, 0)

    def test_open_does_not_launch_when_denied(self) -> None:
        # denied 路径即便带 --open 也不拉起 ui-host（无 UI 可看，且避免阻塞）。
        from unittest import mock

        os.environ["PATH"] = ""
        called = {"count": 0}

        def _fake_host(args: "argparse.Namespace") -> int:
            called["count"] += 1
            return 0

        with mock.patch("zworkbench.cli._ui_host_command", _fake_host):
            status, payload = self._run(
                [
                    "run",
                    "--case-root",
                    str(self.root),
                    "--workspace",
                    str(self.root),
                    "--prompt",
                    "summarize the README",
                    "--run-id",
                    "open-denied",
                    "--open",
                ]
            )
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "denied")
        self.assertEqual(called["count"], 0)

    def test_classify_run_error_maps_exception_families(self) -> None:
        # 1-9-4 timeout/failed 区分：纯函数把异常归到 operator-facing 桶。
        import socket

        from zworkbench.cli import _classify_run_error
        from zworkbench.codex_adapter import (
            CodexAdapterError,
            CodexProtocolError,
            CodexTurnWaitTimeout,
        )

        self.assertEqual(_classify_run_error(CodexTurnWaitTimeout("x"))[0], "timeout")
        self.assertEqual(_classify_run_error(TimeoutError("x"))[0], "timeout")
        self.assertEqual(_classify_run_error(socket.timeout("x"))[0], "timeout")
        self.assertEqual(_classify_run_error(ConnectionError("x"))[0], "timeout")
        self.assertEqual(_classify_run_error(CodexProtocolError("x"))[0], "protocol")
        self.assertEqual(_classify_run_error(CodexAdapterError("x"))[0], "adapter")
        self.assertEqual(_classify_run_error(RuntimeError("x"))[0], "execution")
        for exc in (
            CodexTurnWaitTimeout("x"),
            TimeoutError("x"),
            CodexProtocolError("x"),
            CodexAdapterError("x"),
            RuntimeError("x"),
        ):
            _, hint = _classify_run_error(exc)
            self.assertTrue(hint.strip())

    def test_failed_run_reports_timeout_category_and_retry_hint(self) -> None:
        # 1-9-4 失败分类接入真实 payload：timeout 异常 -> error.category=timeout
        # + 顶层 retry_hint 指回 --timeout / doctor。status 仍是 failed（fail-closed 不变）。
        from unittest import mock

        from zworkbench.codex_adapter import CodexTurnWaitTimeout

        codex = self._fake_codex(self.root)

        def _boom(*args, **kwargs):
            raise CodexTurnWaitTimeout("turn wait expired")

        with mock.patch("zworkbench.cli.LocalReadOnlyRunOrchestrator.run", _boom):
            status, payload = self._run(
                [
                    "run",
                    "--prompt",
                    "p",
                    "--codex",
                    str(codex),
                    "--run-id",
                    "ux-timeout-1",
                    "--timeout",
                    "1",
                ]
            )
        self.assertEqual(status, 1)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["category"], "timeout")
        self.assertEqual(payload["error"]["type"], "CodexTurnWaitTimeout")
        self.assertIn("retry_hint", payload)
        self.assertIn("--timeout", payload["retry_hint"])

    def test_failed_run_reports_protocol_category_and_retry_hint(self) -> None:
        # protocol 异常 -> error.category=protocol + retry_hint 指向 doctor。
        from unittest import mock

        from zworkbench.codex_adapter import CodexProtocolError

        codex = self._fake_codex(self.root)

        def _boom(*args, **kwargs):
            raise CodexProtocolError("turn/start failed: missing turn.id")

        with mock.patch("zworkbench.cli.LocalReadOnlyRunOrchestrator.run", _boom):
            status, payload = self._run(
                [
                    "run",
                    "--prompt",
                    "p",
                    "--codex",
                    str(codex),
                    "--run-id",
                    "ux-protocol-1",
                    "--timeout",
                    "1",
                ]
            )
        self.assertEqual(status, 1)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["category"], "protocol")
        self.assertIn("doctor", payload["retry_hint"])

    def test_denied_violation_carries_actionable_hint(self) -> None:
        # 1-9-4 denied payload 的每个 violation 带非空 hint（fail-closed 可操作化）。
        os.environ["PATH"] = ""
        status, payload = self._run(
            [
                "run",
                "--case-root",
                str(self.root),
                "--workspace",
                str(self.root),
                "--prompt",
                "p",
                "--run-id",
                "ux-denied-hint",
            ]
        )
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "denied")
        violations = payload["preflight"]["violations"]
        self.assertTrue(violations)
        target = next(v for v in violations if v["code"] == "codex_executable_missing")
        self.assertIn("--codex", target["hint"])


if __name__ == "__main__":
    unittest.main()
