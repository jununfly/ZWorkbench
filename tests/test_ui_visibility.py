"""Behaviour tests for the three visibility states the PRD requires.

The PRD asks every semantic unit in a scenario to be classified as visible,
expandable or not applicable, and it attaches a different obligation to each:
an expandable unit must be locatable after a read-only expansion, a hidden unit
must answer ``unavailable`` rather than resolve to a substitute, and a not
applicable unit must carry a stated reason and must never be a relabelled
missing implementation.

Two properties are load-bearing across the whole file. Visibility is measured
against the document that was actually rendered, not against the manifest --
a declaration says a unit exists somewhere, not that it is on this page. And
``unavailable`` is the answer for "declared but not present", which is a
different fix from "never declared".
"""

import json
import sys
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import locate, render_document, serve_workbench
from zworkbench.ui_matrix import (
    CoverageError,
    MATRIX,
    UNIT_VISIBILITY,
    coverage_report,
    required_units,
    unit_visibility,
)
from zworkbench.ui_record_view import record_manifest, render_record_view
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_task_detail import render_task_detail, task_detail_manifest
from zworkbench.ui_token import build_deep_link
from zworkbench.ui_view_model import owner_view_source, task_detail_view_model

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

RECORD_VIEW = {
    "picker": "run-one",
    "events": [{"title": "run.created"}],
    "detail": "run.created",
    "mode": "recorded_view",
}


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


class ClassifyingEveryUnitTests(unittest.TestCase):
    """1-5 — the classification is a specification, transcribed by hand.

    It is deliberately not derived from the renderers. A table computed from
    what the code happens to render would agree with any implementation,
    including one that renders nothing.
    """

    def test_every_specified_unit_has_a_visibility_class(self):
        for view in MATRIX:
            for unit in required_units(view):
                with self.subTest(view=view, unit=unit):
                    self.assertIn(
                        unit_visibility(view, unit),
                        ("visible", "expandable", "conditional"),
                    )

    def test_the_table_names_no_unit_outside_the_specification(self):
        """Otherwise a stale entry could excuse a unit that no longer exists."""
        for view, classes in UNIT_VISIBILITY.items():
            self.assertEqual(
                sorted(classes), sorted(required_units(view)), view
            )


class ExpandingAUnitReadOnlyTests(unittest.TestCase):
    """1-5-1 — an expandable unit must be locatable once expanded."""

    def setUp(self):
        self.manifest = record_manifest()

    def test_the_specification_marks_the_disclosed_units_expandable(self):
        for unit in (
            "record-view.result",
            "record-view.artifact-metadata",
            "record-view.replay-metadata",
        ):
            self.assertEqual(unit_visibility("record-view", unit), "expandable")

    def test_an_expandable_unit_is_present_but_collapsed_by_default(self):
        markup = render_record_view(RECORD_VIEW, manifest=self.manifest)
        audit = audit_rendered_html(self.manifest, markup)
        self.assertIn("record-view.result", audit["instances"])
        self.assertNotIn(" open", markup)

    def test_expanding_opens_the_disclosure_that_holds_the_unit(self):
        markup = render_record_view(
            RECORD_VIEW, manifest=self.manifest, expand=("record-view.result",)
        )
        self.assertIn("<details", markup)
        self.assertIn(" open", markup)

    def test_a_deep_link_to_an_expandable_unit_expands_and_locates_it(self):
        """The whole point: following the link must not require a click."""
        document = render_document(
            "/record-view",
            RECORD_VIEW,
            "ui_ref=record-view.result&ui_map=" + self.manifest["ui_map"],
        )
        self.assertIn('data-ui-located="record-view.result"', document)
        self.assertIn(" open", document)

    def test_expanding_one_unit_does_not_open_an_unrelated_disclosure(self):
        """A link that opens everything has not located anything."""
        markup = render_record_view(
            RECORD_VIEW, manifest=self.manifest, expand=("record-view.record-picker",)
        )
        self.assertNotIn(" open", markup)

    def test_expansion_reveals_content_without_changing_the_references(self):
        collapsed = audit_rendered_html(
            self.manifest, render_record_view(RECORD_VIEW, manifest=self.manifest)
        )
        expanded = audit_rendered_html(
            self.manifest,
            render_record_view(
                RECORD_VIEW, manifest=self.manifest, expand=("record-view.result",)
            ),
        )
        self.assertEqual(collapsed["instances"], expanded["instances"])
        self.assertEqual(expanded["undeclared"], ())


class LocatingAHiddenUnitTests(unittest.TestCase):
    """1-5-2 — a unit that is not on this page answers ``unavailable``."""

    def setUp(self):
        self.manifest = home_manifest()

    def test_a_declared_unit_absent_from_the_document_is_unavailable(self):
        empty = "<main></main>"
        outcome = locate(
            self.manifest,
            "ui_ref=home.record-list.item&ui_map=" + self.manifest["ui_map"],
            empty,
        )
        self.assertEqual(outcome["outcome"], "unavailable")

    def test_unavailable_is_distinct_from_never_declared(self):
        """The two need different fixes, so they must not share one word."""
        rendered = "<main></main>"
        unknown = locate(
            self.manifest,
            "ui_ref=home.invented&ui_map=" + self.manifest["ui_map"],
            rendered,
        )
        self.assertEqual(unknown["outcome"], "unknown-reference")

    def test_an_empty_list_makes_its_item_unavailable_over_http(self):
        """A real hidden state: no records, so no row exists to point at."""
        host = serve_workbench(view_source=lambda route: {"records": []})
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertIn("unavailable", body)
        self.assertNotIn("data-ui-located=", body)

    def test_the_same_link_locates_the_item_once_a_record_exists(self):
        """Without this the test above would pass on a permanently broken link."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(owner.close)
        owner.create_run("run-one", "local_read_only_run", {})
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertIn('data-ui-located="home.record-list.item"', body)
        self.assertNotIn("unavailable", body)

    def test_an_unavailable_link_does_not_fall_back_to_another_element(self):
        host = serve_workbench(view_source=lambda route: {"records": []})
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertEqual(body.count("data-ui-located="), 0)


class ExcusingAUnitAsNotApplicableTests(unittest.TestCase):
    """1-5-3 — a real scenario uses the exemption, with a stated reason."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.addCleanup(self.owner.close)
        self.owner.create_run("run-alpha", "local_read_only_run", {})
        self.model = task_detail_view_model(self.owner, "run-alpha")

    def test_a_read_only_run_reports_the_effect_family_as_not_applicable(self):
        self.assertEqual(
            sorted(self.model["not_applicable"]),
            ["task-detail.approval", "task-detail.effect", "task-detail.reconcile"],
        )

    def test_each_exemption_carries_a_reason_from_the_product(self):
        for unit, reason in self.model["not_applicable"].items():
            self.assertTrue(str(reason).strip(), unit)

    def test_the_reason_is_shown_to_the_reviewer(self):
        markup = render_task_detail(self.model, manifest=task_detail_manifest())
        self.assertIn('data-ui-not-applicable="task-detail.effect"', markup)
        self.assertIn(self.model["not_applicable"]["task-detail.effect"], markup)

    def test_an_excused_unit_is_not_rendered_as_a_reference(self):
        """Otherwise the exemption and the coverage count would contradict."""
        manifest = task_detail_manifest()
        audit = audit_rendered_html(manifest, render_task_detail(self.model, manifest=manifest))
        self.assertNotIn("task-detail.effect", audit["instances"])
        self.assertIn("task-detail.effect", audit["missing"])

    def test_the_report_accepts_the_exemption_and_keeps_the_denominator(self):
        manifest = task_detail_manifest()
        markup = render_task_detail(self.model, manifest=manifest)
        rendered = tuple(audit_rendered_html(manifest, markup)["instances"])
        report = coverage_report(
            "task-detail",
            declared_refs=rendered,
            not_applicable=self.model["not_applicable"],
        )
        self.assertEqual(report["gaps"], ())
        self.assertEqual(report["not_applicable"], 3)
        self.assertEqual(report["required"], len(required_units("task-detail")))

    def test_a_unit_the_specification_requires_visible_cannot_be_excused(self):
        """This is the rule that stops a missing implementation being relabelled."""
        self.assertEqual(unit_visibility("task-detail", "task-detail.intent"), "visible")
        with self.assertRaises(CoverageError):
            coverage_report(
                "task-detail",
                declared_refs=(),
                not_applicable={"task-detail.intent": "还没做"},
            )

    def test_a_run_that_can_produce_effects_is_not_excused(self):
        """The exemption must follow the run class, not the surface."""
        self.owner.create_run("run-beta", "worker_diff_run", {})
        model = task_detail_view_model(self.owner, "run-beta")
        self.assertEqual(model["not_applicable"], {})


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class DisclosingContentInARealEngineTests(unittest.TestCase):
    """1-5-1 — native disclosure, measured rather than asserted from markup.

    ``<details>`` hides its content in the engine, not in the markup, so only an
    engine can say whether an expandable unit is really revealed.

    The measurement is ``checkVisibility()`` plus the text the page actually
    exposes, and the choice matters. Geometry looks like the obvious probe and is
    useless here: Chrome gives the collapsed content a layout box anyway, so its
    height is 24px both collapsed and expanded. An assertion on height would
    have been false in one direction and vacuously true in the other -- the
    second is the dangerous one, because ``height > 0`` would have "passed"
    without the disclosure ever opening. The disclosure element's own height does
    grow, but that measures the summary plus content, not whether the unit is
    revealed.
    """

    def setUp(self):
        self.manifest = record_manifest()
        self.host = serve_workbench(view_source=lambda route: RECORD_VIEW)
        self.addCleanup(self.host.close)

    def _measure(self, path):
        with browser() as engine:
            engine.open(self.host.base_url + path, viewport=(1280, 900))
            return json.loads(
                engine.evaluate(
                    "JSON.stringify((() => {"
                    "  const unit = document.querySelector("
                    "    '[data-ui-ref=\"record-view.result\"]');"
                    "  return {"
                    "    present: !!unit,"
                    "    rendered: unit ? unit.checkVisibility({"
                    "      checkVisibilityCSS: true, contentVisibilityAuto: true"
                    "    }) : false,"
                    "    exposed: document.body.innerText.includes('unknown'),"
                    "    open: document.querySelector('details').open,"
                    "  };"
                    "})())"
                )
            )

    def test_a_collapsed_unit_is_in_the_document_but_is_not_rendered(self):
        """Present in the DOM, absent from the page: that is what hidden means."""
        measured = self._measure("/record-view")
        self.assertTrue(measured["present"])
        self.assertFalse(measured["open"])
        self.assertFalse(measured["rendered"])
        self.assertFalse(measured["exposed"])

    def test_following_the_link_reveals_the_unit_without_scripting(self):
        """No script runs on this page, so the engine's own disclosure did it."""
        link = build_deep_link(self.manifest, "record-view.result")
        measured = self._measure(link)
        self.assertTrue(measured["open"])
        self.assertTrue(measured["rendered"])
        self.assertTrue(measured["exposed"])


if __name__ == "__main__":
    unittest.main()
