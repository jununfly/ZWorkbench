"""1-6-2 — a real click reaches the business element through the review layer.

``tests/test_ui_overlay.py`` establishes the two static halves of this: the
engine computes ``pointer-events: none`` on the highlight layer, and hit
testing at a button's own coordinates still answers with that button. Neither
is a click. Hit testing asks the layout engine a question; input delivery is a
separate path, and a layer can be transparent to ``elementFromPoint`` while
still consuming a dispatched event.

So the assertion here is made on the event: a real mouse press is dispatched at
the business button's coordinates while the overlay covers them, and the page
reports which element the engine delivered it to, and how many times.

Counting matters as much as targeting. A layer that both passes a click through
and handles it would deliver the business action twice, and a test that only
looked at the target would call that a pass.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}

BUTTON = "home.preflight-run.action"

#: Records every click the document sees, at the document level, so an event
#: handled and stopped by an intermediate layer is still counted where it was
#: delivered rather than silently missing.
RECORDER = (
    "(() => {"
    "  window.__clicks = [];"
    "  document.addEventListener('click', event => {"
    "    const node = event.target;"
    "    window.__clicks.push({"
    "      ref: node.getAttribute && node.getAttribute('data-ui-ref'),"
    "      overlay: !!(node.closest && node.closest('[data-ui-overlay]')),"
    "      panel: node.getAttribute && node.getAttribute('data-ui-panel-action'),"
    "    });"
    "  }, true);"
    "  return true;"
    "})()"
)

#: Where a reference's element sits, and whether the review layer covers it.
#: Coverage is asserted alongside the click because passthrough through a layer
#: that covers nothing is vacuously true.
CENTRE = """
(() => {
  const node = document.querySelector('[data-ui-ref="__REF__"]');
  const box = node.getBoundingClientRect();
  const overlay = document.querySelector('[data-ui-overlay]');
  const area = overlay ? overlay.getBoundingClientRect() : null;
  return JSON.stringify({
    x: box.left + box.width / 2,
    y: box.top + box.height / 2,
    covered: !!area && area.width > 0 && area.height > 0
      && box.left >= area.left && box.right <= area.right
      && box.top >= area.top && box.bottom <= area.bottom,
  });
})()
"""

#: Where a panel control sits. Kept separate from CENTRE because panel controls
#: are addressed by action, not by semantic reference.
PANEL_CENTRE = """
(() => {
  const node = document.querySelector('[data-ui-panel-action="__ACTION__"]');
  const box = node.getBoundingClientRect();
  return JSON.stringify({
    x: box.left + box.width / 2, y: box.top + box.height / 2});
})()
"""


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; pointer-events-passthrough stays unknown",
)
class ClickingThroughTheReviewLayerTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _click_business_button(self, engine):
        engine.open(self.host.base_url + "/home", viewport=(1280, 900))
        engine.evaluate(RECORDER)
        where = json.loads(engine.evaluate(CENTRE.replace("__REF__", BUTTON)))
        engine.click(where["x"], where["y"])
        return where, json.loads(engine.evaluate("JSON.stringify(window.__clicks)"))

    def test_the_click_is_delivered_to_the_business_element(self):
        with browser() as engine:
            where, clicks = self._click_business_button(engine)
        self.assertTrue(where["covered"], "the overlay does not cover the target")
        self.assertEqual([click["ref"] for click in clicks], [BUTTON])

    def test_the_review_layer_is_never_the_target_of_that_click(self):
        with browser() as engine:
            _, clicks = self._click_business_button(engine)
        self.assertEqual([click for click in clicks if click["overlay"]], [])

    def test_the_click_is_delivered_exactly_once(self):
        """Passthrough that also handles the event would double the action."""
        with browser() as engine:
            _, clicks = self._click_business_button(engine)
        self.assertEqual(len(clicks), 1)

    def test_a_click_on_a_panel_control_stays_in_the_panel(self):
        """The converse: passthrough is directional.

        A layer that let every click fall through, including the clicks on its
        own controls, would be unusable rather than transparent. The panel must
        receive its own click and no business reference may see it.
        """
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(RECORDER)
            where = json.loads(
                engine.evaluate(PANEL_CENTRE.replace("__ACTION__", "lock"))
            )
            engine.click(where["x"], where["y"])
            clicks = json.loads(engine.evaluate(
                "JSON.stringify(window.__clicks.map(click => ({"
                "  ref: click.ref, panel: click.panel})))"
            ))
        self.assertEqual([click["panel"] for click in clicks], ["lock"])
        self.assertEqual([click["ref"] for click in clicks], [None])


if __name__ == "__main__":
    unittest.main()
