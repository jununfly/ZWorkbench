"""1-6-1 — the tab order a real engine produces in review mode.

This is the half of the keyboard contract a state machine cannot reach.
``tests/test_ui_review.py`` settles which actions exist and which key each one
answers to; ``tests/test_ui_panel.py`` settles that each one is rendered as a
focusable control. Neither can say what happens when a human presses Tab: that
order is decided by the engine from document order, tabindex and its own
policy, so it is measured here by dispatching real key events.

Focus is read back from ``document.activeElement`` after each press rather than
predicted from the markup. Predicting it would re-implement the browser's
focus algorithm in the test and then assert the test against itself.
"""

import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_review import PANEL_ACTIONS

#: The review-mode ring: every declared element in document order, then the
#: review entry, then every panel action. Static units are stops because the
#: page layer gives them tabindex -- a keyboard reviewer has no hover, so
#: traversal is their only way to point at one. The business order is the
#: renderer's output order; a renderer that reordered sections would reorder
#: the ring, which is exactly what this asserts against.
BUSINESS_STOPS = [
    "ref:home.root",
    "ref:home.workspace-context",
    "ref:home.run-facts",
    "ref:home.record-list",
    "ref:home.record-list.item",
    "ref:home.record-list.item",
    "ref:home.current-intent",
    "ref:home.plan-next-step",
    "ref:home.artifacts",
    "ref:home.evidence",
    "ref:home.preflight-run.action",
    "ref:home.preflight-result",
]
REVIEW_RING = BUSINESS_STOPS + ["entry"] + [
    "panel:" + action for action in PANEL_ACTIONS
]

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}

#: Reads the focused element as either a panel action or a business reference.
#: Elements that are neither answer with their tag alone, so an unexpected stop
#: in the sequence is visible instead of being folded into ``None``.
FOCUSED = (
    "(() => {"
    "  const node = document.activeElement;"
    "  if (!node || node === document.body) return 'none';"
    "  const action = node.getAttribute('data-ui-panel-action');"
    "  if (action) return 'panel:' + action;"
    "  if (node.hasAttribute('data-ui-review-entry')) return 'entry';"
    "  const ref = node.getAttribute('data-ui-ref');"
    "  if (ref) return 'ref:' + ref;"
    "  if (node.hasAttribute('data-ui-overlay')) return 'overlay';"
    "  return 'other:' + node.tagName;"
    "})()"
)


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; keyboard-focus-order stays unknown",
)
class TabOrderInARealEngineTests(unittest.TestCase):
    def _walk(self, review, presses, key="Tab"):
        host = serve_workbench(view_source=lambda route: VIEW_MODEL, review=review)
        self.addCleanup(host.close)
        with browser() as engine:
            engine.open(host.base_url + "/home", viewport=(1280, 900))
            stops = []
            for _ in range(presses):
                engine.press(key)
                stops.append(engine.evaluate(FOCUSED))
            return stops

    def test_the_review_layer_does_not_take_focus_before_the_business_page(self):
        """A reviewer tabs into the page they are reviewing, not into the tool.

        Every declared business element comes before the review entry and the
        panel. If the tool came first, every keyboard user would traverse it
        before reaching the content on every page load.
        """
        stops = self._walk(review=True, presses=len(REVIEW_RING))
        self.assertEqual(stops[: len(BUSINESS_STOPS)], BUSINESS_STOPS)
        self.assertEqual(stops[len(BUSINESS_STOPS)], "entry")

    def test_tab_reaches_static_units_a_pointer_would_hover(self):
        """The point of the change: record rows are text, not controls, and
        without the page layer's tabindex no keyboard path could point at one."""
        stops = self._walk(review=True, presses=len(REVIEW_RING))
        self.assertEqual(
            stops.count("ref:home.record-list.item"), 2
        )

    def test_every_stop_appears_in_the_declared_order(self):
        """Reachable and in document order, then tool order.

        An engine that produced a different sequence would mean the rendered
        document had reordered them, which is exactly the drift this asserts
        against.
        """
        stops = self._walk(review=True, presses=len(REVIEW_RING))
        self.assertEqual(stops, REVIEW_RING)

    def test_the_highlight_layer_never_receives_focus(self):
        """It conveys nothing, so a stop on it would be a stop on nothing."""
        stops = self._walk(review=True, presses=2 * len(REVIEW_RING))
        self.assertNotIn("overlay", stops)

    def test_the_sequence_cycles_rather_than_trapping(self):
        """Tabbing past the last control returns to the first.

        A keyboard trap is the failure mode that matters here: it cannot be
        seen from one pass, only from continuing past the end.
        """
        cycle = len(REVIEW_RING)
        stops = self._walk(review=True, presses=2 * cycle)
        self.assertEqual(stops[:cycle], stops[cycle:])

    def test_shift_tab_retraces_the_same_order_backwards(self):
        """Reverse traversal is the forward sequence read backwards.

        Both walks start from a freshly loaded document with nothing focused,
        so the first Shift+Tab enters at the end of the same ring rather than
        somewhere the forward walk never visited.
        """
        cycle = len(REVIEW_RING)
        forward = self._walk(review=True, presses=cycle)
        backward = self._walk(review=True, presses=cycle, key="ShiftTab")
        self.assertEqual(backward, list(reversed(forward)))

    def test_normal_mode_offers_the_business_control_alone(self):
        """Review mode adds stops; it must not be needed to reach the content."""
        stops = self._walk(review=False, presses=2)
        self.assertEqual(stops[0], "ref:home.preflight-run.action")
        self.assertNotIn("panel:select", stops)


if __name__ == "__main__":
    unittest.main()
