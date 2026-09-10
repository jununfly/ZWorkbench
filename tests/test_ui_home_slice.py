"""End-to-end contract tests for the minimum vertical slice.

The slice proves one chain: declaration -> manifest -> DOM -> token -> code
location.  It covers a static region, a dynamic record list and a business
button, at both viewport classes.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_home import HOME_REFS, home_manifest, render_home
from zworkbench.ui_manifest import locate_source
from zworkbench.ui_runtime import ReviewSession, audit_rendered_html
from zworkbench.ui_ref import resolve
from zworkbench.ui_token import build_token, parse_token


def view_model(records=(), state="running"):
    """A redacted presentation model, as the control-plane facade would emit."""
    return {
        "state": state,
        "records": list(records),
        "run_facts": {"status": state, "run": "unknown"},
    }


class RenderingTheHomeSliceTests(unittest.TestCase):
    def test_the_static_region_the_list_and_the_button_are_all_rendered(self):
        html_text = render_home(view_model(records=[{"key": "e1", "title": "甲"}]))
        audit = audit_rendered_html(home_manifest(), html_text)
        for ref in ("home.run-facts", "home.record-list.item", "home.preflight-run.action"):
            self.assertIn(ref, audit["instances"])

    def test_the_rendered_view_declares_every_reference_it_uses(self):
        html_text = render_home(view_model(records=[{"key": "e1", "title": "甲"}]))
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertEqual(audit["undeclared"], ())

class TheChainClosesForEachTargetKindTests(unittest.TestCase):
    """declaration -> manifest -> DOM -> token -> code location, per kind."""

    def _walk_chain(self, ref, *, viewport, records):
        manifest = home_manifest()
        html_text = render_home(view_model(records=records), manifest=manifest)

        # DOM agrees with the manifest.
        audit = audit_rendered_html(manifest, html_text)
        self.assertIn(ref, audit["instances"])

        # A token is produced and parses back.
        token = build_token(manifest, ref, viewport=viewport, state="running")
        parsed = parse_token(token)
        self.assertEqual(parsed["outcome"], "valid")
        self.assertEqual(parsed["token"]["ref"], ref)
        self.assertEqual(parsed["token"]["ui_map"], manifest["ui_map"])

        # The token resolves to a declaration.
        structural = resolve(manifest, parsed["token"]["ref"], ui_map=parsed["token"]["ui_map"])
        self.assertEqual(structural["outcome"], "found")

        # The declaration locates real code.
        located = locate_source(manifest, ref, root=Path(__file__).resolve().parents[1])
        self.assertEqual(located["outcome"], "found")
        self.assertEqual(located["repo_path"], "src/zworkbench/ui_home.py")
        return located

    def test_the_chain_closes_for_the_static_region(self):
        self._walk_chain("home.run-facts", viewport="wide", records=[])

    def test_the_chain_closes_for_a_dynamic_record_item(self):
        self._walk_chain(
            "home.record-list.item",
            viewport="wide",
            records=[{"key": "e1", "title": "甲"}],
        )

    def test_the_chain_closes_for_the_business_button(self):
        self._walk_chain("home.preflight-run.action", viewport="wide", records=[])

    def test_code_location_reports_no_line_number(self):
        located = self._walk_chain("home.run-facts", viewport="wide", records=[])
        self.assertNotIn("line", located)

class ViewportClassesTests(unittest.TestCase):
    """390px is compact, 1280px is wide; the chain must hold at both."""

    VIEWPORTS = (("compact", 390), ("wide", 1280))

    def test_the_declared_boundary_matches_the_spec(self):
        from zworkbench.ui_token import VIEWPORTS as allowed

        self.assertEqual(sorted(allowed), ["compact", "wide"])
        for name, width in self.VIEWPORTS:
            expected = "compact" if width < 768 else "wide"
            self.assertEqual(name, expected)

    def test_every_target_kind_closes_the_chain_at_both_viewports(self):
        manifest = home_manifest()
        for viewport, _width in self.VIEWPORTS:
            for ref in (
                "home.run-facts",
                "home.record-list.item",
                "home.preflight-run.action",
            ):
                with self.subTest(viewport=viewport, ref=ref):
                    token = build_token(manifest, ref, viewport=viewport, state="running")
                    parsed = parse_token(token)
                    self.assertEqual(parsed["outcome"], "valid")
                    self.assertEqual(parsed["token"]["viewport"], viewport)

    def test_the_rendered_markup_does_not_depend_on_the_viewport(self):
        """Layout is CSS; the reference contract must not fork per viewport."""
        records = [{"key": "e1", "title": "甲"}]
        first = render_home(view_model(records=records))
        second = render_home(view_model(records=records))
        self.assertEqual(first, second)


class EmptyAndUnknownStateTests(unittest.TestCase):
    def test_an_empty_record_list_still_declares_the_list_region(self):
        html_text = render_home(view_model(records=[], state="empty"))
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertIn("home.record-list", audit["instances"])
        self.assertNotIn("home.record-list.item", audit["instances"])

    def test_an_empty_list_reports_the_item_as_missing_not_as_undeclared(self):
        audit = audit_rendered_html(
            home_manifest(), render_home(view_model(records=[], state="empty"))
        )
        self.assertIn("home.record-list.item", audit["missing"])
        self.assertEqual(audit["undeclared"], ())

    def test_an_unmounted_item_resolves_as_unavailable_in_an_empty_list(self):
        manifest = home_manifest()
        session = ReviewSession(manifest)
        self.assertEqual(
            session.resolve_structural("home.record-list.item")["outcome"], "unavailable"
        )

    def test_an_unknown_state_is_carried_as_unknown_not_guessed(self):
        manifest = home_manifest()
        html_text = render_home(view_model(records=[], state="unknown"), manifest=manifest)
        self.assertIn("unknown", html_text)
        parsed = parse_token(
            build_token(manifest, "home.run-facts", viewport="compact", state="unknown")
        )
        self.assertEqual(parsed["token"]["state"], "unknown")

    def test_two_records_are_ambiguous_without_a_handle_at_either_viewport(self):
        manifest = home_manifest()
        session = ReviewSession(manifest)
        session.mount("home.record-list.item", entity_key="e1")
        session.mount("home.record-list.item", entity_key="e2")
        located = session.resolve_structural("home.record-list.item")
        self.assertEqual(located["outcome"], "ambiguous")
        self.assertEqual(located["instance_count"], 2)


if __name__ == "__main__":
    unittest.main()
