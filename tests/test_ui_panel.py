"""Behaviour tests for the review panel in a served document.

The seam under test is the served review document. The panel's decisions were
already settled as a state machine in tests/test_ui_review.py -- which entries
exist, what locking means, when a copy is refused -- and none of that is
retested here. What is new is that those decisions reach a real DOM with the
semantics an assistive technology needs.

The panel is a region with content, so unlike the highlight layer it is not
role="presentation" and it does accept input. Two things are asserted that a
state machine could not: that every keyboard-reachable action is present as a
real focusable control, and that each entry names the manifest identity it was
rendered against.

Native tab order remains a host unknown (1-6-1). Rendering focusable controls
in document order is necessary for it, not evidence of it.
"""

import json
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_review import PANEL_ACTIONS

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}


def fetch(base, path="/home"):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.read().decode("utf-8")


class RenderingThePanelTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)
        self.document = fetch(self.host.base_url)

    def test_the_panel_is_present_in_review_mode(self):
        self.assertIn('data-ui-panel="review"', self.document)

    def test_the_panel_names_the_manifest_identity_it_was_rendered_against(self):
        """A reviewer must be able to tell whether they share a build."""
        manifest = home_manifest()
        self.assertIn(manifest["ui_map"][:12], self.document)
        self.assertIn(manifest["build"][:12], self.document)

    def test_every_panel_action_is_present_as_a_control(self):
        for action in PANEL_ACTIONS:
            with self.subTest(action=action):
                self.assertIn('data-ui-panel-action="{0}"'.format(action), self.document)

    def test_the_panel_lists_the_declared_references_it_can_target(self):
        self.assertIn("home.record-list.item", self.document)


class CarryingAccessibilitySemanticsTests(unittest.TestCase):
    """1-4-5 -- markup semantics, kept separate from focus order (1-6-1)."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)
        self.document = fetch(self.host.base_url)

    def test_the_panel_is_a_labelled_region(self):
        self.assertIn('role="region"', self.document)
        self.assertIn("aria-label", self.document)

    def test_the_highlight_layer_is_presentational_but_the_panel_is_not(self):
        """The highlight conveys nothing; the panel conveys the references."""
        overlay = self.document[self.document.index("<aside"):]
        self.assertIn('role="presentation"', overlay)
        panel = self.document[self.document.index('data-ui-panel="review"'):]
        self.assertNotIn('role="presentation"', panel)


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class ThePanelInARealEngineTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _probe(self, expression):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            return json.loads(engine.evaluate(expression))

    def test_every_panel_action_is_a_focusable_control(self):
        """Reachability without a pointer starts with being focusable at all."""
        focusable = self._probe(
            "JSON.stringify(Array.from("
            "document.querySelectorAll('[data-ui-panel-action]')"
            ").map(node => ({"
            "  action: node.getAttribute('data-ui-panel-action'),"
            "  tag: node.tagName,"
            "  disabled: node.disabled === true,"
            "})))"
        )
        self.assertEqual(
            sorted(item["action"] for item in focusable), sorted(PANEL_ACTIONS)
        )
        for item in focusable:
            with self.subTest(action=item["action"]):
                self.assertEqual(item["tag"], "BUTTON")
                self.assertFalse(item["disabled"])

    def test_the_panel_accepts_input_although_the_highlight_does_not(self):
        computed = self._probe(
            "JSON.stringify({"
            "  panel: getComputedStyle("
            "    document.querySelector('[data-ui-panel]')).pointerEvents,"
            "  overlay: getComputedStyle("
            "    document.querySelector('[data-ui-overlay]')).pointerEvents,"
            "})"
        )
        self.assertEqual(computed["overlay"], "none")
        self.assertEqual(computed["panel"], "auto")

    def test_the_panel_does_not_hide_the_business_element_it_lists(self):
        """A panel that covers the content would defeat its own purpose."""
        hit = self._probe(
            "(() => {"
            "  const button = document.querySelector("
            "    '[data-ui-ref=\\'home.preflight-run.action\\']');"
            "  const box = button.getBoundingClientRect();"
            "  const node = document.elementFromPoint("
            "    box.left + box.width / 2, box.top + box.height / 2);"
            "  return JSON.stringify({"
            "    ref: node ? node.getAttribute('data-ui-ref') : null});"
            "})()"
        )
        self.assertEqual(hit["ref"], "home.preflight-run.action")


if __name__ == "__main__":
    unittest.main()
