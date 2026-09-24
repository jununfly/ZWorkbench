"""Behaviour tests for the F6 input-composer write seam (1-2-1).

The composer reuses the F10 narrow facade (POST /api/runs) under
``task_type=composer_message``. These tests prove, over real HTTP against a
real CompositionOwner on a temp database, that: a wired host renders a live
composer form and serves its script; a read-only host degrades the composer to
a disabled shell; and a send creates + starts a run carrying the typed prompt.
"""

import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.composition import CompositionOwner
from zworkbench.ui_host import (
    COMPOSER_SCRIPT_ROUTE,
    RUN_API_ROUTE,
    serve_workbench,
)
from zworkbench.ui_run import (
    COMPOSER_TASK_TYPE,
    composer_script,
    owner_command_source,
)
from zworkbench.ui_view_model import owner_view_source


#: A loopback host must be reached directly; a machine-wide proxy would answer.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(base, path):
    request = urllib.request.Request(base + path)
    try:
        with DIRECT.open(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, ""


def _post(base, path, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with DIRECT.open(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, ""


class ComposerApiTests(unittest.TestCase):
    """The composer payload through the same narrow facade F10 uses."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")

    def tearDown(self):
        self.owner.close()
        self.directory.cleanup()

    def test_composer_post_creates_and_starts_a_run(self):
        cmd = owner_command_source(self.owner)
        result = cmd(
            task_type=COMPOSER_TASK_TYPE,
            input_value={"prompt": "列出最近三次运行", "origin": "composer"},
            metadata={"source": "workbench-ui", "triggered_by": "composer"},
        )
        self.assertTrue(str(result["run_id"]).startswith("run-"))
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["task_type"], COMPOSER_TASK_TYPE)

    def test_composer_run_carries_the_typed_prompt(self):
        cmd = owner_command_source(self.owner)
        created = cmd(
            task_type=COMPOSER_TASK_TYPE,
            input_value={"prompt": "把 /tmp 下的日志归档", "origin": "composer"},
        )
        snapshot = self.owner.snapshot()
        run = next(
            (r for r in snapshot.get("runs", []) if r["run_id"] == created["run_id"]),
            None,
        )
        self.assertIsNotNone(run)
        self.assertEqual(run.get("input", {}).get("prompt"), "把 /tmp 下的日志归档")

    def test_composer_response_does_not_echo_the_prompt(self):
        # The redacted view must never surface the raw input back to the client.
        cmd = owner_command_source(self.owner)
        result = cmd(
            task_type=COMPOSER_TASK_TYPE,
            input_value={"prompt": "secret-instruction", "origin": "composer"},
        )
        self.assertNotIn("secret-instruction", json.dumps(result))


class ComposerHostTests(unittest.TestCase):
    """The composer form + script over real HTTP on a wired host."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.host = serve_workbench(
            view_source=owner_view_source(owner),
            command_source=owner_command_source(owner),
        )
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_home_carries_composer_script_and_live_form(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertIn(COMPOSER_SCRIPT_ROUTE, home)
        self.assertIn("data-composer", home)
        self.assertIn("data-composer-send", home)
        # A wired host renders the live (enabled) send button, not the shell.
        send_fragment = home.split("data-composer-send")[1].split("</button>")[0]
        self.assertNotIn('aria-disabled="true"', send_fragment)

    def test_composer_script_resource_is_served(self):
        status, body = _get(self.host.base_url, COMPOSER_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/runs", body)
        self.assertIn("composer_message", body)
        self.assertIn("data-composer", body)
        self.assertIn("workbench:run-created", body)

    def test_composer_send_creates_a_run(self):
        status, body = _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {
                "task_type": COMPOSER_TASK_TYPE,
                "input_value": {"prompt": "调度一次只读预检", "origin": "composer"},
                "metadata": {"source": "workbench-ui", "triggered_by": "composer"},
            },
        )
        self.assertEqual(status, 201)
        data = json.loads(body)
        self.assertTrue(str(data["run_id"]).startswith("run-"))
        self.assertEqual(data["status"], "running")


class ReadOnlyHostComposerTests(unittest.TestCase):
    """A read-only host (no command facade) keeps the composer disabled."""

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_home_without_command_facade_shows_disabled_composer(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertNotIn(COMPOSER_SCRIPT_ROUTE, home)
        self.assertIn("data-composer", home)
        # The disabled shell carries aria-disabled="true" on the form.
        self.assertIn('aria-disabled="true"', home)


if __name__ == "__main__":
    unittest.main()
