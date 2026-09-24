"""Behaviour tests for the F12 approval-execution write seam.

The seam under test is the loopback host's POST /api/approvals (approve/deny)
and POST /api/effects (record receipt) endpoints plus the approval-console
handler, exercised through real HTTP. The owner is a real CompositionOwner on a
temp database, so these tests prove the human decision actually flips an
approval / commits an effect -- not a mock.

"apply diff" and "retry" are deliberately out of scope here: approving
authorises the worker (control plane) to apply the diff, exactly as F10/F6 let
the UI create + start a run while the real execution stays server-side. The UI
surface owns only the human-decidable verbs (approve/deny/record receipt).
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
from zworkbench.ui_approval import (
    APPROVAL_API_ROUTE,
    APPROVAL_SCRIPT_ROUTE,
    EFFECT_API_ROUTE,
    owner_approval_source,
)
from zworkbench.ui_host import serve_workbench
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
    """Create one running run, one pending approval and one claimed effect."""
    owner.create_run("run-seed", "interactive_run", {"prompt": "x"}, {})
    owner.start_run("run-seed")
    approval = owner.request_approval(
        "run-seed", "op-approve", "write_file", "/tmp/target.txt", "idem-approve",
        "seed: require approval for write_file",
    )
    effect = owner.claim_effect(
        "run-seed", "op-effect", "write_file", "/tmp/out.txt", "idem-effect", "idempotent"
    )
    return approval["approval_id"], effect.effect_id


class ApprovalFacadeTests(unittest.TestCase):
    """The narrow approval facade against a real owner."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")

    def tearDown(self):
        self.owner.close()
        self.directory.cleanup()

    def test_approve_flips_a_pending_approval(self):
        approval_id, _ = _seed(self.owner)
        src = owner_approval_source(self.owner)
        result = src(action="approve", approval_id=approval_id)
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["approval_id"], approval_id)
        self.assertNotIn("token_hash", result)

    def test_deny_flips_a_pending_approval(self):
        approval_id, _ = _seed(self.owner)
        src = owner_approval_source(self.owner)
        result = src(action="deny", approval_id=approval_id, reason="risk")
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["decision_reason"], "risk")

    def test_record_effect_commits_a_claimed_effect(self):
        _, effect_id = _seed(self.owner)
        src = owner_approval_source(self.owner)
        result = src(action="complete_effect", effect_id=effect_id, external_receipt={"ok": True})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["effect_id"], effect_id)
        self.assertEqual(result["physical_effect_count"], 1)

    def test_unknown_action_is_rejected(self):
        src = owner_approval_source(self.owner)
        with self.assertRaises(ValueError):
            src(action="explode", approval_id="x")


class ApprovalApiEndpointTests(unittest.TestCase):
    """The host's approval/effect write contracts, observed over real HTTP."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        self.approval_id, self.effect_id = _seed(owner)
        self.host = serve_workbench(
            view_source=owner_view_source(owner),
            approval_source=owner_approval_source(owner),
        )
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_post_approve_decides_the_approval(self):
        status, body = _post(
            self.host.base_url,
            APPROVAL_API_ROUTE,
            {"action": "approve", "approval_id": self.approval_id},
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "approved")
        self.assertNotIn("token_hash", data)

    def test_post_deny_decides_the_approval(self):
        status, body = _post(
            self.host.base_url,
            APPROVAL_API_ROUTE,
            {"action": "deny", "approval_id": self.approval_id, "reason": "nope"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "denied")

    def test_post_record_effect_commits_receipt(self):
        status, body = _post(
            self.host.base_url,
            EFFECT_API_ROUTE,
            {"effect_id": self.effect_id, "external_receipt": {"applied": True}},
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["physical_effect_count"], 1)

    def test_post_approve_rejects_missing_approval_id(self):
        status, _ = _post(
            self.host.base_url, APPROVAL_API_ROUTE, {"action": "approve"}
        )
        self.assertEqual(status, 400)

    def test_post_approve_rejects_bad_action(self):
        status, _ = _post(
            self.host.base_url,
            APPROVAL_API_ROUTE,
            {"action": "merge", "approval_id": self.approval_id},
        )
        self.assertEqual(status, 400)

    def test_post_effect_rejects_missing_effect_id(self):
        status, _ = _post(
            self.host.base_url, EFFECT_API_ROUTE, {"external_receipt": {}}
        )
        self.assertEqual(status, 400)

    def test_home_carries_approval_script_and_live_controls(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertIn(APPROVAL_SCRIPT_ROUTE, home)
        self.assertIn("data-approval-approve", home)
        self.assertIn("data-effect-receipt", home)
        # The console is wired (can_decide=True), so the controls are not the
        # disabled read-only shell.
        self.assertNotIn(
            "只读宿主：审批未接线命令面", home.split("approval-console-section")[1].split("</section>")[0]
        )

    def test_approval_script_resource_is_served(self):
        status, body = _get(self.host.base_url, APPROVAL_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/approvals", body)
        self.assertIn("/api/effects", body)
        self.assertIn("workbench:decision-made", body)


class ReadOnlyHostApprovalTests(unittest.TestCase):
    """A read-only host (no approval facade) must refuse the write surface."""

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_post_approvals_without_facade_is_refused(self):
        status, _ = _post(
            self.host.base_url,
            APPROVAL_API_ROUTE,
            {"action": "approve", "approval_id": "anything"},
        )
        self.assertEqual(status, 404)

    def test_post_effects_without_facade_is_refused(self):
        status, _ = _post(
            self.host.base_url,
            EFFECT_API_ROUTE,
            {"effect_id": "anything"},
        )
        self.assertEqual(status, 404)

    def test_home_without_facade_shows_disabled_console(self):
        _, home = _get(self.host.base_url, "/home")
        self.assertNotIn(APPROVAL_SCRIPT_ROUTE, home)
        self.assertIn("只读宿主：审批未接线命令面", home)


if __name__ == "__main__":
    unittest.main()
