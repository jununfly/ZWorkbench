"""Behaviour tests for the review overlay as an engine sees it.

The seam under test is the served document: the host is started in review mode
and the result is observed over HTTP and in a real engine.

ReviewMode already decided everything about panels, gestures and exit; that is
tested as a state machine in tests/test_ui_review.py. What could not be settled
there is whether an engine honours the layer's contract, so the assertions here
are the ones a state machine cannot make: computed pointer-events, hit testing,
and the fact that the business markup is untouched.

Review mode is a host start-up choice, never a URL parameter. tests/
test_ui_deep_link.py asserts that a link cannot turn review on; keeping the
switch out of the request makes that structural rather than a whitelist
omission.
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

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}


def fetch(base, path="/home"):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.read().decode("utf-8")


class RenderingTheOverlayTests(unittest.TestCase):
    def setUp(self):
        self.plain = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(self.plain.close)
        self.review = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.review.close)

    def test_review_mode_adds_an_overlay_layer(self):
        self.assertIn('data-ui-overlay', fetch(self.review.base_url))

    def test_normal_mode_has_no_overlay(self):
        self.assertNotIn("data-ui-overlay", fetch(self.plain.base_url))

    def test_the_overlay_declares_itself_transparent_to_input(self):
        self.assertIn("pointer-events", fetch(self.review.base_url))

    def test_the_business_markup_is_untouched_by_review_mode(self):
        """1-4-3: the difference between the modes is the review layer, exactly.

        Removing the review subtrees from the review document must yield the
        normal document byte for byte. This is the assertion the old mode
        comparison could not make, because there was nothing to subtract.

        Every review addition is removed by locating its boundaries rather than
        by assuming there is one. An earlier version subtracted only the
        overlay and passed; adding the panel turned it red, and adding the
        review entry and behaviour layer turned it red again. That is the
        behaviour a subtraction test should have: each new review-mode part
        must be named here before the comparison can pass.
        """
        review = fetch(self.review.base_url)
        stripped = review
        for opening, closing in (
            ("<aside", "</aside>"),
            ("<button type=\"button\" data-ui-review-entry", "</button>"),
            ("<section data-ui-panel", "</section>"),
            ("<script", "</script>"),
        ):
            start = stripped.index(opening)
            end = stripped.index(closing, start) + len(closing)
            stripped = stripped[:start] + stripped[end:]
        self.assertEqual(stripped, fetch(self.plain.base_url))


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class TheOverlayInARealEngineTests(unittest.TestCase):
    """A state machine can declare pointer-events: none; only an engine honours it."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_the_engine_computes_the_overlay_as_transparent_to_input(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            computed = engine.evaluate(
                "getComputedStyle(document.querySelector('[data-ui-overlay]'))"
                ".pointerEvents"
            )
        self.assertEqual(computed, "none")

    def test_the_overlay_covers_the_page_without_intercepting_a_click(self):
        """Hit testing is the only honest form of this assertion.

        The overlay must sit over the content -- otherwise passthrough is
        vacuous, since a layer covering nothing intercepts nothing -- and the
        element found at a business element's own coordinates must still be
        that element.
        """
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            report = json.loads(engine.evaluate(
                "(() => {"
                "  const overlay = document.querySelector('[data-ui-overlay]');"
                "  const button = document.querySelector("
                "    '[data-ui-ref=\\'home.preflight-run.action\\']');"
                "  const box = button.getBoundingClientRect();"
                "  const x = box.left + box.width / 2;"
                "  const y = box.top + box.height / 2;"
                "  const overlayBox = overlay.getBoundingClientRect();"
                "  const hit = document.elementFromPoint(x, y);"
                "  return JSON.stringify({"
                "    covers: overlayBox.width > 0 && overlayBox.height > 0"
                "      && x >= overlayBox.left && x <= overlayBox.right"
                "      && y >= overlayBox.top && y <= overlayBox.bottom,"
                "    hit: hit ? hit.getAttribute('data-ui-ref') : null,"
                "  });"
                "})()"
            ))
        self.assertTrue(report["covers"], "the overlay does not cover the target")
        self.assertEqual(report["hit"], "home.preflight-run.action")

    def test_every_declared_reference_still_renders_in_review_mode(self):
        declared = {entry["ref"] for entry in home_manifest()["refs"]}
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            rendered = set(json.loads(engine.evaluate(
                "JSON.stringify(Array.from("
                "document.querySelectorAll('main [data-ui-ref]')"
                ").map(n => n.getAttribute('data-ui-ref')))"
            )))
        self.assertEqual(rendered - declared, set())


if __name__ == "__main__":
    unittest.main()
