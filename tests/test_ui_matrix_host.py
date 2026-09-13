"""1-7-1 — the full PRD matrix, re-run through the host in a real engine.

``tests/test_ui_matrix_fixtures.py`` covers the same scenarios structurally: it
calls the renderers as pure functions and compares markup against the manifest.
That is a claim about strings. It cannot see the stylesheet, the viewport, the
review layer, or anything the engine decides, so "the matrix passes" there does
not mean the matrix passes where a reviewer stands.

This file re-runs every view × scenario over HTTP and in the engine, at both
required viewports and in both modes, and asserts what only the engine knows:
that every required unit is present *and rendered*, that no undeclared
reference appears, and that review mode adds its layer without removing a
single business unit.

One browser is reused across the scenarios of a configuration. Launching one
per scenario would multiply 27 scenarios by four configurations into a hundred
process starts; the page is re-navigated instead, which is the same isolation
for this purpose because the host keeps no state between requests.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from test_ui_matrix_fixtures import VIEWS, home_view, detail_view, record_view
from zworkbench.ui_matrix import (
    REQUIRED_VIEWPORTS,
    required_scenarios,
    required_units,
    unit_visibility,
    viewport_class,
)
from zworkbench.ui_host import serve_workbench

#: The two widths the PRD names, and the class each must resolve to. The class
#: is derived rather than written down, so a breakpoint change cannot leave this
#: table asserting the old answer.
VIEWPORTS = {
    "compact": (390, 800),
    "wide": (1280, 900),
}

ROUTES = {
    "home": "/home",
    "task-detail": "/task-detail",
    "record-view": "/record-view",
}

BUILDERS = {
    "home": home_view,
    "task-detail": detail_view,
    "record-view": record_view,
}

#: Every reference the engine actually rendered, with whether it is visible.
#: ``checkVisibility`` is the engine's own answer; a unit inside a collapsed
#: disclosure keeps a layout box in Chrome, so geometry cannot tell them apart.
RENDERED = """
JSON.stringify(Array.from(document.querySelectorAll('[data-ui-ref]')).map(node => ({
  ref: node.getAttribute('data-ui-ref'),
  visible: node.checkVisibility(),
})))
"""


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; the matrix stays structural-only",
)
class TheMatrixInARealEngineTests(unittest.TestCase):
    """Every view, every scenario, both viewports, both modes.

    The four walks -- two viewports times two modes -- are collected once for
    the class and shared. Each walk is 27 navigations, so repeating them per
    test method would spend minutes re-measuring identical pages; the walks are
    read-only observations, so sharing them costs no isolation.
    """

    matrix = None

    @classmethod
    def setUpClass(cls):
        cls._hosts = []
        cls.matrix = {
            (viewport, review): cls._walk(review=review, viewport_name=viewport)
            for viewport in REQUIRED_VIEWPORTS
            for review in (False, True)
        }

    @classmethod
    def tearDownClass(cls):
        for host in cls._hosts:
            host.close()

    @classmethod
    def _walk(cls, *, review, viewport_name):
        """Walk the whole matrix in one engine and collect what it rendered."""
        scenario = {"view": "home", "name": "no-records"}

        def view_source(route):
            view = next(v for v, r in ROUTES.items() if r == route)
            return BUILDERS[view](scenario["name"])

        host = serve_workbench(view_source=view_source, review=review)
        cls._hosts.append(host)
        observed = {}
        with browser() as engine:
            for view in VIEWS:
                for name in required_scenarios(view):
                    scenario["view"], scenario["name"] = view, name
                    engine.open(
                        host.base_url + ROUTES[view], viewport=VIEWPORTS[viewport_name]
                    )
                    observed[(view, name)] = json.loads(engine.evaluate(RENDERED))
        return observed

    def test_the_engine_lays_out_each_named_width_as_its_declared_class(self):
        """The widths are the PRD's; the classes must be the product's own."""
        host = serve_workbench(view_source=lambda route: home_view("running"))
        self.addCleanup(host.close)
        for name, (width, height) in VIEWPORTS.items():
            with self.subTest(viewport=name):
                self.assertEqual(viewport_class(width), name)
                with browser() as engine:
                    engine.open(host.base_url + "/home", viewport=(width, height))
                    measured = engine.evaluate(
                        "getComputedStyle(document.querySelector('main'))"
                        ".getPropertyValue('--viewport-class').trim()"
                    )
                self.assertEqual(measured, name)

    def test_the_walk_covered_every_view_and_scenario_the_prd_requires(self):
        """Guards the loops themselves: a short walk would quietly pass.

        Every assertion below iterates over what the walk collected, so a walk
        that skipped a view or a scenario would assert over less and still be
        green. The count is checked against the specification instead.
        """
        expected = {
            (view, scenario)
            for view in VIEWS
            for scenario in required_scenarios(view)
        }
        self.assertEqual(len(expected), 27)
        for (viewport_name, review), observed in self.matrix.items():
            with self.subTest(viewport=viewport_name, review=review):
                self.assertEqual(set(observed), expected)
                self.assertTrue(all(observed.values()))

    def test_every_always_present_unit_is_rendered_and_visible_everywhere(self):
        """A unit the specification calls visible must be visible in fact.

        Structural coverage answers "is it declared". This answers "did the
        engine put it on the page", which is the question the PRD's matrix is
        actually about.
        """
        for viewport_name in REQUIRED_VIEWPORTS:
            observed = self.matrix[(viewport_name, False)]
            for (view, scenario), nodes in observed.items():
                visible = {node["ref"] for node in nodes if node["visible"]}
                for unit in required_units(view):
                    if unit_visibility(view, unit) != "visible":
                        continue
                    with self.subTest(
                        viewport=viewport_name, view=view, scenario=scenario, unit=unit
                    ):
                        self.assertIn(unit, visible)

    def test_no_scenario_renders_a_reference_the_manifest_never_declared(self):
        """Including the review walks: the layer must not mint a reference."""
        declared = {
            view: {entry["ref"] for entry in manifest_of()["refs"]}
            for view, (manifest_of, _, _) in VIEWS.items()
        }
        for (viewport_name, review), observed in self.matrix.items():
            for (view, scenario), nodes in observed.items():
                undeclared = {
                    node["ref"] for node in nodes if node["ref"] not in declared[view]
                }
                with self.subTest(
                    viewport=viewport_name, review=review,
                    view=view, scenario=scenario,
                ):
                    self.assertEqual(undeclared, set())

    def test_review_mode_removes_no_business_unit_in_any_scenario(self):
        """The comparison the mode matrix owes, made where it can bite.

        Review mode adds an overlay, an entry and a panel. What it must never
        do is take something away -- and a scenario-by-scenario comparison in
        the engine is the only place that can be checked against what was
        actually laid out rather than against a string.
        """
        for viewport_name in REQUIRED_VIEWPORTS:
            plain = self.matrix[(viewport_name, False)]
            review = self.matrix[(viewport_name, True)]
            for key, nodes in plain.items():
                # Counted, not set-compared: review mode dropping one of three
                # identical list rows would leave the set of references intact.
                before = sorted(node["ref"] for node in nodes)
                after = sorted(node["ref"] for node in review[key])
                with self.subTest(viewport=viewport_name, case=key):
                    self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
