"""Regression tests for the 1-6/1-7 review findings.

Each finding below was demonstrated against the code before it was fixed; the
tests pin the fixed behaviour so the failure mode cannot return quietly.
"""

import json
import re
import html
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import render_panel, serve_workbench
from zworkbench.ui_record_view import record_manifest
from zworkbench.ui_task_detail import task_detail_manifest

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ThePanelMountsOnlyWhatTheRouteDeclaresTests(unittest.TestCase):
    """Finding 1: hard-coding one view's ref crashed every other route."""

    def test_a_route_without_the_home_list_ref_does_not_crash(self):
        """Before the fix this raised UnregisteredReference; over HTTP the
        client saw RemoteDisconnected with no response at all."""
        document = render_panel(
            task_detail_manifest(), {"records": [{"title": "x"}]}, "/task-detail"
        )
        self.assertIn('data-ui-panel="review"', document)
        self.assertNotIn("home.record-list.item", document)

    def test_the_record_view_panel_mounts_its_own_list_ref(self):
        document = render_panel(
            record_manifest(), {"events": [{"title": "e1"}]}, "/record-view"
        )
        self.assertIn("record-view.event-list.item", document)
        self.assertNotIn("home.record-list.item", document)

    def test_over_http_a_record_view_page_in_review_mode_serves_cleanly(self):
        """The crash path, observed through the actual wire protocol."""
        host = serve_workbench(
            view_source=lambda route: {"events": [{"title": "e1"}]}, review=True
        )
        self.addCleanup(host.close)
        with DIRECT.open(host.base_url + "/record-view", timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("record-view.event-list.item", body)


class TheTokenStateReflectsWhatWasServedTests(unittest.TestCase):
    """Finding 4: a page showing 'running' minted a token claiming 'unknown'."""

    def _wide_token(self, document):
        match = re.search(r'data-ui-panel-token-wide="([^"]+)', document)
        self.assertIsNotNone(match)
        return json.loads(html.unescape(match.group(1)))

    def test_a_running_view_mints_a_running_token(self):
        document = render_panel(
            home_manifest(),
            {"records": [{"title": "a"}], "run_facts": {"status": "running"}},
            "/home",
        )
        self.assertEqual(self._wide_token(document)["state"], "running")

    def test_an_unrecognised_status_falls_back_to_unknown(self):
        """The host validates against the token whitelist; it does not invent
        states the contract rejects."""
        document = render_panel(
            home_manifest(),
            {"records": [{"title": "a"}], "run_facts": {"status": "invented"}},
            "/home",
        )
        self.assertEqual(self._wide_token(document)["state"], "unknown")

    def test_a_mode_label_is_not_a_display_state(self):
        """recorded_view is a replay mode, not a STATES value; unknown is honest."""
        document = render_panel(
            record_manifest(),
            {"events": [{"title": "e1"}], "mode": "recorded_view"},
            "/record-view",
        )
        self.assertEqual(self._wide_token(document)["state"], "unknown")


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class TheReviewEntryReopensThePanelTests(unittest.TestCase):
    """Finding 2: close was a one-way door and the focus fallback was dead."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: {"records": [{"title": "a"}]}, review=True
        )
        self.addCleanup(self.host.close)

    def _panel_state(self, engine):
        return json.loads(engine.evaluate("""
          JSON.stringify({
            hidden: document.querySelector('[data-ui-panel="review"]').hasAttribute('hidden'),
            pressed: document.querySelector('[data-ui-review-entry]')
              .getAttribute('aria-pressed'),
            activePanel: (() => {
              const node = document.activeElement;
              return node ? node.getAttribute('data-ui-panel-action') : null;
            })(),
          })
        """))

    def _click(self, engine, selector, modifiers=0):
        where = json.loads(engine.evaluate(
            "(() => {"
            "  const node = document.querySelector('" + selector + "');"
            "  const box = node.getBoundingClientRect();"
            "  return JSON.stringify({"
            "    x: box.left + box.width / 2, y: box.top + box.height / 2});"
            "})()"
        ))
        engine.click(where["x"], where["y"], modifiers=modifiers)

    def test_closing_then_clicking_the_entry_reopens_the_panel(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self._click(engine, '[data-ui-panel-action="close"]')
            closed = self._panel_state(engine)
            self.assertTrue(closed["hidden"])
            self.assertEqual(closed["pressed"], "false")
            self._click(engine, "[data-ui-review-entry]")
            reopened = self._panel_state(engine)
        self.assertFalse(reopened["hidden"])
        self.assertEqual(reopened["pressed"], "true")

    def test_reopening_moves_focus_into_the_panel(self):
        """The fallback focus target is no longer a dead end: it leads back in."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self._click(engine, '[data-ui-panel-action="close"]')
            self._click(engine, "[data-ui-review-entry]")
            active = self._panel_state(engine)["activePanel"]
        self.assertEqual(active, "select")

    def test_shift_click_walks_the_selection_backwards(self):
        """Finding 6: a one-way select forced a full lap to reach an earlier row.

        Shift is the same qualifier that reverses Tab, so the pointer path
        learns the same direction pair the keyboard already has. Two rows are
        needed: with one entry forwards and backwards are the same move and
        the assertion would pass on a broken step.
        """
        host = serve_workbench(
            view_source=lambda route: {
                "records": [{"title": "a"}, {"title": "b"}]
            },
            review=True,
        )
        self.addCleanup(host.close)
        with browser() as engine:
            engine.open(host.base_url + "/home", viewport=(1280, 900))
            self._click(engine, '[data-ui-panel-action="select"]')
            forward = engine.evaluate(
                "Array.from(document.querySelectorAll('[data-ui-panel-entry]'))"
                ".indexOf(document.querySelector('[data-ui-panel-locked]'))"
            )
            self._click(engine, '[data-ui-panel-action="select"]', modifiers=8)
            back = engine.evaluate(
                "Array.from(document.querySelectorAll('[data-ui-panel-entry]'))"
                ".indexOf(document.querySelector('[data-ui-panel-locked]'))"
            )
        self.assertEqual(forward, 0)
        self.assertEqual(back, 1)

    def test_a_close_reopen_cycle_changes_no_review_state(self):
        """Reopening is not a fresh review session: the selection survives."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self._click(engine, '[data-ui-panel-action="select"]')
            self._click(engine, '[data-ui-panel-action="close"]')
            self._click(engine, "[data-ui-review-entry]")
            locked = engine.evaluate(
                "!!document.querySelector('[data-ui-panel-locked=\\'true\\']')"
            )
        self.assertTrue(locked)


if __name__ == "__main__":
    unittest.main()
