"""Behaviour tests for the F13 reconcile write seam (1-2-8).

The seam under test is the loopback host's POST /api/reconcile endpoint plus the
safe-stop banner's reconcile button, exercised through real HTTP. The owner is a
real CompositionOwner on a temp database, so these tests prove the click actually
re-runs identity reconciliation -- not a mock.

A read-only host (no reconcile facade) must refuse the write surface with 404,
and the safe-stop banner must degrade to its disabled placeholder. A wired host
flips the button to a real trigger and the endpoint re-runs
``owner.reconcile_identity``. A safe-stopped run is terminal: reconcile records
the decision durably but never resurrects it (honest terminal state, per
1-2-5 Q2).
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
from zworkbench.ui_reconcile import (
    RECONCILE_API_ROUTE,
    RECONCILE_SCRIPT_ROUTE,
    owner_reconcile_source,
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
    """Create one run with a broken identity reference.

    This is the only run seeded, so it is the latest run and the /home banner
    (auto-selected by latest run) renders its active reconcile button. The clean
    run used by the resolve test is created locally inside that test so it cannot
    displace this violation run as the latest.
    """
    # A broken child_run_id in metadata is an unresolved identity reference, so
    # the run fails the identity-graph scan and the safe-stop banner activates.
    owner.create_run(
        "run-bad", "interactive_run", {"prompt": "y"}, {"child_run_id": "missing-child"}
    )
    owner.start_run("run-bad")
    return "run-bad"


class ReconcileFacadeTests(unittest.TestCase):
    """The narrow reconcile facade against a real owner."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")

    def tearDown(self):
        self.owner.close()
        self.directory.cleanup()

    def test_owner_adapted_to_narrow_facade(self):
        # A clean run (no broken references) reconciles to resolved.
        self.owner.create_run("run-clean", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-clean")
        src = owner_reconcile_source(self.owner)
        result = src(run_id="run-clean")
        self.assertEqual(result["outcome"], "resolved")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["violations"], [])

    def test_reconcile_records_decision_but_keeps_terminal_run(self):
        bad = _seed(self.owner)
        src = owner_reconcile_source(self.owner)
        # run-bad has a broken reference, so reconciliation stays unknown and the
        # run is held safe-stopped -- never resurrected.
        result = src(run_id=bad)
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["status"], "safe_stopped")
        self.assertTrue(result["violations"])


class ReconcileApiEndpointTests(unittest.TestCase):
    """The host's reconcile write contract, observed over real HTTP."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.bad_id = _seed(owner)
        self.host = serve_workbench(
            view_source=owner_view_source(owner),
            reconcile_source=owner_reconcile_source(owner),
        )
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_post_reconcile_resolves_clean_run(self):
        # Create a clean run locally so it does not displace run-bad as the latest
        # (the home test already ran and depends on run-bad being the banner run).
        self.owner.create_run("run-clean", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-clean")
        status, body = _post(
            self.host.base_url, RECONCILE_API_ROUTE, {"run_id": "run-clean"}
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["outcome"], "resolved")
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["violations"], [])

    def test_post_reconcile_keeps_safe_stopped(self):
        status, body = _post(
            self.host.base_url, RECONCILE_API_ROUTE, {"run_id": self.bad_id}
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["outcome"], "unknown")
        self.assertEqual(data["status"], "safe_stopped")
        self.assertTrue(data["violations"])

    def test_post_reconcile_rejects_missing_run_id(self):
        status, _ = _post(self.host.base_url, RECONCILE_API_ROUTE, {})
        self.assertEqual(status, 400)

    def test_post_reconcile_rejects_unknown_run(self):
        # A clean graph but a non-existent run_id makes owner.reconcile_identity
        # raise when it reads the run in the resolved branch; that surfaces as 400.
        status, _ = _post(self.host.base_url, RECONCILE_API_ROUTE, {"run_id": "ghost"})
        self.assertEqual(status, 400)

    def test_home_carries_reconcile_script_and_button(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertIn(RECONCILE_SCRIPT_ROUTE, home)
        # The latest run (run-bad) has a violation and the host is wired, so the
        # button is a real trigger, not the disabled placeholder.
        self.assertIn("data-reconcile-button", home)
        self.assertIn('data-reconcile-run-id="{0}"'.format(self.bad_id), home)

    def test_reconcile_script_resource_is_served(self):
        status, body = _get(self.host.base_url, RECONCILE_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/reconcile", body)
        self.assertIn("workbench:reconcile-done", body)


class ReadOnlyHostReconcileTests(unittest.TestCase):
    """A read-only host (no reconcile facade) must refuse the write surface."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.bad_id = _seed(owner)
        # Wired view but NO reconcile_source -> read-only host.
        self.host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_post_reconcile_without_facade_is_refused(self):
        status, _ = _post(
            self.host.base_url, RECONCILE_API_ROUTE, {"run_id": self.bad_id}
        )
        self.assertEqual(status, 404)

    def test_home_without_facade_shows_disabled_placeholder(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertNotIn(RECONCILE_SCRIPT_ROUTE, home)
        self.assertNotIn("data-reconcile-button", home)


if __name__ == "__main__":
    unittest.main()
