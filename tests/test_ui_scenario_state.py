"""Behaviour tests for the F11 scenario-state write seam (1-2-7).

The seam under test is the loopback host's POST /api/scenario-state endpoint plus
the scenario-state stepper's controls, exercised through real HTTP. The owner is a
real CompositionOwner on a temp database, so these tests prove the controls
actually drive the scenario state machine -- not a mock.

A read-only host (no scenario facade) must refuse the write surface with 404, and
the stepper's controls must degrade to disabled placeholders. A wired host flips
the controls to real triggers and the endpoint drives ``owner.request_approval`` /
``owner.safe_stop_run``.
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
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_scenario_state import (
    SCENARIO_API_ROUTE,
    SCENARIO_SCRIPT_ROUTE,
    owner_scenario_source,
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


def _seed(owner):
    """Create one clean run so the scenario reads `planning` (no pending approval).

    This is the only run seeded, so it is the latest run and the /home stepper
    (auto-selected by latest run) renders in the planning state with both controls
    visible. The pending-approval used by the approval-state test is created
    locally inside that test so it cannot displace this run's planning state.
    """
    owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
    owner.start_run("run-1")
    return "run-1"


class ScenarioFacadeTests(unittest.TestCase):
    """The narrow scenario-state facade against a real owner."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")

    def tearDown(self):
        self.owner.close()
        self.directory.cleanup()

    def test_request_approval_creates_pending(self):
        self.owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-1")
        src = owner_scenario_source(self.owner)
        result = src(
            action="request_approval",
            run_id="run-1",
            operation_id="op-1",
            op_action="execute",
            resource="scenario",
            idempotency_key="idem-1",
            reason="t",
        )
        self.assertEqual(result["status"], "pending")
        approvals = [a for a in self.owner.snapshot()["approvals"]]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["status"], "pending")

    def test_request_stop_safe_stops_run(self):
        self.owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-1")
        src = owner_scenario_source(self.owner)
        result = src(action="request_stop", run_id="run-1", reason="stop it")
        self.assertEqual(result["status"], "safe_stopped")

    def test_unknown_action_raises(self):
        src = owner_scenario_source(self.owner)
        with self.assertRaises(ValueError):
            src(action="bogus", run_id="x")


class ScenarioApiEndpointTests(unittest.TestCase):
    """The host's scenario-state write contract, observed over real HTTP."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.run_id = _seed(owner)
        self.host = serve_workbench(
            view_source=owner_view_source(owner),
            scenario_source=owner_scenario_source(owner),
        )
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_post_request_approval_creates_pending(self):
        status, body = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {
                "action": "request_approval",
                "run_id": self.run_id,
                "operation_id": "op-1",
                "op_action": "execute",
                "resource": "scenario",
                "idempotency_key": "idem-1",
                "reason": "t",
            },
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "pending")

    def test_post_request_stop_safe_stops(self):
        status, body = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {"action": "request_stop", "run_id": self.run_id, "reason": "stop"},
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "safe_stopped")

    def test_post_rejects_missing_run_id(self):
        status, _ = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {"action": "request_stop", "reason": "stop"},
        )
        self.assertEqual(status, 400)

    def test_post_rejects_missing_required_approval_field(self):
        status, _ = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {"action": "request_approval", "run_id": self.run_id},
        )
        self.assertEqual(status, 400)

    def test_post_rejects_unknown_action(self):
        status, _ = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {"action": "bogus", "run_id": self.run_id},
        )
        self.assertEqual(status, 400)

    def test_home_carries_scenario_script_and_buttons(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertIn(SCENARIO_SCRIPT_ROUTE, home)
        # The latest run (run-1) is in the planning state and the host is wired,
        # so both controls render as real triggers, not disabled placeholders.
        self.assertIn("data-scenario-request-approval", home)
        self.assertIn("data-scenario-request-stop", home)
        self.assertIn('data-scenario-run-id="{0}"'.format(self.run_id), home)

    def test_scenario_script_resource_is_served(self):
        status, body = _get(self.host.base_url, SCENARIO_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/scenario-state", body)
        self.assertIn("workbench:scenario-changed", body)


class ReadOnlyHostScenarioTests(unittest.TestCase):
    """A read-only host (no scenario facade) must refuse the write surface."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.run_id = _seed(owner)
        # Wired view but NO scenario_source -> read-only host.
        self.host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_post_scenario_state_without_facade_is_refused(self):
        status, _ = _post(
            self.host.base_url,
            SCENARIO_API_ROUTE,
            {"action": "request_stop", "run_id": self.run_id, "reason": "stop"},
        )
        self.assertEqual(status, 404)

    def test_home_without_facade_shows_disabled_placeholders(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertNotIn(SCENARIO_SCRIPT_ROUTE, home)
        self.assertNotIn("data-scenario-request-approval", home)
        # The disabled placeholder still renders the control (so the UI shows the
        # affordance exists) but without the trigger data attributes.
        self.assertIn("scenario-control-request-approval", home)
        self.assertIn("disabled", home)


if __name__ == "__main__":
    unittest.main()
