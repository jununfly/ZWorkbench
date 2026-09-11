"""Behaviour tests for the two required viewports in a real engine.

The seam under test is the served page as an engine lays it out: computed style
and geometry at 390px and 1280px. Markup is deliberately *not* compared between
the two, because it is the same markup -- responsive behaviour belongs to CSS,
and the view model does not vary by viewport.

That is the property worth protecting rather than an accident of the design. If
the presentation model changed with the viewport, responsive layout would have
moved into the data layer and would start applying pressure to rename
references, which the PRD forbids: visual rearrangement must leave a ref
untouched.

The suite this replaces looped over viewport names without using them, so its
2x2 appearance was arithmetic over the loop counter rather than evidence.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_matrix import VIEWPORT_BREAKPOINT_PX, viewport_class

#: The two widths the PRD requires, either side of its 768px breakpoint.
COMPACT = (390, 800)
WIDE = (1280, 900)

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}


class ClassifyingAViewportTests(unittest.TestCase):
    """The token's viewport field must mean what the PRD says it means."""

    def test_the_breakpoint_is_the_one_the_prd_states(self):
        self.assertEqual(VIEWPORT_BREAKPOINT_PX, 768)

    def test_a_width_below_the_breakpoint_is_compact(self):
        self.assertEqual(viewport_class(390), "compact")

    def test_a_width_at_the_breakpoint_is_wide(self):
        """"At least 768px" makes the boundary inclusive on the wide side."""
        self.assertEqual(viewport_class(768), "wide")

    def test_a_width_above_the_breakpoint_is_wide(self):
        self.assertEqual(viewport_class(1280), "wide")


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class LayingOutTheSameMarkupAtBothViewportsTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(self.host.close)

    def _measure(self, viewport):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=viewport)
            return json.loads(
                engine.evaluate(
                    "JSON.stringify({"
                    "  width: document.documentElement.clientWidth,"
                    "  klass: getComputedStyle(document.querySelector('main'))"
                    "    .getPropertyValue('--viewport-class').trim(),"
                    "  padding: getComputedStyle(document.querySelector('main'))"
                    "    .paddingLeft,"
                    "  refs: Array.from("
                    "    document.querySelectorAll('[data-ui-ref]')"
                    "  ).map(n => n.getAttribute('data-ui-ref')).sort()"
                    "})"
                )
            )

    def test_the_engine_reports_the_width_that_was_requested(self):
        """Without this the rest could be measuring the fallback viewport."""
        self.assertEqual(self._measure(COMPACT)["width"], COMPACT[0])
        self.assertEqual(self._measure(WIDE)["width"], WIDE[0])

    def test_the_stylesheet_distinguishes_the_two_viewports(self):
        self.assertEqual(self._measure(COMPACT)["klass"], "compact")
        self.assertEqual(self._measure(WIDE)["klass"], "wide")

    def test_the_two_viewports_lay_out_differently(self):
        """A measurable difference, so the CSS is not merely declaring one."""
        self.assertNotEqual(
            self._measure(COMPACT)["padding"], self._measure(WIDE)["padding"]
        )

    def test_every_declared_reference_survives_the_viewport_change(self):
        """Visual rearrangement must not move a semantic identity."""
        compact = self._measure(COMPACT)["refs"]
        wide = self._measure(WIDE)["refs"]
        self.assertEqual(compact, wide)
        self.assertTrue(set(compact) <= {e["ref"] for e in home_manifest()["refs"]})


if __name__ == "__main__":
    unittest.main()
