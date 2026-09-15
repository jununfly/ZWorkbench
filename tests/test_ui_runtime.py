"""Behavior tests for rendering declared references and locating instances."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from zworkbench.ui_runtime import (
    ReviewSession,
    ReviewSessionClosed,
    audit_rendered_html,
    UnregisteredReference,
    render_attributes,
)


def anchor(symbol: str) -> SourceAnchor:
    return SourceAnchor(
        repo_path="src/zworkbench/ui/home.py",
        symbol=symbol,
        content_digest="a" * 64,
    )


def home_manifest():
    registry = UiRefRegistry()
    registry.declare(
        UiRefDeclaration(
            ref="home.root",
            semantic_zh="工作台首页",
            kind="region",
            view="home",
            source=anchor("render_home"),
        )
    )
    registry.declare(
        UiRefDeclaration(
            ref="home.record-list.item",
            semantic_zh="工作记录项",
            kind="list-item",
            view="home",
            source=anchor("render_item"),
        )
    )
    return registry.build_manifest(build="b" * 64)


class RenderingADeclaredReferenceTests(unittest.TestCase):
    def test_a_declared_reference_renders_the_data_attribute(self):
        self.assertEqual(
            render_attributes(home_manifest(), "home.root"),
            {"data-ui-ref": "home.root"},
        )

    def test_an_undeclared_reference_cannot_be_rendered(self):
        with self.assertRaises(UnregisteredReference):
            render_attributes(home_manifest(), "home.ghost")

class RenderedAttributesCarryNoBusinessDataTests(unittest.TestCase):
    """Run identity, titles and payloads must not travel in the reference."""

    def test_attributes_contain_only_the_structural_reference(self):
        attributes = render_attributes(home_manifest(), "home.record-list.item")
        self.assertEqual(list(attributes), ["data-ui-ref"])

    def test_the_reference_is_the_declared_structural_name_not_an_entity_key(self):
        attributes = render_attributes(home_manifest(), "home.record-list.item")
        self.assertEqual(attributes["data-ui-ref"], "home.record-list.item")

    def test_repeated_items_share_one_structural_reference(self):
        manifest = home_manifest()
        first = render_attributes(manifest, "home.record-list.item")
        second = render_attributes(manifest, "home.record-list.item")
        self.assertEqual(first, second)

class LockingAMountedInstanceTests(unittest.TestCase):
    def test_a_mounted_instance_can_be_locked_and_resolves_to_its_declaration(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.lock(handle)
        located = session.locked_target()
        self.assertEqual(located["outcome"], "found")
        self.assertEqual(located["ref"], "home.record-list.item")
        self.assertEqual(located["semantic_zh"], "工作记录项")

    def test_an_undeclared_reference_cannot_be_mounted(self):
        session = ReviewSession(home_manifest())
        with self.assertRaises(UnregisteredReference):
            session.mount("home.ghost", entity_key="e1")

    def test_a_handle_is_a_128_bit_random_hex_value(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="run-abc-123")
        self.assertRegex(handle, r"^[0-9a-f]{32}$")

    def test_a_handle_is_not_derived_from_the_entity_it_tracks(self):
        first = ReviewSession(home_manifest())
        second = ReviewSession(home_manifest())
        entity = "run-abc-123"
        handle_one = first.mount("home.record-list.item", entity_key=entity)
        handle_two = second.mount("home.record-list.item", entity_key=entity)
        self.assertNotEqual(handle_one, handle_two)
        self.assertNotIn(entity, handle_one)

    def test_nothing_is_locked_before_the_user_selects_a_target(self):
        session = ReviewSession(home_manifest())
        session.mount("home.record-list.item", entity_key="e1")
        self.assertIsNone(session.locked_target())

class UnmountedAndReorderedInstanceTests(unittest.TestCase):
    def test_an_unmounted_instance_is_unavailable_and_not_a_substitute(self):
        session = ReviewSession(home_manifest())
        first = session.mount("home.record-list.item", entity_key="e1")
        session.mount("home.record-list.item", entity_key="e2")
        session.lock(first)
        session.unmount(first)
        located = session.locked_target()
        self.assertEqual(located["outcome"], "unavailable")
        self.assertNotIn("instance", located)

    def test_a_locked_instance_does_not_follow_its_list_position(self):
        session = ReviewSession(home_manifest())
        first = session.mount("home.record-list.item", entity_key="e1")
        second = session.mount("home.record-list.item", entity_key="e2")
        session.lock(second)
        session.reorder([second, first])
        located = session.locked_target()
        self.assertEqual(located["outcome"], "found")
        self.assertEqual(session.entity_key_of(located["instance"]), "e2")

    def test_a_plain_re_render_keeps_the_locked_association(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.lock(handle)
        session.reorder([handle])
        self.assertEqual(session.locked_target()["outcome"], "found")

    def test_remounting_the_same_entity_restores_the_association(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.lock(handle)
        session.unmount(handle)
        restored = session.remount("home.record-list.item", entity_key="e1")
        self.assertEqual(restored, handle)
        self.assertEqual(session.locked_target()["outcome"], "found")

    def test_remounting_a_different_entity_does_not_reuse_the_handle(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.unmount(handle)
        other = session.remount("home.record-list.item", entity_key="e2")
        self.assertNotEqual(other, handle)

class ResolvingAStructuralReferenceTests(unittest.TestCase):
    """A structural reference without a handle must not pick a row for the user."""

    def test_repeated_instances_are_ambiguous_rather_than_the_first_row(self):
        session = ReviewSession(home_manifest())
        session.mount("home.record-list.item", entity_key="e1")
        session.mount("home.record-list.item", entity_key="e2")
        result = session.resolve_structural("home.record-list.item")
        self.assertEqual(result["outcome"], "ambiguous")
        self.assertEqual(result["instance_count"], 2)
        self.assertNotIn("instance", result)

    def test_an_ambiguous_result_does_not_expose_candidate_entities(self):
        session = ReviewSession(home_manifest())
        session.mount("home.record-list.item", entity_key="run-abc-123")
        session.mount("home.record-list.item", entity_key="run-def-456")
        result = session.resolve_structural("home.record-list.item")
        self.assertNotIn("run-abc-123", repr(result))
        self.assertNotIn("run-def-456", repr(result))

    def test_a_single_mounted_instance_resolves_directly(self):
        session = ReviewSession(home_manifest())
        session.mount("home.root", entity_key="static")
        result = session.resolve_structural("home.root")
        self.assertEqual(result["outcome"], "found")

    def test_a_declared_reference_that_is_not_mounted_is_unavailable(self):
        session = ReviewSession(home_manifest())
        result = session.resolve_structural("home.root")
        self.assertEqual(result["outcome"], "unavailable")

    def test_an_undeclared_reference_is_reported_as_unregistered(self):
        session = ReviewSession(home_manifest())
        with self.assertRaises(UnregisteredReference):
            session.resolve_structural("home.ghost")

    def test_ambiguity_clears_once_the_duplicates_unmount(self):
        session = ReviewSession(home_manifest())
        first = session.mount("home.record-list.item", entity_key="e1")
        session.mount("home.record-list.item", entity_key="e2")
        session.unmount(first)
        self.assertEqual(
            session.resolve_structural("home.record-list.item")["outcome"], "found"
        )

class HandleInvalidationTests(unittest.TestCase):
    """Closing review, reloading or switching workspace must void handles."""

    def test_a_handle_from_another_session_is_expired_not_found(self):
        first = ReviewSession(home_manifest())
        handle = first.mount("home.record-list.item", entity_key="e1")
        second = ReviewSession(home_manifest())
        second.mount("home.record-list.item", entity_key="e1")
        result = second.resolve_instance(handle)
        self.assertEqual(result["outcome"], "expired")

    def test_an_expired_result_does_not_claim_to_have_found_the_record(self):
        first = ReviewSession(home_manifest())
        handle = first.mount("home.record-list.item", entity_key="e1")
        second = ReviewSession(home_manifest())
        second.mount("home.record-list.item", entity_key="e1")
        result = second.resolve_instance(handle)
        self.assertNotIn("entity_key", result)
        self.assertNotIn("instance", result)

    def test_closing_review_expires_every_handle(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.lock(handle)
        session.close()
        self.assertEqual(session.resolve_instance(handle)["outcome"], "expired")

    def test_closing_review_clears_the_locked_target(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.lock(handle)
        session.close()
        self.assertIsNone(session.locked_target())

    def test_a_closed_session_does_not_resurrect_an_unmounted_handle(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.unmount(handle)
        session.close()
        self.assertEqual(session.resolve_instance(handle)["outcome"], "expired")

    def test_a_closed_session_mounts_nothing_further(self):
        session = ReviewSession(home_manifest())
        session.close()
        self.assertEqual(session.resolve_structural("home.root")["outcome"], "unavailable")

    def test_a_closed_session_rejects_new_mounts(self):
        session = ReviewSession(home_manifest())
        session.close()
        with self.assertRaises(ReviewSessionClosed):
            session.mount("home.root", entity_key="new")

    def test_a_closed_session_rejects_remounts(self):
        session = ReviewSession(home_manifest())
        handle = session.mount("home.record-list.item", entity_key="e1")
        session.unmount(handle)
        session.close()
        with self.assertRaises(ReviewSessionClosed):
            session.remount("home.record-list.item", entity_key="e1")

class RenderedHtmlAgreesWithTheManifestTests(unittest.TestCase):
    """Generated metadata must agree with what a reviewer actually sees."""

    def test_the_audit_counts_each_rendered_instance(self):
        html_text = (
            '<main data-ui-ref="home.root">'
            '<li data-ui-ref="home.record-list.item">甲</li>'
            '<li data-ui-ref="home.record-list.item">乙</li>'
            "</main>"
        )
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertEqual(audit["instances"]["home.record-list.item"], 2)
        self.assertEqual(audit["instances"]["home.root"], 1)

    def test_an_undeclared_reference_in_the_dom_is_reported(self):
        html_text = '<div data-ui-ref="home.ghost"></div>'
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertEqual(audit["undeclared"], ("home.ghost",))

    def test_a_declared_reference_absent_from_the_dom_is_reported(self):
        html_text = '<main data-ui-ref="home.root"></main>'
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertEqual(audit["missing"], ("home.record-list.item",))

    def test_a_fully_rendered_view_reports_no_discrepancy(self):
        html_text = (
            '<main data-ui-ref="home.root">'
            '<li data-ui-ref="home.record-list.item">甲</li>'
            "</main>"
        )
        audit = audit_rendered_html(home_manifest(), html_text)
        self.assertEqual(audit["undeclared"], ())
        self.assertEqual(audit["missing"], ())

    def test_the_audit_reports_the_manifest_identity_it_checked_against(self):
        manifest = home_manifest()
        audit = audit_rendered_html(manifest, '<main data-ui-ref="home.root"></main>')
        self.assertEqual(audit["ui_map"], manifest["ui_map"])


if __name__ == "__main__":
    unittest.main()


class ReviewSessionPublicSurfaceTests(unittest.TestCase):
    """The review mode must be able to build a panel without reaching inside."""

    def setUp(self):
        self.manifest = home_manifest()
        self.session = ReviewSession(self.manifest)

    def test_mounted_handles_reports_display_order(self):
        first = self.session.mount("home.record-list.item", entity_key="a")
        second = self.session.mount("home.record-list.item", entity_key="b")
        self.assertEqual(self.session.mounted_handles(), (first, second))

    def test_mounted_handles_follows_a_reorder(self):
        first = self.session.mount("home.record-list.item", entity_key="a")
        second = self.session.mount("home.record-list.item", entity_key="b")
        self.session.reorder([second, first])
        self.assertEqual(self.session.mounted_handles(), (second, first))

    def test_mounted_handles_excludes_an_unmounted_instance(self):
        first = self.session.mount("home.record-list.item", entity_key="a")
        self.session.unmount(first)
        self.assertEqual(self.session.mounted_handles(), ())

    def test_ref_of_reports_the_structural_reference(self):
        handle = self.session.mount("home.record-list.item", entity_key="a")
        self.assertEqual(self.session.ref_of(handle), "home.record-list.item")

    def test_unlock_drops_the_selection_without_touching_instances(self):
        handle = self.session.mount("home.record-list.item", entity_key="a")
        self.session.lock(handle)
        self.session.unlock()
        self.assertIsNone(self.session.locked_target())
        self.assertEqual(self.session.mounted_handles(), (handle,))

    def test_unlock_is_a_no_op_when_nothing_is_locked(self):
        self.session.unlock()
        self.assertIsNone(self.session.locked_target())
