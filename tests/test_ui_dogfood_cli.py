"""End-to-end smoke test for the ``zworkbench ui`` dogfood command.

Drives the real CLI subprocess (not the in-process harness) so a regression in
``_ui_command`` wiring — the subparser, the owner open, or the four write-seam
facades passed to ``serve_workbench`` — is caught here rather than only in manual
dogfooding.
"""

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = str(REPO_ROOT / "src")


def _no_proxy_opener():
    """urllib opener that never routes loopback through the sandbox proxy."""

    handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(handler)


def _read_until_serving(proc: "subprocess.Popen[bytes]", timeout: float = 10.0) -> str:
    """Return the base_url from the first ``{"event": "serving"}`` announce line."""

    deadline = time.time() + timeout
    buffer = ""
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == "serving":
            return payload["base_url"]
        buffer = line
    raise AssertionError("ui command never announced serving; last line: %r" % buffer)


class DogfoodCliSmokeTests(unittest.TestCase):
    def _start(self):
        db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        db.close()
        os.unlink(db.name)
        env = dict(os.environ)
        env.update(PYTHONPATH=SRC, PATH=env.get("PATH", ""))
        # The sandbox proxy must not intercept loopback requests.
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env.pop(key, None)
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "zworkbench.cli",
                "ui",
                "--db",
                db.name,
                "--port",
                "0",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc, db.name

    def test_ui_command_serves_writable_host(self):
        proc, db_name = self._start()
        opener = _no_proxy_opener()
        try:
            base_url = _read_until_serving(proc)
            self.assertTrue(base_url.startswith("http://127.0.0.1"), base_url)

            with opener.open(urllib.request.Request(base_url + "/home")) as resp:
                self.assertEqual(resp.status, 200)
                home_html = resp.read().decode("utf-8", "replace")

            # The composer trigger must be live (wired facade), not a disabled
            # placeholder — that is the whole point of the dogfood command.
            self.assertIn("data-composer-send", home_html)

            # A real composer send must create a run in the owner DB.
            req = urllib.request.Request(
                base_url + "/api/runs",
                data=json.dumps(
                    {"task_type": "composer_message", "input_value": {"task": "dogfood smoke"}}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(req) as resp:
                self.assertEqual(resp.status, 201)
                created = json.loads(resp.read().decode("utf-8"))
            self.assertIn("run_id", created)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            if os.path.exists(db_name):
                os.unlink(db_name)
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()

    def test_ui_command_refuses_non_loopback(self):
        # The command must refuse to expose owner state on the network.
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "zworkbench.cli",
                "ui",
                "--db",
                tempfile.mktemp(suffix=".sqlite3"),
                "--host",
                "0.0.0.0",
                "--port",
                "0",
            ],
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": SRC},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate(timeout=15)
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(
            b"loopback" in out or b"loopback" in err,
            "expected a loopback-only refusal, got stdout=%r stderr=%r" % (out, err),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
