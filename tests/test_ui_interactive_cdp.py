"""CDP end-to-end assertions for the interactive write seams (1-2 product gate).

The unittest-level seam tests prove the facades and HTTP endpoints.  These
browser-driven tests close the PRD gap named in ``workbench-ui-interactive.md``
§7: they drive the *real* controls in a real headless Chrome over loopback and
observe the real ``CompositionOwner`` side effects -- not a markup model.

Covered interactions (all require the control-plane facade to be wired into the
host, mirroring how the DSH control plane would inject it):

* F6  composer send             -> POST /api/runs creates a composer_message run
* F11 scenario request-stop    -> POST /api/scenario-state safe-stops the run
* F11 scenario request-approval-> POST /api/scenario-state creates a pending approval
* F12 approval-console approve -> POST /api/approvals flips a pending approval to approved
* F12 approval-console deny    -> POST /api/approvals flips a pending approval to denied
* F13 safe-stop banner         -> present as role=alert; reconcile stays disabled
* F19 ?variant=B / ?variant=C  -> server renders the canvas / journal layout
* read-only host invariant     -> no real trigger is ever exposed without a facade

ADR 0004: the verification-stage browser is optional.  When Chrome is absent the
whole module skips; an unavailable engine is not evidence of correct behaviour.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.composition import CompositionOwner
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_view_model import owner_view_source
from zworkbench.ui_run import owner_command_source
from zworkbench.ui_scenario_state import owner_scenario_source
from zworkbench.ui_approval import owner_approval_source
from zworkbench.ui_reconcile import owner_reconcile_source


def _center(engine, selector):
    """Viewport center of the first element matching ``selector``, or ``None``.

    Scrolls the element into view first, because the controls live below the fold
    of the 900px acceptance viewport and a click at an off-screen coordinate would
    miss the real hit-test.
    """
    return engine.evaluate(
        "(() => { const el = document.querySelector("
        + json.dumps(selector)
        + "); if (!el) return null; el.scrollIntoView({block: 'center'});"
        " const r = el.getBoundingClientRect();"
        " return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()"
    )


@unittest.skipUnless(chrome_available(), "the verification-stage browser is absent")
class InteractiveSeamCdpTests(unittest.TestCase):
    """Real-engine assertions for the wired (control-plane-injected) host."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        # One running run -> /home reads it as the latest run in the planning state.
        self.owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-1")
        self.host = serve_workbench(
            view_source=owner_view_source(self.owner),
            command_source=owner_command_source(self.owner),
            scenario_source=owner_scenario_source(self.owner),
            approval_source=owner_approval_source(self.owner),
            reconcile_source=owner_reconcile_source(self.owner),
        )
        self.addCleanup(self.host.close)
        self.addCleanup(self.owner.close)
        self.addCleanup(self.directory.cleanup)

    def _open_home(self, engine, query="", reduced_motion=False):
        engine.open(self.host.base_url + "/home" + query, viewport=(1280, 900),
                    reduced_motion=reduced_motion)
        # Give the deferred progressive-enhancement scripts time to attach.
        time.sleep(0.4)

    def test_composer_send_creates_run_via_real_post(self):
        # F6/1-2-1: typing a prompt and clicking send must create a run through
        # the real command facade, observed on the owner -- not a mock.
        with browser() as engine:
            self._open_home(engine)
            engine.evaluate(
                "document.querySelector('[data-composer-input]').value"
                " = '从工作台执行一个真实任务'"
            )
            box = _center(engine, "[data-composer-send]")
            self.assertIsNotNone(box, "composer send must be a real trigger when wired")
            engine.click(box["x"], box["y"])
            time.sleep(0.8)
        sent = [r for r in self.owner.snapshot()["runs"]
                if r.get("task_type") == "composer_message"]
        self.assertEqual(len(sent), 1, "composer send must POST a composer_message run")
        self.assertEqual(sent[0]["status"], "running")

    def test_scenario_request_stop_safe_stops_latest_run(self):
        # F11/1-2-7: clicking the real request-stop control must safe-stop the
        # latest run through owner.safe_stop_run.
        with browser() as engine:
            self._open_home(engine)
            box = _center(engine, "[data-scenario-request-stop]")
            self.assertIsNotNone(box, "scenario request-stop must be a real trigger when wired")
            engine.click(box["x"], box["y"])
            time.sleep(0.8)
        runs = {r["run_id"]: r for r in self.owner.snapshot()["runs"]}
        self.assertEqual(runs["run-1"]["status"], "safe_stopped")

    def test_scenario_request_approval_creates_pending(self):
        # F11/1-2-7: clicking the real request-approval control must open a pending
        # approval through owner.request_approval.
        with browser() as engine:
            self._open_home(engine)
            box = _center(engine, "[data-scenario-request-approval]")
            self.assertIsNotNone(box, "scenario request-approval must be a real trigger when wired")
            engine.click(box["x"], box["y"])
            time.sleep(0.8)
        approvals = self.owner.snapshot()["approvals"]
        self.assertTrue(any(a["status"] == "pending" for a in approvals),
                        "request-approval must create a pending approval on the owner")

    def test_approval_console_approve_decides_pending_approval(self):
        # F12/1-2-2: clicking the real Approve button on a pending approval must
        # flip it to approved through owner.approve (via the approval command
        # facade) -- observed on the owner, not a mock.
        approval = self.owner.request_approval(
            "run-1", "op-approve", "write_file", "/tmp/target.txt",
            "idem-approve", "execute write_file on target",
        )
        aid = approval["approval_id"]
        with browser() as engine:
            self._open_home(engine)
            box = _center(engine, '[data-approval-approve][data-approval-id="%s"]' % aid)
            self.assertIsNotNone(box, "approve button must be a real trigger when wired")
            engine.click(box["x"], box["y"])
            time.sleep(0.8)
        approvals = {a["approval_id"]: a for a in self.owner.snapshot()["approvals"]}
        self.assertEqual(approvals[aid]["status"], "approved",
                         "approve click must POST /api/approvals and flip the row")

    def test_approval_console_deny_decides_pending_approval(self):
        # F12/1-2-2: clicking the real Deny button must flip the pending approval
        # to denied through owner.deny_approval. The backend requires a non-empty
        # reason, so the test fills the reason input first -- the same step a human
        # must take; an empty reason is rejected by the owner (400), which is the
        # honest contract the UI's "optional" placeholder currently misstates.
        approval = self.owner.request_approval(
            "run-1", "op-deny", "delete_file", "/tmp/target.txt",
            "idem-deny", "require approval for delete_file",
        )
        aid = approval["approval_id"]
        with browser() as engine:
            self._open_home(engine)
            engine.evaluate(
                "document.querySelector('[data-approval-reason=\"%s\"]').value"
                " = '安全策略不允许删除'" % aid
            )
            box = _center(engine, '[data-approval-deny][data-approval-id="%s"]' % aid)
            self.assertIsNotNone(box, "deny button must be a real trigger when wired")
            engine.click(box["x"], box["y"])
            time.sleep(0.8)
        approvals = {a["approval_id"]: a for a in self.owner.snapshot()["approvals"]}
        self.assertEqual(approvals[aid]["status"], "denied",
                         "deny click must POST /api/approvals and flip the row")

    def test_safe_stop_banner_visible_and_reconcile_stays_disabled(self):
        # F13/1-2-5+1-2-8: a stopped run shows the alert banner in a real engine,
        # and the reconcile button stays a disabled placeholder until a concrete
        # identity violation is detected.
        self.owner.safe_stop_run("run-1", reason="manual")
        with browser() as engine:
            self._open_home(engine)
            banner = engine.evaluate("!!document.querySelector('[role=\"alert\"].safe-stop')")
            self.assertTrue(banner, "the safe-stop banner must render as role=alert")
            info = engine.evaluate(
                "(() => { const b = document.querySelector('.reconcile-button');"
                " if (!b) return { present: false };"
                " return { present: true,"
                " disabled: b.disabled || b.getAttribute('aria-disabled') === 'true',"
                " real: !!b.getAttribute('data-reconcile-button') }; })()"
            )
            self.assertTrue(info["present"], "a reconcile button must be present")
            self.assertTrue(info["disabled"], "without a detected violation it stays disabled")
            self.assertFalse(info["real"], "no real trigger until a violation is detected")

    def test_safe_stop_banner_visible_under_reduced_motion(self):
        # Reuse the browser harness' reduced-motion mechanism (PRD §7): the banner
        # must still be present and honest when the engine emulates the media query.
        self.owner.safe_stop_run("run-1", reason="manual")
        with browser() as engine:
            self._open_home(engine, reduced_motion=True)
            banner = engine.evaluate("!!document.querySelector('[role=\"alert\"].safe-stop')")
            self.assertTrue(banner)

    def test_variant_b_renders_canvas_layout(self):
        # F19/1-3-1: ?variant=B drives the server-rendered canvas content branch.
        with browser() as engine:
            self._open_home(engine, query="?variant=B")
            has_canvas = engine.evaluate("!!document.querySelector('section.variant-canvas')")
            has_journal = engine.evaluate("!!document.querySelector('section.variant-journal')")
            self.assertTrue(has_canvas, "variant=B must render the canvas layout")
            self.assertFalse(has_journal, "variant=B must not render the journal layout")

    def test_variant_c_renders_journal_layout(self):
        # F19/1-3-2: ?variant=C drives the server-rendered journal content branch.
        with browser() as engine:
            self._open_home(engine, query="?variant=C")
            has_canvas = engine.evaluate("!!document.querySelector('section.variant-canvas')")
            has_journal = engine.evaluate("!!document.querySelector('section.variant-journal')")
            self.assertFalse(has_canvas, "variant=C must not render the canvas layout")
            self.assertTrue(has_journal, "variant=C must render the journal layout")


@unittest.skipUnless(chrome_available(), "the verification-stage browser is absent")
class ReadOnlyHostCdpTests(unittest.TestCase):
    """Real-engine proof that a read-only host never exposes a write trigger."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
        self.owner.start_run("run-1")
        # No facade injected: this is exactly the read-only CLI `ui-host` shape.
        self.host = serve_workbench(view_source=owner_view_source(self.owner))
        self.addCleanup(self.host.close)
        self.addCleanup(self.owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_no_real_scenario_trigger_is_exposed(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            time.sleep(0.4)
            real = engine.evaluate(
                "(() => {"
                " const stop = document.querySelector('[data-scenario-request-stop]');"
                " const approve = document.querySelector('[data-scenario-request-approval]');"
                " return { stop: !!stop, approve: !!approve }; })()"
            )
            self.assertFalse(real["stop"], "read-only host must not expose a real stop trigger")
            self.assertFalse(real["approve"], "read-only host must not expose a real approval trigger")
            # Disabled placeholders must still be present (no dead affordance).
            placeholders = engine.evaluate(
                "document.querySelectorAll('.scenario-control[aria-disabled=\"true\"]').length"
            )
            self.assertGreater(placeholders, 0, "scenario controls degrade to disabled placeholders")

    def test_composer_send_is_disabled_on_read_only_host(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            time.sleep(0.4)
            disabled = engine.evaluate(
                "(() => { const b = document.querySelector('[data-composer-send]');"
                " return !!b && (b.disabled || b.getAttribute('aria-disabled') === 'true'); })()"
            )
            self.assertTrue(disabled, "read-only host must keep the composer send disabled")

    def test_approval_console_has_no_real_trigger_on_read_only_host(self):
        # Even with a pending approval present, a read-only host (no approval
        # command facade) must render only the disabled hint, never a real
        # approve/deny trigger that would POST to /api/approvals.
        self.owner.request_approval(
            "run-1", "op-ro", "write_file", "/tmp/target.txt",
            "idem-ro", "read-only host must not expose approval triggers",
        )
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            time.sleep(0.4)
            real = engine.evaluate(
                "(() => {"
                " const approve = document.querySelector('[data-approval-approve]');"
                " const deny = document.querySelector('[data-approval-deny]');"
                " return { approve: !!approve, deny: !!deny }; })()"
            )
            self.assertFalse(real["approve"], "read-only host must not expose an approve trigger")
            self.assertFalse(real["deny"], "read-only host must not expose a deny trigger")
            hint = engine.evaluate("!!document.querySelector('.approval-disabled-hint')")
            self.assertTrue(hint, "read-only host must show the disabled approval hint")


if __name__ == "__main__":
    unittest.main()
