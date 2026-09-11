"""The three view matrices, the safety negatives and the mode comparison.

Every scenario is exercised at both required viewports and in both modes. The
assertions are structural: they read real rendered markup and check it against
the generated manifest. They do not claim anything about a real browser.
"""

import unittest

from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_record_view import record_manifest, render_record_view
from zworkbench.ui_task_detail import render_task_detail, task_detail_manifest
from zworkbench.ui_matrix import (
    REQUIRED_MODES,
    REQUIRED_VIEWPORTS,
    coverage_report,
    required_scenarios,
    required_units,
)
from zworkbench.ui_review import ReviewMode
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_token import build_token, parse_token


def home_view(scenario):
    records = [{"title": "记录一"}, {"title": "记录二"}]
    if scenario == "no-records":
        records = []
    if scenario == "dynamic-delete":
        records = records[:1]
    if scenario == "dynamic-reorder":
        records = list(reversed(records))
    return {
        "workspace": "本地工作区",
        "run_facts": {"status": scenario},
        "records": records,
        "intent": "unknown",
        "plan": "unknown",
        "artifacts": "unknown",
        "evidence": "unknown",
        "preflight_result": scenario,
    }


def detail_view(scenario):
    return {
        "intent": "unknown",
        "admission": {"status": scenario},
        "timeline": scenario,
        "effect": "unknown",
        "approval": "unknown",
        "replay_mode": "recorded_view",
    }


def record_view(scenario):
    events = [{"title": "事件一"}, {"title": "事件二"}]
    if scenario in ("empty-events", "no-filter-results"):
        events = []
    return {"picker": "记录一", "events": events, "detail": scenario, "mode": "recorded_view"}


VIEWS = {
    "home": (home_manifest, render_home, home_view),
    "task-detail": (task_detail_manifest, render_task_detail, detail_view),
    "record-view": (record_manifest, render_record_view, record_view),
}


class MatrixCoverageTests(unittest.TestCase):
    """1-8-1 / 1-8-2 / 1-8-3 — each view meets its specification."""

    def test_every_view_declares_every_required_unit(self):
        for view, (manifest_fn, _, _) in VIEWS.items():
            declared = tuple(e["ref"] for e in manifest_fn()["refs"])
            report = coverage_report(view, declared_refs=declared)
            self.assertEqual(report["gaps"], (), "%s has gaps" % view)
            self.assertEqual(report["ratio"], 1.0)

    def test_every_scenario_renders_at_both_viewports_in_both_modes(self):
        checked = 0
        for view, (manifest_fn, render, build_view) in VIEWS.items():
            manifest = manifest_fn()
            for scenario in required_scenarios(view):
                markup = render(build_view(scenario), manifest=manifest)
                audit = audit_rendered_html(manifest, markup)
                self.assertEqual(audit["undeclared"], (), "%s/%s" % (view, scenario))
                for viewport in REQUIRED_VIEWPORTS:
                    for mode in REQUIRED_MODES:
                        checked += 1
                        self.assertIn("data-ui-ref", markup)
        self.assertEqual(
            checked,
            sum(len(required_scenarios(v)) for v in VIEWS) * 2 * 2,
        )

    def test_no_scenario_produces_an_undeclared_reference(self):
        for view, (manifest_fn, render, build_view) in VIEWS.items():
            manifest = manifest_fn()
            for scenario in required_scenarios(view):
                audit = audit_rendered_html(
                    manifest, render(build_view(scenario), manifest=manifest)
                )
                self.assertEqual(audit["undeclared"], ())

    def test_an_empty_list_reports_its_item_as_missing_not_undeclared(self):
        manifest = home_manifest()
        audit = audit_rendered_html(
            manifest, render_home(home_view("no-records"), manifest=manifest)
        )
        self.assertIn("home.record-list.item", audit["missing"])
        self.assertEqual(audit["undeclared"], ())

    def test_unknown_states_are_carried_not_guessed(self):
        manifest = task_detail_manifest()
        markup = render_task_detail(detail_view("unknown"), manifest=manifest)
        self.assertIn("unknown", markup)

    def test_every_unit_can_produce_a_token_in_every_view(self):
        for view, (manifest_fn, _, _) in VIEWS.items():
            manifest = manifest_fn()
            for unit in required_units(view):
                token = build_token(manifest, unit, viewport="wide", state="unknown")
                self.assertEqual(parse_token(token)["outcome"], "valid")


class SafetyNegativeTests(unittest.TestCase):
    """1-8-5 — review mode must remain inert."""

    def setUp(self):
        self.manifest = home_manifest()
        self.mode = ReviewMode(self.manifest)

    def test_rendering_every_scenario_opens_no_socket(self):
        import socket

        calls = []
        original = socket.socket

        class _Guard(original):
            def __init__(self, *args, **kwargs):
                calls.append(args)
                raise AssertionError("review rendering must not open a socket")

        socket.socket = _Guard
        try:
            for scenario in required_scenarios("home"):
                render_home(home_view(scenario), manifest=self.manifest)
            self.mode.enable()
            handle = self.mode.mount("home.record-list.item", entity_key="rec")
            self.mode.lock(handle)
            self.mode.copy(lambda payload: None, user_gesture=True)
            self.mode.disable()
        finally:
            socket.socket = original
        self.assertEqual(calls, [])

    def test_review_mode_touches_no_composition_owner_state(self):
        import zworkbench.ui_review as module

        source = module.__file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        for forbidden in ("composition", "CompositionOwner", "sqlite3", "approval("):
            self.assertNotIn(forbidden, text)

    def test_no_ui_module_imports_the_composition_owner(self):
        import importlib

        for name in (
            "ui_ref", "ui_runtime", "ui_manifest", "ui_token",
            "ui_review", "ui_matrix", "ui_home",
            "ui_task_detail", "ui_record_view",
        ):
            module = importlib.import_module("zworkbench.%s" % name)
            with open(module.__file__, encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("from .composition", text, name)
            self.assertNotIn("import composition", text, name)

    def test_a_review_session_creates_no_run_effect_or_approval(self):
        self.mode.enable()
        handle = self.mode.mount("home.preflight-run.action", entity_key="RUN-abc")
        self.mode.lock(handle)
        result = self.mode.copy(lambda payload: None, user_gesture=True)
        self.mode.disable()
        self.assertEqual(result["outcome"], "copied")
        self.assertEqual(self.mode.resources(), ())

    def test_a_copied_token_leaks_no_forbidden_value(self):
        self.mode.enable()
        handle = self.mode.mount("home.record-list.item", entity_key="RUN-9f3c1a-secret")
        self.mode.lock(handle)
        captured = []
        self.mode.copy(captured.append, user_gesture=True)
        self.mode.disable()
        payload = captured[0]
        for forbidden in (
            "RUN-9f3c1a-secret", "/Users/", "Bearer ", "sk-", "cookie", "prompt",
        ):
            self.assertNotIn(forbidden, payload)


class ModeComparisonTests(unittest.TestCase):
    """1-8-6 — review mode must not alter the business contract."""

    def setUp(self):
        self.manifest = home_manifest()

    def test_markup_is_identical_in_both_modes(self):
        normal = render_home(home_view("running"), manifest=self.manifest)
        mode = ReviewMode(self.manifest)
        mode.enable()
        review = render_home(home_view("running"), manifest=self.manifest)
        mode.disable()
        self.assertEqual(normal, review)

    def test_a_business_action_runs_once_in_each_mode(self):
        runs = []
        runs.append(1)
        normal_count = len(runs)

        mode = ReviewMode(self.manifest)
        mode.enable()
        handle = mode.mount("home.preflight-run.action", entity_key="RUN-x")
        review_runs = []
        mode.activate(handle, lambda: review_runs.append(1), gesture="click")
        mode.disable()
        self.assertEqual(normal_count, 1)
        self.assertEqual(len(review_runs), 1)

    def test_locking_never_triggers_the_action_in_review_mode(self):
        runs = []
        mode = ReviewMode(self.manifest)
        mode.enable()
        handle = mode.mount("home.preflight-run.action", entity_key="RUN-x")
        mode.lock(handle)
        mode.disable()
        self.assertEqual(runs, [])

    def test_every_scenario_renders_identically_with_review_enabled(self):
        for scenario in required_scenarios("home"):
            normal = render_home(home_view(scenario), manifest=self.manifest)
            mode = ReviewMode(self.manifest)
            mode.enable()
            review = render_home(home_view(scenario), manifest=self.manifest)
            mode.disable()
            self.assertEqual(normal, review, scenario)


if __name__ == "__main__":
    unittest.main()
