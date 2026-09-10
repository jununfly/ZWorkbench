"""Behaviour contract for the local review annotation mode.

These tests cover the *logical* half of each interaction contract: what the
review mode decides.  They do not and cannot cover the *host* half — whether a
browser actually honours ``pointer-events: none``, what native focus order a
real DOM produces, or how a real clipboard API rejects a write.  Those surfaces
stay ``unknown`` and are declared as such in ``HOST_UNKNOWNS``.
"""

import unittest

from zworkbench.ui_home import home_manifest
from zworkbench.ui_review import (
    HOST_UNKNOWNS,
    PANEL_ACTIONS,
    ReviewMode,
    ReviewModeError,
)


class _Button:
    """A business action that records how many times it really ran."""

    def __init__(self):
        self.runs = 0

    def __call__(self):
        self.runs += 1
        return "ran"


def _mode():
    return ReviewMode(home_manifest())


class ReviewModeLifecycleTests(unittest.TestCase):
    """1-6-1 — default off, explicit local enable, zero residue on exit."""

    def test_review_mode_is_off_until_explicitly_enabled(self):
        self.assertFalse(_mode().enabled)

    def test_a_disabled_mode_holds_no_resources(self):
        self.assertEqual(_mode().resources(), ())

    def test_enabling_registers_an_overlay_and_listeners(self):
        mode = _mode()
        mode.enable()
        kinds = {resource["kind"] for resource in mode.resources()}
        self.assertEqual(kinds, {"overlay", "listener"})

    def test_enabling_twice_does_not_duplicate_registrations(self):
        mode = _mode()
        mode.enable()
        first = len(mode.resources())
        mode.enable()
        self.assertEqual(len(mode.resources()), first)

    def test_disabling_releases_every_resource(self):
        mode = _mode()
        mode.enable()
        mode.disable()
        self.assertEqual(mode.resources(), ())

    def test_repeated_start_stop_cycles_leave_no_residue(self):
        mode = _mode()
        for _ in range(10):
            mode.enable()
            mode.mount("home.record-list.item", entity_key="record-1")
            mode.disable()
        self.assertFalse(mode.enabled)
        self.assertEqual(mode.resources(), ())
        self.assertEqual(mode.session_handles(), ())

    def test_disabling_an_already_disabled_mode_is_a_no_op(self):
        mode = _mode()
        mode.disable()
        self.assertEqual(mode.resources(), ())

    def test_a_disabled_mode_refuses_panel_operations(self):
        with self.assertRaises(ReviewModeError):
            _mode().panel_entries()

    def test_handles_do_not_survive_a_restart(self):
        mode = _mode()
        mode.enable()
        handle = mode.mount("home.record-list.item", entity_key="record-1")
        mode.disable()
        mode.enable()
        self.assertEqual(mode.resolve_instance(handle)["outcome"], "expired")


class PointerPassthroughTests(unittest.TestCase):
    """1-6-2 — the highlight layer must not swallow business interaction."""

    def setUp(self):
        self.mode = _mode()
        self.mode.enable()
        self.handle = self.mode.mount("home.preflight-run.action", entity_key="preflight")
        self.button = _Button()

    def test_the_overlay_declares_that_it_takes_no_pointer_events(self):
        self.assertEqual(self.mode.overlay_descriptor()["pointer-events"], "none")

    def test_a_plain_click_runs_the_business_action_exactly_once(self):
        result = self.mode.activate(self.handle, self.button, gesture="click")
        self.assertEqual(self.button.runs, 1)
        self.assertEqual(result["business"], "delivered")
        self.assertEqual(result["review"], "not-consumed")

    def test_enter_and_space_keep_their_business_behaviour(self):
        for key in ("Enter", " "):
            button = _Button()
            result = self.mode.activate(self.handle, button, gesture=key)
            self.assertEqual(button.runs, 1)
            self.assertEqual(result["business"], "delivered")

    def test_hover_and_focus_only_preview(self):
        for gesture in ("hover", "focus"):
            preview = self.mode.preview(self.handle, gesture=gesture)
            self.assertEqual(preview["outcome"], "preview")
            self.assertIsNone(self.mode.locked_target())
            self.assertEqual(self.button.runs, 0)

    def test_review_mode_never_dispatches_a_business_activation_itself(self):
        self.mode.lock(self.handle)
        self.assertEqual(self.button.runs, 0)


class PanelSurfaceTests(unittest.TestCase):
    """1-6-3 — panel content, redaction and keyboard reachability."""

    def setUp(self):
        self.mode = _mode()
        self.mode.enable()
        self.first = self.mode.mount("home.record-list.item", entity_key="record-1")
        self.second = self.mode.mount("home.record-list.item", entity_key="record-2")
        self.button = self.mode.mount("home.preflight-run.action", entity_key="RUN-9f3c1a")

    def test_a_panel_entry_carries_only_the_declared_fields(self):
        for entry in self.mode.panel_entries():
            self.assertEqual(set(entry), {"ref", "semantic_zh", "instance", "mark"})

    def test_the_panel_never_exposes_a_business_entity_key(self):
        rendered = repr(self.mode.panel_entries())
        for forbidden in ("record-1", "record-2", "RUN-9f3c1a"):
            self.assertNotIn(forbidden, rendered)

    def test_only_repeated_structural_items_carry_a_mark(self):
        marks = {entry["instance"]: entry["mark"] for entry in self.mode.panel_entries()}
        self.assertIsNotNone(marks[self.first])
        self.assertIsNotNone(marks[self.second])
        self.assertIsNone(marks[self.button])

    def test_a_mark_is_transient_and_is_not_an_identity(self):
        before = {e["instance"]: e["mark"] for e in self.mode.panel_entries()}
        after = {e["instance"]: e["mark"] for e in self.mode.panel_entries()}
        self.assertNotEqual(before[self.first], after[self.first])
        self.assertNotEqual(before[self.first], self.first)

    def test_every_panel_action_has_a_keyboard_route(self):
        plan = self.mode.keyboard_plan()
        self.assertEqual(set(plan), set(PANEL_ACTIONS))
        self.assertTrue(all(plan.values()))

    def test_the_focused_panel_entry_is_always_visible(self):
        self.mode.focus_panel()
        self.assertIsNotNone(self.mode.focused_entry())

    def test_locking_from_the_panel_selects_without_executing(self):
        button = _Button()
        self.mode.lock(self.button)
        self.assertEqual(button.runs, 0)
        self.assertEqual(self.mode.locked_target()["instance"], self.button)


class EscapeScopeTests(unittest.TestCase):
    """1-6-4 — Escape belongs to the panel only."""

    def setUp(self):
        self.mode = _mode()
        self.mode.enable()
        self.handle = self.mode.mount("home.record-list.item", entity_key="record-1")
        self.mode.lock(self.handle)

    def test_escape_clears_the_lock_while_the_panel_holds_focus(self):
        self.mode.focus_panel()
        result = self.mode.handle_key("Escape")
        self.assertEqual(result["review"], "consumed")
        self.assertIsNone(self.mode.locked_target())

    def test_escape_is_left_alone_when_the_panel_lacks_focus(self):
        result = self.mode.handle_key("Escape")
        self.assertEqual(result["review"], "not-consumed")
        self.assertEqual(self.mode.locked_target()["instance"], self.handle)

    def test_escape_does_not_intercept_a_business_dialog(self):
        result = self.mode.handle_key("Escape", business_dialog_open=True)
        self.assertEqual(result["review"], "not-consumed")
        self.assertEqual(result["business"], "delivered")

    def test_a_business_dialog_wins_even_if_the_panel_is_focused(self):
        self.mode.focus_panel()
        result = self.mode.handle_key("Escape", business_dialog_open=True)
        self.assertEqual(result["review"], "not-consumed")
        self.assertEqual(self.mode.locked_target()["instance"], self.handle)


class CopyContractTests(unittest.TestCase):
    """1-6-5 — copying is user-initiated, and failure is visible."""

    def setUp(self):
        self.mode = _mode()
        self.mode.enable()
        self.handle = self.mode.mount("home.record-list.item", entity_key="record-1")
        self.mode.lock(self.handle)
        self.writes = []

    def _writer(self, payload):
        self.writes.append(payload)

    def _failing_writer(self, payload):
        self.writes.append(payload)
        raise OSError("clipboard refused")

    def test_a_copy_without_a_user_gesture_is_refused(self):
        result = self.mode.copy(self._writer, user_gesture=False)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(self.writes, [])

    def test_a_user_initiated_copy_writes_the_token_once(self):
        result = self.mode.copy(self._writer, user_gesture=True)
        self.assertEqual(result["outcome"], "copied")
        self.assertEqual(len(self.writes), 1)

    def test_a_copy_failure_is_visible_and_keeps_the_selection(self):
        result = self.mode.copy(self._failing_writer, user_gesture=True)
        self.assertEqual(result["outcome"], "copy-failed")
        self.assertTrue(result["visible"])
        self.assertEqual(self.mode.locked_target()["instance"], self.handle)

    def test_a_failed_copy_is_never_retried_automatically(self):
        self.mode.copy(self._failing_writer, user_gesture=True)
        self.assertEqual(len(self.writes), 1)

    def test_a_copy_failure_does_not_echo_the_host_error(self):
        result = self.mode.copy(self._failing_writer, user_gesture=True)
        self.assertNotIn("clipboard refused", repr(result))

    def test_copying_without_a_locked_target_reports_no_target(self):
        self.mode.clear()
        result = self.mode.copy(self._writer, user_gesture=True)
        self.assertEqual(result["outcome"], "no-target")
        self.assertEqual(self.writes, [])

    def test_the_copied_payload_is_a_parseable_review_token(self):
        self.mode.copy(self._writer, user_gesture=True)
        from zworkbench.ui_token import parse_token

        self.assertEqual(parse_token(self.writes[0])["outcome"], "valid")


class FocusRestoreTests(unittest.TestCase):
    """1-6-6 — closing the panel restores a predictable focus target."""

    def test_closing_restores_the_pre_review_target_when_it_still_exists(self):
        mode = _mode()
        mode.enable(focused_ref="home.preflight-run.action")
        mode.focus_panel()
        result = mode.close_panel(mounted_refs=("home.preflight-run.action",))
        self.assertEqual(result["focus"], "home.preflight-run.action")
        self.assertEqual(result["outcome"], "restored")

    def test_closing_falls_back_to_the_review_entry_when_the_target_vanished(self):
        mode = _mode()
        mode.enable(focused_ref="home.record-list.item")
        mode.focus_panel()
        result = mode.close_panel(mounted_refs=())
        self.assertEqual(result["outcome"], "fallback")
        self.assertEqual(result["focus"], mode.review_entry_ref())

    def test_closing_without_a_prior_focus_target_falls_back(self):
        mode = _mode()
        mode.enable()
        result = mode.close_panel(mounted_refs=("home.preflight-run.action",))
        self.assertEqual(result["outcome"], "fallback")

    def test_closing_the_panel_does_not_disable_review_mode(self):
        mode = _mode()
        mode.enable(focused_ref="home.preflight-run.action")
        mode.close_panel(mounted_refs=("home.preflight-run.action",))
        self.assertTrue(mode.enabled)


class HostUnknownTests(unittest.TestCase):
    """The honesty anchor: host-dependent halves are not claimed as passing."""

    def test_every_host_surface_stays_unknown(self):
        self.assertTrue(HOST_UNKNOWNS)
        for surface in HOST_UNKNOWNS:
            self.assertEqual(surface["status"], "unknown")
            self.assertTrue(surface["reason"])

    def test_the_four_prd_interaction_surfaces_are_all_declared(self):
        declared = {surface["surface"] for surface in HOST_UNKNOWNS}
        self.assertEqual(
            declared,
            {
                "keyboard-focus-order",
                "pointer-events-passthrough",
                "clipboard-failure-visible",
                "focus-restore-on-close",
            },
        )

    def test_no_host_surface_claims_automated_verification(self):
        for surface in HOST_UNKNOWNS:
            self.assertNotEqual(surface["verified_by"], "automated")


if __name__ == "__main__":
    unittest.main()
