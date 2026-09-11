"""Behaviour tests for the style layer coexisting with the reference protocol.

The seam under test is the host's HTTP contract plus the resulting DOM in a
real engine. Two things are deliberately *not* asserted: the text of the
stylesheet (that would freeze authoring choices into a test) and any private
helper of the renderers.

The load-bearing rule here is that styling must never key off ``data-ui-ref``.
A reference is a semantic identity with a lifecycle: the PRD requires that
visual rearrangement leaves a ref untouched. If a selector depended on a ref,
restyling would create pressure to rename it, and the lifecycle guarantee would
decay into a naming convention nobody can honour.
"""

import json
import re
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_host import STYLESHEET_ROUTE, serve_workbench
from zworkbench.ui_record_view import record_manifest, render_record_view
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_task_detail import render_task_detail, task_detail_manifest

#: Route -> (manifest factory, the bare renderer that owes no styling).
VIEWS = (
    ("/home", home_manifest, render_home),
    ("/task-detail", task_detail_manifest, render_task_detail),
    ("/record-view", record_manifest, render_record_view),
)

#: A view model with content, so the comparison covers repeated instances of a
#: list item rather than only the always-present singletons.
VIEW_MODEL = {"records": [{"title": "a"}, {"title": "b"}], "events": [{"title": "e"}]}

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.headers, response.read().decode("utf-8")


class ServingTheStyleLayerTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_the_stylesheet_is_served_as_css(self):
        status, headers, body = fetch(self.host.base_url, STYLESHEET_ROUTE)
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/css"))
        self.assertIn("{", body)

    def test_every_view_links_the_stylesheet(self):
        for route, _, _ in VIEWS:
            with self.subTest(route=route):
                _, _, body = fetch(self.host.base_url, route)
                self.assertIn('rel="stylesheet"', body)
                self.assertIn(STYLESHEET_ROUTE, body)


class StylingDoesNotKeyOffReferencesTests(unittest.TestCase):
    """A ref is a semantic identity, not a styling hook."""

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)
        _, _, self.css = fetch(self.host.base_url, STYLESHEET_ROUTE)

    def test_no_selector_targets_a_reference_attribute(self):
        self.assertEqual(re.findall(r"\[data-ui-ref[^\]]*\]", self.css), [])

    def test_the_stylesheet_names_no_declared_reference(self):
        declared = set()
        for _, manifest_of, _ in VIEWS:
            declared.update(entry["ref"] for entry in manifest_of()["refs"])
        named = sorted(ref for ref in declared if ref in self.css)
        self.assertEqual(named, [])

    def test_the_styled_document_carries_the_same_references_as_the_bare_view(self):
        """The independent source of truth is the unstyled renderer's output.

        Comparing the served document against the bare renderer catches a
        style layer that adds, drops or duplicates a reference. Asserting
        ``undeclared == ()`` alone would not: dropping every reference also
        satisfies it.
        """
        host = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(host.close)
        for route, manifest_of, render in VIEWS:
            with self.subTest(route=route):
                manifest = manifest_of()
                _, _, served = fetch(host.base_url, route)
                bare = render(VIEW_MODEL, manifest=manifest)
                self.assertEqual(
                    audit_rendered_html(manifest, served)["instances"],
                    audit_rendered_html(manifest, bare)["instances"],
                )

    def test_serving_the_style_layer_adds_no_undeclared_reference(self):
        for route, manifest_of, _ in VIEWS:
            with self.subTest(route=route):
                _, _, body = fetch(self.host.base_url, route)
                self.assertEqual(audit_rendered_html(manifest_of(), body)["undeclared"], ())


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class TheStyleLayerInARealEngineTests(unittest.TestCase):
    """String inspection cannot tell an applied stylesheet from a dead one."""

    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(self.host.close)

    def test_the_stylesheet_actually_applies(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            layout = engine.evaluate(
                "getComputedStyle(document.querySelector('main')).flexDirection"
            )
        self.assertEqual(layout, "column")

    def test_styled_elements_keep_the_reference_the_manifest_declares(self):
        """Read the refs back out of the live DOM, after styling applied."""
        declared = {entry["ref"] for entry in home_manifest()["refs"]}
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self.assertEqual(
                engine.evaluate(
                    "getComputedStyle(document.querySelector('main')).flexDirection"
                ),
                "column",
            )
            live = engine.evaluate(
                "JSON.stringify(Array.from("
                "document.querySelectorAll('[data-ui-ref]')"
                ").map(node => node.getAttribute('data-ui-ref')))"
            )
        rendered = set(json.loads(live))
        self.assertEqual(rendered - declared, set())
        self.assertIn("home.record-list.item", rendered)

    def test_no_style_rule_matches_on_a_reference_attribute(self):
        """Ask the engine which rules matched, not the stylesheet text.

        A selector could reach a ref through a form the source scan misses.
        The engine's own view of the matched rules is the independent check.
        """
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            selectors = engine.evaluate(
                "JSON.stringify(Array.from(document.styleSheets)"
                ".flatMap(sheet => Array.from(sheet.cssRules))"
                ".map(rule => rule.selectorText).filter(Boolean))"
            )
        offenders = [s for s in json.loads(selectors) if "data-ui-ref" in s]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
