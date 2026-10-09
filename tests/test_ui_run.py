"""Behaviour tests for the F10 executable-Run write seam.

The seam under test is the loopback host's POST /api/runs endpoint plus the
run trigger script, exercised through real HTTP. The owner is a real
CompositionOwner on a temp database, so these tests prove the button actually
creates + starts a run -- not a mock.
"""

import json
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.composition import CompositionOwner
from zworkbench.local_run import LocalReadOnlyRunConfig
from zworkbench.ui_host import (
    LIVE_FACTS_ROUTE,
    RUN_API_ROUTE,
    RUN_SCRIPT_ROUTE,
    serve_workbench,
)
from zworkbench.ui_run import (
    _prompt_from_input,
    owner_command_source,
    owner_command_source_with_executor,
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


class CommandFacadeTests(unittest.TestCase):
    """The narrow write facade against a real owner."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")

    def tearDown(self):
        self.owner.close()
        self.directory.cleanup()

    def test_create_and_start_moves_run_into_running(self):
        cmd = owner_command_source(self.owner)
        result = cmd(
            task_type="interactive_run",
            input_value={"prompt": "x"},
            metadata={"source": "test"},
        )
        self.assertTrue(str(result["run_id"]).startswith("run-"))
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["task_type"], "interactive_run")
        self.assertIn("created_at", result)

    def test_created_run_is_durable_in_the_owner(self):
        cmd = owner_command_source(self.owner)
        created = cmd(task_type="interactive_run", input_value={"prompt": "x"})
        snapshot = self.owner.snapshot()
        run_ids = [r["run_id"] for r in snapshot.get("runs", [])]
        self.assertIn(created["run_id"], run_ids)


class RunApiEndpointTests(unittest.TestCase):
    """The host's POST /api/runs contract, observed over real HTTP."""

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

    def test_post_creates_and_starts_a_run(self):
        status, body = _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {
                "task_type": "interactive_run",
                "input_value": {"prompt": "manual trigger"},
                "metadata": {"source": "workbench-ui"},
            },
        )
        self.assertEqual(status, 201)
        data = json.loads(body)
        self.assertTrue(str(data["run_id"]).startswith("run-"))
        self.assertEqual(data["status"], "running")

    def test_live_facts_reflects_the_new_run(self):
        _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {"task_type": "interactive_run", "input_value": {"prompt": "x"}},
        )
        _, facts = _get(self.host.base_url, LIVE_FACTS_ROUTE)
        data = json.loads(facts)
        self.assertEqual(data["status"], "running")
        self.assertTrue(str(data["run_id"]).startswith("run-"))

    def test_post_rejects_missing_input_value(self):
        status, _ = _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {"task_type": "interactive_run"},
        )
        self.assertEqual(status, 400)

    def test_post_rejects_missing_task_type(self):
        status, _ = _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {"input_value": {"prompt": "x"}},
        )
        self.assertEqual(status, 400)

    def test_post_rejects_non_json_body(self):
        body = b"not json"
        request = urllib.request.Request(
            self.host.base_url + RUN_API_ROUTE,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with DIRECT.open(request, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertEqual(status, 400)

    def test_run_script_resource_is_served(self):
        status, body = _get(self.host.base_url, RUN_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/runs", body)
        self.assertIn("workbench:run-created", body)

    def test_home_carries_run_script_and_trigger_button(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertIn(RUN_SCRIPT_ROUTE, home)
        self.assertIn("data-run-trigger", home)
        self.assertNotIn('aria-disabled="true"', home.split("rail-run-button")[1].split("</button>")[0])


class ExecutorCommandFacadeTests(unittest.TestCase):
    """The executing facade runs a started run to a terminal state in the owner."""

    def _make_config(self, *, codex_exists: bool):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        case_root = Path(directory.name)
        workspace = case_root / "workspace"
        workspace.mkdir()
        code_home = case_root / "codex-home"
        code_home.mkdir()
        event_log = case_root / "events" / "codex.jsonl"
        event_log.parent.mkdir()
        database = case_root / "owner.sqlite3"
        codex = case_root / "codex"
        if codex_exists:
            codex.write_text("#!/bin/sh\n")
            codex.chmod(0o755)
        # Missing codex -> preflight denies; existing-but-loopback -> would attempt.
        return LocalReadOnlyRunConfig(
            case_root=case_root,
            workspace=workspace,
            database=database,
            code_home=code_home,
            codex_executable=codex,
            event_log=event_log,
            provider_identity={
                "provider": "fake-loopback",
                "model": "fake-model",
                "endpoint": "http://127.0.0.1:11434",
                "model_provider": "ollama",
            },
        )

    def _wait_terminal(self, owner, run_id, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if owner.get_run(run_id)["status"] != "running":
                return owner.get_run(run_id)["status"]
            time.sleep(0.02)
        return owner.get_run(run_id)["status"]

    def test_prompt_from_input_pulls_composer_text(self):
        self.assertEqual(_prompt_from_input({"prompt": "hi", "origin": "composer"}), "hi")
        self.assertEqual(_prompt_from_input({"origin": "x"}), "")
        self.assertEqual(_prompt_from_input(None), "")

    def test_executor_fails_run_when_preflight_denied(self):
        # A missing codex executable makes preflight deny; the executor must move
        # the started run out of `running` (no dangling run), recording the denial.
        config = self._make_config(codex_exists=False)
        owner = CompositionOwner(config.database)
        self.addCleanup(owner.close)
        cmd = owner_command_source_with_executor(owner, config, timeout=5.0)
        result = cmd(task_type="interactive_run", input_value={"prompt": "hello"})
        run_id = result["run_id"]
        self.assertEqual(owner.get_run(run_id)["status"], "running")
        status = self._wait_terminal(owner, run_id)
        self.assertEqual(status, "failed")

    def test_executor_does_not_double_claim_existing_run(self):
        # The facade created + started the run; the executor must drive it with
        # run_claim="assume" and not raise on the already-present run identity.
        config = self._make_config(codex_exists=False)
        owner = CompositionOwner(config.database)
        self.addCleanup(owner.close)
        cmd = owner_command_source_with_executor(owner, config, timeout=5.0)
        result = cmd(task_type="interactive_run", input_value={"prompt": "x"})
        self._wait_terminal(owner, result["run_id"])
        # No CompositionError escaped: the run simply reached a terminal state.
        self.assertIn(
            owner.get_run(result["run_id"])["status"],
            {"failed", "safe_stopped", "completed"},
        )


class ReadOnlyHostRunApiTests(unittest.TestCase):
    """A read-only host (no command facade) must refuse the write surface."""

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_post_without_command_facade_is_refused(self):
        status, _ = _post(
            self.host.base_url,
            RUN_API_ROUTE,
            {"task_type": "interactive_run", "input_value": {"prompt": "x"}},
        )
        self.assertEqual(status, 404)

    def test_home_without_command_facade_shows_disabled_button(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertNotIn(RUN_SCRIPT_ROUTE, home)
        self.assertNotIn("data-run-trigger", home)
        self.assertIn('aria-disabled="true"', home)


if __name__ == "__main__":
    unittest.main()
