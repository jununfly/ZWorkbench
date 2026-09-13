"""The review layer must be *visible*, not merely present.

1-4 through 1-7 proved the overlay, panel and deep-link marker exist in the
served document and behave. None of that is what a reviewer experiences: an
unstyled panel reads as leftover markup at the bottom of the page, and a
marker attribute no rule styles highlights nothing. The PRD's promise -- 悬停
或选择时看到边框、中文语义名和稳定引用 -- is a visible affordance, so it is
asserted where visibility is decided: in the engine, with real mouse moves.
"""

import json
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_token import build_deep_link

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}


def center_of(engine, selector):
    box = json.loads(engine.evaluate(
        "(() => {"
        "  const node = document.querySelector('" + selector + "');"
        "  if (!node) return 'null';"
        "  const rect = node.getBoundingClientRect();"
        "  return JSON.stringify({"
        "    x: rect.left + rect.width / 2, y: rect.top + rect.height / 2});"
        "})()"
    ))
    assert box is not None, "no element matches " + selector
    return box


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class ThePanelIsAVisibleSideRegionTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_the_panel_is_a_fixed_side_region_not_leftover_markup(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            probe = json.loads(engine.evaluate(
                "JSON.stringify((() => {"
                "  const panel = document.querySelector('[data-ui-panel]');"
                "  const style = getComputedStyle(panel);"
                "  return {position: style.position, right: style.right,"
                "    visible: panel.checkVisibility()};"
                "})())"
            ))
            self.assertEqual(probe["position"], "fixed")
            self.assertEqual(probe["right"], "0px")
            self.assertTrue(probe["visible"])


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class HoverPreviewTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _preview(self, engine):
        return json.loads(engine.evaluate(
            "JSON.stringify((() => {"
            "  const box = document.querySelector('[data-ui-preview-box]');"
            "  if (!box) return {present: false};"
            "  const badge = box.querySelector('[data-ui-preview-badge]');"
            "  return {present: true, visible: box.checkVisibility(),"
            "    name: badge ? badge.textContent : null,"
            "    inOverlay: !!box.closest('[data-ui-overlay]')};"
            "})())"
        ))

    def test_hovering_an_element_shows_its_semantic_name_in_the_overlay(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            where = center_of(engine, '[data-ui-ref="home.record-list.item"]')
            engine.move(where["x"], where["y"])
            preview = self._preview(engine)
            self.assertTrue(preview["present"])
            self.assertTrue(preview["visible"])
            self.assertTrue(preview["inOverlay"])
            self.assertEqual(preview["name"], "工作记录项")

    def test_previewing_never_selects(self):
        """Hover is a preview gesture; the lock stays empty."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            where = center_of(engine, '[data-ui-ref="home.record-list.item"]')
            engine.move(where["x"], where["y"])
            locked = engine.evaluate(
                "document.querySelectorAll('[data-ui-panel-locked]').length"
            )
            self.assertEqual(locked, 0)

    def test_moving_to_another_element_replaces_the_preview(self):
        """One preview at a time, naming whatever is hovered now. The page
        root is itself a declared unit, so there is no spot on the page that
        previews nothing -- hovering elsewhere must replace, not stack."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            where = center_of(engine, '[data-ui-ref="home.record-list.item"]')
            engine.move(where["x"], where["y"])
            self.assertEqual(self._preview(engine)["name"], "工作记录项")
            where = center_of(engine, '[data-ui-ref="home.preflight-run.action"]')
            engine.move(where["x"], where["y"])
            boxes = engine.evaluate(
                "document.querySelectorAll('[data-ui-preview-box]').length"
            )
            self.assertEqual(boxes, 1)
            self.assertEqual(self._preview(engine)["name"], "预检并运行")


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class FocusIsAPreviewGestureTests(unittest.TestCase):
    """Keyboard pointing: focus shows the same preview hover does."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_tabbing_to_an_element_names_it(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            # Walk to the first record item: root, workspace, facts, list, item.
            for _ in range(5):
                engine.press("Tab")
            focused = engine.evaluate(
                "document.activeElement.getAttribute('data-ui-ref')"
            )
            self.assertEqual(focused, "home.record-list.item")
            preview = json.loads(engine.evaluate(
                "JSON.stringify((() => {"
                "  const badge = document.querySelector('[data-ui-preview-badge]');"
                "  return badge ? {name: badge.textContent} : {name: null};"
                "})())"
            ))
            self.assertEqual(preview["name"], "工作记录项")
            # Focusing never locks: preview is not selection.
            self.assertEqual(
                engine.evaluate(
                    "document.querySelectorAll('[data-ui-panel-locked]').length"
                ),
                0,
            )


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class ThePageRootPreviewStaysVisibleTests(unittest.TestCase):
    """The root unit's box touches the viewport top; its name badge must not
    float off-screen, or hovering the page's own gaps reads as no effect."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_the_root_preview_badge_stays_inside_the_viewport(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            # A gap between sections belongs to main (home.root), not to any
            # smaller unit.
            gap = json.loads(engine.evaluate(
                "(() => {"
                "  const a = document.querySelector("
                "    '[data-ui-ref=\"home.workspace-context\"]');"
                "  const b = document.querySelector("
                "    '[data-ui-ref=\"home.run-facts\"]');"
                "  const ra = a.getBoundingClientRect();"
                "  const rb = b.getBoundingClientRect();"
                "  return JSON.stringify({"
                "    x: ra.left + ra.width / 2,"
                "    y: (ra.bottom + rb.top) / 2});"
                "})()"
            ))
            engine.move(gap["x"], gap["y"])
            preview = json.loads(engine.evaluate(
                "JSON.stringify((() => {"
                "  const badge = document.querySelector('[data-ui-preview-badge]');"
                "  if (!badge) return {present: false};"
                "  const rect = badge.getBoundingClientRect();"
                "  return {present: true, name: badge.textContent,"
                "    top: rect.top, visible: badge.checkVisibility()};"
                "})())"
            ))
            self.assertTrue(preview["present"])
            self.assertEqual(preview["name"], "工作台首页")
            self.assertTrue(preview["visible"])
            self.assertGreaterEqual(preview["top"], 0)


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class ThePanelIsDockedNotOverlaidTests(unittest.TestCase):
    """A panel that covers business elements defeats its own purpose: the
    reviewer cannot see, hover or click what the panel hides. The page makes
    room instead -- and takes the room back when the panel closes."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_no_business_element_sits_under_the_panel(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            overlap = json.loads(engine.evaluate(
                "JSON.stringify((() => {"
                "  const panel = document.querySelector('[data-ui-panel]')"
                "    .getBoundingClientRect();"
                "  return Array.from(document.querySelectorAll('[data-ui-ref]'))"
                "    .map(node => node.getBoundingClientRect())"
                "    .filter(rect => rect.right > panel.left && rect.left < panel.right"
                "      && rect.bottom > panel.top && rect.top < panel.bottom)"
                "    .length;"
                "})())"
            ))
            self.assertEqual(overlap, 0)

    def test_closing_the_panel_hands_the_space_back(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            where = center_of(engine, '[data-ui-panel-action="close"]')
            engine.click(where["x"], where["y"])
            padding = engine.evaluate(
                "getComputedStyle(document.body).paddingRight"
            )
            self.assertEqual(padding, "0px")

    def test_a_compact_viewport_docks_the_panel_at_the_bottom(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(390, 844))
            probe = json.loads(engine.evaluate(
                "JSON.stringify((() => {"
                "  const panel = document.querySelector('[data-ui-panel]');"
                "  const style = getComputedStyle(panel);"
                "  const panelRect = panel.getBoundingClientRect();"
                "  const covered = Array.from("
                "    document.querySelectorAll('[data-ui-ref]'))"
                "    .map(node => node.getBoundingClientRect())"
                "    .filter(rect => rect.top < panelRect.bottom"
                "      && rect.bottom > panelRect.top).length;"
                "  return {bottom: style.bottom, left: style.left,"
                "    bodyPaddingBottom: getComputedStyle(document.body)"
                "      .paddingBottom,"
                "    coveredAboveFold: covered};"
                "})())"
            ))
            self.assertEqual(probe["bottom"], "0px")
            self.assertEqual(probe["left"], "0px")
            self.assertNotEqual(probe["bodyPaddingBottom"], "0px")


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class TheLockedSelectionIsVisibleOnThePageTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _ringed_titles(self, engine):
        return json.loads(engine.evaluate(
            "JSON.stringify(Array.from("
            "  document.querySelectorAll('[data-ui-locked-target]'))"
            ".map(node => node.textContent))"
        ))

    def _click_action(self, engine, action):
        where = center_of(engine, '[data-ui-panel-action="' + action + '"]')
        engine.click(where["x"], where["y"])

    def test_selecting_in_the_panel_rings_the_business_element(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self._click_action(engine, "select")
            self.assertEqual(self._ringed_titles(engine), ["run-one"])
            self._click_action(engine, "select")
            self.assertEqual(self._ringed_titles(engine), ["run-two"])

    def test_clearing_removes_the_ring(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            self._click_action(engine, "select")
            self._click_action(engine, "clear")
            self.assertEqual(self._ringed_titles(engine), [])


@unittest.skipUnless(chrome_available(), "verification-stage browser not present")
class ADeepLinkRingIsVisibleTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW_MODEL)
        self.addCleanup(self.host.close)

    def test_the_located_element_carries_a_visible_ring(self):
        """The marker attribute alone highlights nothing a human can see."""
        link = build_deep_link(home_manifest(), "home.record-list")
        with browser() as engine:
            engine.open(self.host.base_url + link, viewport=(1280, 900))
            outline = engine.evaluate(
                "getComputedStyle(document.querySelector('[data-ui-located]'))"
                ".outlineWidth"
            )
            self.assertEqual(outline, "3px")


if __name__ == "__main__":
    unittest.main()
