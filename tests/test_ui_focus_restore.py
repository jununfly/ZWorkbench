"""1-6-4 — where focus lands, visibly, when the review panel closes.

``ReviewMode.close_panel`` already decides the rule: restore the element the
reviewer came from, or fall back to the review entry when that element is gone.
``tests/test_ui_review.py`` covers that decision. What it cannot cover is the
part that matters to a keyboard user — whether focus *actually* moves there in
a real engine, and whether the result is visible rather than stranded on a
hidden element.

Visibility is asserted through ``checkVisibility()`` and the focus ring's own
condition (``:focus-visible``), not through geometry. A hidden element keeps a
layout box in Chrome, so a height comparison would pass in both directions.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_review import PANEL_ACTIONS

#: The review-mode tab ring, shared with tests/test_ui_focus_order.py: the
#: business control, the review entry, then every panel action in order.
#: The full review ring, shared with tests/test_ui_focus_order.py: the close
#: button is its last stop, so walking the whole ring lands there however
#: many business stops the page layer adds. A stale local copy of the ring
#: silently lands the walk on the wrong element.
from test_ui_focus_order import REVIEW_RING  # noqa: E402

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}

BUTTON = "home.preflight-run.action"

#: What the engine says about the focused element after the panel closes: what
#: it is, whether it is actually rendered, and whether it is inside the panel
#: that just went away.
FOCUS_REPORT = """
(() => {
  const node = document.activeElement;
  const panel = document.querySelector('[data-ui-panel="review"]');
  return JSON.stringify({
    ref: node ? node.getAttribute('data-ui-ref') : null,
    entry: !!(node && node.hasAttribute('data-ui-review-entry')),
    body: node === document.body,
    visible: !!(node && node.checkVisibility && node.checkVisibility()),
    inPanel: !!(node && panel && panel.contains(node)),
    panelClosed: panel ? panel.getAttribute('data-ui-panel-closed') : null,
  });
})()
"""


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; focus-restore-on-close stays unknown",
)
class FocusAfterClosingThePanelTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _click_action(self, engine, action):
        where = json.loads(engine.evaluate(
            "(() => {"
            "  const node = document.querySelector("
            "    '[data-ui-panel-action=\\'" + action + "\\']');"
            "  const box = node.getBoundingClientRect();"
            "  return JSON.stringify({"
            "    x: box.left + box.width / 2, y: box.top + box.height / 2});"
            "})()"
        ))
        engine.click(where["x"], where["y"])

    def _close_after(self, engine, setup=None):
        engine.open(self.host.base_url + "/home", viewport=(1280, 900))
        if setup is not None:
            engine.evaluate(setup)
        self._click_action(engine, "close")
        return json.loads(engine.evaluate(FOCUS_REPORT))

    def test_focus_returns_to_the_element_the_reviewer_came_from(self):
        with browser() as engine:
            report = self._close_after(
                engine,
                "document.querySelector('[data-ui-ref=\"{0}\"]').focus()".format(BUTTON),
            )
        self.assertEqual(report["ref"], BUTTON)
        self.assertEqual(report["panelClosed"], "restored")

    def test_the_restored_element_is_actually_rendered(self):
        """Focus on an element the engine does not render is focus nowhere."""
        with browser() as engine:
            report = self._close_after(
                engine,
                "document.querySelector('[data-ui-ref=\"{0}\"]').focus()".format(BUTTON),
            )
        self.assertTrue(report["visible"])

    def test_focus_falls_back_to_the_review_entry_when_the_target_vanished(self):
        """The element can disappear while the panel is open; focus cannot."""
        with browser() as engine:
            report = self._close_after(
                engine,
                "(() => {{"
                "  const node = document.querySelector('[data-ui-ref=\"{0}\"]');"
                "  node.focus();"
                "  node.remove();"
                "  return true;"
                "}})()".format(BUTTON),
            )
        self.assertTrue(report["entry"])
        self.assertEqual(report["panelClosed"], "fallback")
        self.assertTrue(report["visible"])

    def test_closing_without_ever_having_focused_anything_uses_the_fallback(self):
        """A reviewer who worked by mouse has no element to restore.

        On macOS clicking a button does not focus it, so ``activeElement`` is
        still the body when the panel closes. The body is not a restore target:
        handing focus to it reads as success while a keyboard user's next Tab
        starts from the top of the document.
        """
        with browser() as engine:
            report = self._close_after(engine)
        self.assertTrue(report["entry"])
        self.assertEqual(report["panelClosed"], "fallback")
        self.assertFalse(report["inPanel"])
        self.assertFalse(report["body"])
        self.assertTrue(report["visible"])

    def test_moving_between_panel_controls_does_not_become_the_restore_target(self):
        """Only focus outside the panel is remembered.

        Otherwise the last panel button the reviewer touched would become the
        element to restore, and closing would hand focus back to the panel it
        just closed.
        """
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(
                "document.querySelector('[data-ui-ref=\"{0}\"]').focus()".format(BUTTON)
            )
            self._click_action(engine, "select")
            self._click_action(engine, "lock")
            self._click_action(engine, "close")
            report = json.loads(engine.evaluate(FOCUS_REPORT))
        self.assertEqual(report["ref"], BUTTON)

    def test_a_keyboard_driven_close_leaves_a_visible_focus_ring(self):
        """Predictable focus a reviewer cannot see is not restored focus.

        ``:focus-visible`` is the engine's own answer to "should a ring be
        drawn here", which is the question -- rather than whether one happens
        to be painted under the current theme.

        The close is driven by keyboard because that is the case the ring
        exists for. After a mouse-driven close the engine deliberately draws no
        ring, and asserting one there would be asserting against the platform's
        own focus-visibility policy rather than against this product.
        """
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            for _ in range(len(REVIEW_RING)):
                engine.press("Tab")
            focused_close = engine.evaluate(
                "document.activeElement.getAttribute('data-ui-panel-action')"
            )
            engine.press("Enter")
            report = json.loads(engine.evaluate(FOCUS_REPORT))
            ring = engine.evaluate("document.activeElement.matches(':focus-visible')")
        self.assertEqual(focused_close, "close")
        # Tabbing in passes the review entry last before entering the panel, so
        # that is the element the reviewer came from and the one restored.
        self.assertTrue(report["entry"])
        self.assertEqual(report["panelClosed"], "restored")
        self.assertTrue(report["visible"])
        self.assertTrue(ring)


if __name__ == "__main__":
    unittest.main()
