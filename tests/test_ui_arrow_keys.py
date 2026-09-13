"""ArrowUp/ArrowDown point at *any* declared element.

The first cut of the arrow keys walked the panel's entry list, which only
ever contains mounted references -- on the home view, the record rows. Every
other declared unit (sections, the list itself, the action) was unreachable
by arrow: exactly the gap a keyboard reviewer hits first, because they have
no hover.

The arrows now move focus across every ``[data-ui-ref]`` in document order --
the same ring Tab walks. Focus shows the preview, Ctrl+C copies the pointed
element, and the panel's own select/lock remains for what only the panel
does: retaining one entry as the annotation target.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}, {"title": "run-three"}]}

#: The ring the arrows walk, in document order. Derived from the served page
#: rather than written out: a view that gains a unit gains a stop, and a test
#: that listed stops by hand would silently keep passing on the old length.
RING = (
    "JSON.stringify(Array.from(document.querySelectorAll('[data-ui-ref]'))"
    ".map(node => node.getAttribute('data-ui-ref')))"
)


def focused_ref(engine):
    node = engine.evaluate(
        "document.activeElement ? document.activeElement.getAttribute('data-ui-ref') : null"
    )
    return node


def badge_name(engine):
    return engine.evaluate(
        "(() => {"
        "  const badge = document.querySelector('[data-ui-preview-badge]');"
        "  return badge ? badge.textContent : null;"
        "})()"
    )


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class ArrowKeysPointAtEveryDeclaredElementTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_arrow_down_walks_every_declared_element_in_document_order(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            ring = json.loads(engine.evaluate(RING))
            walked = []
            for _ in range(len(ring)):
                engine.press("ArrowDown")
                walked.append(focused_ref(engine))
            self.assertEqual(walked, ring)

    def test_arrow_up_walks_the_same_ring_backwards(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.press("ArrowDown")
            engine.press("ArrowDown")
            forward = focused_ref(engine)
            engine.press("ArrowUp")
            self.assertNotEqual(focused_ref(engine), forward)

    def test_the_walk_wraps_around_the_ring(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            ring = json.loads(engine.evaluate(RING))
            engine.press("ArrowUp")  # from nowhere: wraps to the last element
            self.assertEqual(focused_ref(engine), ring[-1])
            engine.press("ArrowDown")
            self.assertEqual(focused_ref(engine), ring[0])

    def test_static_units_are_reachable_and_named(self):
        """The gap this fixed: sections are text, not controls."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.press("ArrowDown")
            engine.press("ArrowDown")  # root, then workspace-context
            self.assertEqual(focused_ref(engine), "home.workspace-context")
            self.assertEqual(badge_name(engine), "工作区与模式上下文")

    def test_arrows_from_inside_the_panel_resume_from_the_business_anchor(self):
        """Focus in the panel does not strand the walk: the anchor is the
        element the reviewer was on before the panel, and the arrow moves on
        from there -- focus leaves the panel, because the pointing is about
        the page."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            ring = json.loads(engine.evaluate(RING))
            engine.press("ArrowDown")
            anchor = focused_ref(engine)
            # Into the panel, then arrow again.
            engine.evaluate(
                "document.querySelector('[data-ui-panel-action]').focus()"
            )
            engine.press("ArrowDown")
            expected = ring[(ring.index(anchor) + 1) % len(ring)]
            self.assertEqual(focused_ref(engine), expected)

    def test_the_panel_select_still_locks_entries(self):
        """Locking one entry as the annotation target stays a panel act."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            where = json.loads(engine.evaluate(
                "(() => {"
                "  const node = document.querySelector("
                "    '[data-ui-panel-action=\\'select\\']');"
                "  const box = node.getBoundingClientRect();"
                "  return JSON.stringify({"
                "    x: box.left + box.width / 2, y: box.top + box.height / 2});"
                "})()"
            ))
            engine.click(where["x"], where["y"])
            locked = engine.evaluate(
                "document.querySelectorAll('[data-ui-panel-locked]').length"
            )
            self.assertEqual(locked, 1)


if __name__ == "__main__":
    unittest.main()
