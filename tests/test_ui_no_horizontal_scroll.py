"""No horizontal scroll across all three views at both acceptance viewports.

The PRD requires every page to avoid horizontal scroll at 390px and 1280px.
Coverage was previously limited to ``/home`` (see ``test_ui_home_surface.py``);
this suite extends the "no horizontal scroll" acceptance evidence to
``/task-detail`` and ``/record-view`` so the claim covers all three views, not
just the first one a reviewer happens to open.

The assertion is taken from the document element, the same geometry
``test_ui_home_surface.py`` relies on, because a page that scrolls horizontally
reports a ``scrollWidth`` larger than its ``clientWidth`` there regardless of
which view produced it.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench

#: The two widths the PRD requires.
COMPACT = (390, 800)
WIDE = (1280, 900)

#: Sparse but valid for every view: ``render_task_detail`` and
#: ``render_record_view`` tolerate the same model ``render_home`` uses (see
#: ``test_ui_style.py``), so one source can exercise all three routes. Long
#: titles stress the nowrap/ellipsis cells rather than letting them widen the
#: page.
VIEW_MODEL = {
    "records": [
        {
            "title": "为工作台建立第一条 UI seam 名称很长很长很长很长很长很长很长很长很长很长很长很长",
        },
        {"title": "补齐负向状态并回到已知边界"},
    ],
    "events": [{"title": "recorded event", "status": "completed"}],
}

ROUTES = ("/home", "/task-detail", "/record-view")


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class NoHorizontalScrollAcrossViewsTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(self.host.close)

    def _overflow(self, route, viewport):
        with browser() as engine:
            engine.open(self.host.base_url + route, viewport=viewport)
            return json.loads(
                engine.evaluate(
                    "JSON.stringify({"
                    "clientWidth: document.documentElement.clientWidth,"
                    "scrollWidth: document.documentElement.scrollWidth"
                    "})"
                )
            )

    def test_wide_view_has_no_horizontal_scroll(self):
        for route in ROUTES:
            with self.subTest(route=route):
                measured = self._overflow(route, WIDE)
                self.assertLessEqual(measured["scrollWidth"], measured["clientWidth"])

    def test_compact_view_has_no_horizontal_scroll(self):
        for route in ROUTES:
            with self.subTest(route=route):
                measured = self._overflow(route, COMPACT)
                self.assertLessEqual(measured["scrollWidth"], measured["clientWidth"])


if __name__ == "__main__":
    unittest.main()
