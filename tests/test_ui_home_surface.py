"""Product-surface checks for the first visible Workbench home slice.

The protocol tests prove that references survive rendering.  These checks keep
the first visual shell honest as well: it must expose the information
architecture from the PRD, retain explicit status/source language, and fit the
two acceptance viewports without introducing horizontal scroll.
"""

import json
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_runtime import audit_rendered_html


VIEW = {
    "workspace": {
        "name": "ZWorkbench case-local",
        "mode": "local_read_only",
        "status": "implemented",
    },
    "records": [
        {
            "title": "为工作台建立第一条 UI seam",
            "run_id": "run-home-01",
            "status": "running",
            "updated_at": "刚刚",
        },
    ],
    "state": "running",
    "run_facts": {
        "status": "running",
        "run_id": "run-home-01",
        "parent_child": "unknown",
        "workspace": "case-local",
        "provider": "fake-loopback",
        "evidence": "owner snapshot",
        "source": "CompositionOwner",
    },
    "intent": {
        "title": "为工作台建立第一条 UI seam",
        "summary": "先把已记录事实放进一个可读、可定位、不会伪造执行能力的首页。",
        "status": "running",
        "source": "Owner / recorded input",
    },
    "plan": {
        "steps": [
            {"title": "完成首页视觉壳", "status": "completed"},
            {"title": "补齐负向状态", "status": "running"},
        ]
    },
    "artifacts": [{"title": "ui_home.py", "description": "server-rendered view"}],
    "evidence": [{"title": "owner snapshot", "description": "read-only source"}],
    "preflight_result": {"status": "ready", "source": "local preflight"},
}


class HomeSurfaceMarkupTests(unittest.TestCase):
    def test_planning_surface_keeps_information_architecture_and_sources_visible(self):
        markup = render_home(VIEW)
        self.assertIn("为工作台建立第一条 UI seam", markup)
        self.assertIn("WORK RECORDS", markup)
        self.assertIn("RUNTIME FACTS", markup)
        self.assertIn("CompositionOwner", markup)
        self.assertIn("来源：CompositionOwner", markup)
        self.assertIn('aria-disabled="true"', markup)
        self.assertIn("不会从页面启动 Run", markup)

        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())
        self.assertEqual(audit["instances"]["home.record-list.item"], 1)

    def test_unknown_run_facts_are_not_relabelled_as_success(self):
        view = dict(VIEW)
        view["run_facts"] = {"status": "unknown", "source": "missing identity"}
        markup = render_home(view)
        self.assertIn('data-status="unknown"', markup)
        self.assertIn("来源：missing identity", markup)
        self.assertNotIn('data-status="completed"', markup)

    def test_missing_workspace_context_stays_unknown(self):
        markup = render_home({"workspace": "unknown", "run_facts": {"status": "unknown"}})
        self.assertIn('class="scope-tag scope-unknown"', markup)
        self.assertIn("source unknown", markup)
        self.assertNotIn("owner-backed", markup)


@unittest.skipUnless(chrome_available(), "the verification-stage browser is absent")
class HomeSurfaceBrowserTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW)
        self.addCleanup(self.host.close)

    def _measure(self, viewport):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=viewport)
            return json.loads(
                engine.evaluate(
                    "JSON.stringify({"
                    "pageWidth: document.documentElement.clientWidth,"
                    "scrollWidth: document.documentElement.scrollWidth,"
                    "layout: getComputedStyle(document.querySelector('.home-layout')).display,"
                    "columns: getComputedStyle(document.querySelector('.home-layout')).gridTemplateColumns,"
                    "layoutWidth: document.querySelector('.home-layout').getBoundingClientRect().width,"
                    "sidebar: document.querySelector('.home-records').getBoundingClientRect().width,"
                    "content: document.querySelector('.home-content').getBoundingClientRect().width,"
                    "inspector: document.querySelector('.home-inspector').getBoundingClientRect().width"
                    "})"
                )
            )

    def test_wide_view_is_a_three_column_workbench(self):
        measured = self._measure((1280, 900))
        self.assertEqual(measured["layout"], "grid")
        self.assertEqual(measured["sidebar"], 236)
        self.assertEqual(measured["inspector"], 318)
        self.assertGreater(measured["content"], 460)
        self.assertLessEqual(measured["scrollWidth"], measured["pageWidth"])

    def test_compact_view_stacks_all_required_information_without_horizontal_scroll(self):
        measured = self._measure((390, 800))
        self.assertEqual(measured["layout"], "grid")
        self.assertEqual(measured["columns"], "{0}px".format(measured["layoutWidth"]))
        self.assertEqual(measured["sidebar"], measured["layoutWidth"])
        self.assertEqual(measured["inspector"], measured["layoutWidth"])
        self.assertLessEqual(measured["scrollWidth"], measured["pageWidth"])


if __name__ == "__main__":
    unittest.main()
