"""Read-only doctor self-check (roadmap 1-9-2).

The doctor probes, without writing anything:
  1. Codex executability (locate + `codex --version` with a timeout),
  2. case directory conventions (pure stat, derived paths reported),
  3. loopback provider reachability (loopback endpoints only; non-loopback
     endpoints are reported ``unknown`` and never contacted).

Read-only is a hard constraint, not a comment: a guard test asserts the
probed case root's directory tree is byte-for-byte unchanged after a run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

from zworkbench import cli
from zworkbench.doctor import DOCTOR_SCHEMA, DoctorCheck, DoctorReport, run_doctor


def _tree(root: Path) -> list[str]:
    entries: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(dirnames):
            entries.append(str(Path(dirpath, name).relative_to(root)) + "/")
        for name in sorted(filenames):
            entries.append(str(Path(dirpath, name).relative_to(root)))
    return sorted(entries)


def _fake_codex(directory: Path, output: str = "codex 0.1.0") -> Path:
    executable = directory / "codex"
    executable.write_text("#!/bin/sh\necho '%s'\n" % output, encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _recording_http_probe(calls: list[str], result=(True, "ok")):
    def probe(endpoint: str):
        calls.append(endpoint)
        return result

    return probe


class _QuietHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib interface
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:
        pass


def _serve_loopback() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:{0}".format(server.server_address[1])


class DoctorCodexProbeTests(unittest.TestCase):
    def test_missing_codex_fails_with_actionable_fix_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_doctor(
                case_root=root,
                codex=root / "no-such-codex",
            )
            check = report.check("codex_executable")
            self.assertEqual("fail", check.status)
            self.assertIsNotNone(check.fix_hint)
            self.assertIn("--codex", check.fix_hint)

    def test_executable_codex_passes_and_reports_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex = _fake_codex(root)
            report = run_doctor(case_root=root, codex=codex)
            check = report.check("codex_executable")
            self.assertEqual("pass", check.status)
            self.assertIn("codex 0.1.0", check.detail)

    def test_version_timeout_is_fail_not_hang(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
            executable.chmod(0o755)

            def slow_probe(path: Path):
                try:
                    completed = subprocess.run(
                        [str(path), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                    )
                    return completed.returncode == 0, completed.stdout.strip()
                except subprocess.TimeoutExpired:
                    return False, "codex --version timed out"

            report = run_doctor(case_root=root, codex=executable, codex_probe=slow_probe)
            check = report.check("codex_executable")
            self.assertEqual("fail", check.status)


class DoctorCaseLayoutTests(unittest.TestCase):
    def test_missing_case_root_fails_with_fix_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_doctor(
                case_root=Path(temporary) / "absent-root",
                codex=None,
            )
            check = report.check("case_layout")
            self.assertEqual("fail", check.status)
            self.assertIn("--case-root", check.fix_hint)

    def test_missing_workspace_inside_existing_case_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_doctor(case_root=root, workspace=root / "absent-ws", codex=None)
            check = report.check("case_layout")
            self.assertEqual("fail", check.status)
            self.assertIn("--workspace", check.fix_hint)

    def test_existing_layout_passes_and_reports_derived_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_doctor(case_root=root, codex=None)
            check = report.check("case_layout")
            self.assertEqual("pass", check.status)
            detail = check.detail
            self.assertIn(str(root / "state" / "composition.sqlite3"), detail)
            self.assertIn(str(root / "codex-home"), detail)
            self.assertIn(str(root / "events" / "codex.jsonl"), detail)


class DoctorLoopbackProbeTests(unittest.TestCase):
    def test_reachable_loopback_endpoint_passes(self) -> None:
        server, endpoint = _serve_loopback()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                report = run_doctor(case_root=Path(temporary), codex=None, endpoint=endpoint)
                check = report.check("loopback_provider")
                self.assertEqual("pass", check.status)
        finally:
            server.shutdown()
            server.server_close()

    def test_unreachable_loopback_endpoint_fails_with_fix_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            # Port 1 on loopback is reserved and refuses connections.
            report = run_doctor(
                case_root=Path(temporary),
                codex=None,
                endpoint="http://127.0.0.1:1",
                loopback_timeout=0.5,
            )
            check = report.check("loopback_provider")
            self.assertEqual("fail", check.status)
            self.assertIn("--endpoint", check.fix_hint)

    def test_non_loopback_endpoint_is_unknown_and_never_contacted(self) -> None:
        calls: list[str] = []
        probe = _recording_http_probe(calls)
        with tempfile.TemporaryDirectory() as temporary:
            report = run_doctor(
                case_root=Path(temporary),
                codex=None,
                endpoint="http://10.0.0.1:9999",
                http_probe=probe,
            )
        check = report.check("loopback_provider")
        self.assertEqual("unknown", check.status)
        self.assertEqual([], calls)
        self.assertIsNotNone(check.fix_hint)


class DoctorAggregationTests(unittest.TestCase):
    def test_all_pass_is_ready_with_zero_exit_payload(self) -> None:
        server, endpoint = _serve_loopback()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                report = run_doctor(
                    case_root=root, codex=_fake_codex(root), endpoint=endpoint
                )
                self.assertEqual("ready", report.status)
                self.assertTrue(report.ready)
        finally:
            server.shutdown()
            server.server_close()

    def test_any_fail_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_doctor(case_root=root, codex=root / "absent")
            self.assertEqual("not_ready", report.status)
            self.assertFalse(report.ready)

    def test_report_to_dict_is_json_safe_with_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_doctor(case_root=Path(temporary), codex=None)
            payload = report.to_dict()
            self.assertEqual(DOCTOR_SCHEMA, payload["schema"])
            json.dumps(payload)
            self.assertEqual(
                {"codex_executable", "case_layout", "loopback_provider"},
                {item["name"] for item in payload["checks"]},
            )
            for item in payload["checks"]:
                self.assertIn(item["status"], {"pass", "fail", "unknown"})


class DoctorReadOnlyGuardTests(unittest.TestCase):
    def test_doctor_never_writes_to_the_case_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            before = _tree(root)
            run_doctor(case_root=root, workspace=workspace, codex=None)
            self.assertEqual(before, _tree(root))
            self.assertFalse((root / "state").exists())
            self.assertFalse((root / "codex-home").exists())
            self.assertFalse((root / "events").exists())


class DoctorCliTests(unittest.TestCase):
    def test_cli_doctor_prints_json_and_exits_one_when_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            buffer = __import__("io").StringIO()
            original = sys.stdout
            sys.stdout = buffer
            try:
                # Port 1 refuses connections, so not_ready holds on any machine
                # (a dev box may genuinely have codex and a live 11434 endpoint).
                exit_code = cli.main(
                    ["doctor", "--case-root", str(root), "--endpoint", "http://127.0.0.1:1"]
                )
            finally:
                sys.stdout = original
            self.assertEqual(1, exit_code)
            payload = json.loads(buffer.getvalue())
            self.assertEqual("zworkbench-doctor/v1", payload["schema"])
            self.assertEqual("not_ready", payload["status"])

    def test_cli_doctor_exits_zero_when_ready(self) -> None:
        server, endpoint = _serve_loopback()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                codex = _fake_codex(root)
                buffer = __import__("io").StringIO()
                original = sys.stdout
                sys.stdout = buffer
                try:
                    exit_code = cli.main(
                        [
                            "doctor",
                            "--case-root",
                            str(root),
                            "--codex",
                            str(codex),
                            "--endpoint",
                            endpoint,
                        ]
                    )
                finally:
                    sys.stdout = original
                self.assertEqual(0, exit_code)
                payload = json.loads(buffer.getvalue())
                self.assertEqual("ready", payload["status"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
