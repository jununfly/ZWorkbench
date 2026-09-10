"""Behavior tests for the UI reference registry and its generated manifest."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_ref import (
    SourceAnchor,
    UiRefDeclaration,
    UiRefRegistry,
    UiRefValidationError,
    UI_REF_SCHEMA,
    resolve,
)


def anchor(symbol: str) -> SourceAnchor:
    return SourceAnchor(
        repo_path="src/zworkbench/ui/home.py",
        symbol=symbol,
        content_digest="a" * 64,
    )


class DeclaringASemanticElementTests(unittest.TestCase):
    def test_declare_returns_the_reference_for_the_render_layer_to_inline(self):
        registry = UiRefRegistry()
        ref = registry.declare(
            UiRefDeclaration(
                ref="home.root",
                semantic_zh="工作台首页",
                kind="region",
                view="home",
                source=anchor("render_home"),
            )
        )
        self.assertEqual(ref, "home.root")

    def test_a_duplicate_declaration_is_rejected(self):
        registry = UiRefRegistry()
        first = UiRefDeclaration(
            ref="home.root",
            semantic_zh="工作台首页",
            kind="region",
            view="home",
            source=anchor("render_home"),
        )
        second = UiRefDeclaration(
            ref="home.root",
            semantic_zh="另一个语义",
            kind="region",
            view="home",
            source=anchor("render_other"),
        )
        registry.declare(first)
        with self.assertRaises(UiRefValidationError):
            registry.declare(second)

    def test_a_rejected_duplicate_does_not_replace_the_original_declaration(self):
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
        try:
            registry.declare(
                UiRefDeclaration(
                    ref="home.root",
                    semantic_zh="冒充者",
                    kind="region",
                    view="home",
                    source=anchor("render_other"),
                )
            )
        except UiRefValidationError:
            pass
        self.assertEqual(registry.declaration("home.root").semantic_zh, "工作台首页")


class ReferenceNameContractTests(unittest.TestCase):
    """The spec fixes ref names: 1-128 ASCII chars, lowercase-letter start,
    dot-separated segments of lowercase letters, digits and hyphens."""

    def _declare(self, ref: str) -> str:
        return UiRefRegistry().declare(
            UiRefDeclaration(
                ref=ref,
                semantic_zh="语义名",
                kind="region",
                view="home",
                source=anchor("render"),
            )
        )

    def test_a_dotted_lowercase_reference_is_accepted(self):
        self.assertEqual(self._declare("home.record-list.item"), "home.record-list.item")

    def test_an_uppercase_reference_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            self._declare("Home.Root")

    def test_a_reference_starting_with_a_digit_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            self._declare("1home.root")

    def test_a_reference_with_an_empty_segment_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            self._declare("home..root")

    def test_a_reference_with_a_non_ascii_character_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            self._declare("home.首页")

    def test_a_reference_longer_than_128_characters_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            self._declare("home." + "a" * 124)

    def test_a_reference_of_exactly_128_characters_is_accepted(self):
        ref = "home." + "a" * 123
        self.assertEqual(len(ref), 128)
        self.assertEqual(self._declare(ref), ref)


class SourceAnchorContractTests(unittest.TestCase):
    """Code provenance must stay repository-relative and content-addressed."""

    def test_an_absolute_repo_path_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            SourceAnchor(
                repo_path="/Users/someone/repo/src/home.py",
                symbol="render_home",
                content_digest="a" * 64,
            )

    def test_a_digest_that_is_not_a_lowercase_sha256_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            SourceAnchor(
                repo_path="src/zworkbench/ui/home.py",
                symbol="render_home",
                content_digest="A" * 64,
            )

    def test_a_truncated_digest_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            SourceAnchor(
                repo_path="src/zworkbench/ui/home.py",
                symbol="render_home",
                content_digest="abc123",
            )


def home_registry() -> UiRefRegistry:
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
            ref="home.record-list",
            semantic_zh="工作记录列表",
            kind="list",
            view="home",
            source=anchor("render_record_list"),
        )
    )
    return registry


class ManifestGenerationTests(unittest.TestCase):
    def test_the_manifest_carries_the_schema_and_every_declaration(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        self.assertEqual(manifest["schema"], UI_REF_SCHEMA)
        self.assertEqual(
            [entry["ref"] for entry in manifest["refs"]],
            ["home.record-list", "home.root"],
        )

    def test_the_same_declarations_produce_the_same_ui_map(self):
        first = home_registry().build_manifest(build="b" * 64)
        second = home_registry().build_manifest(build="b" * 64)
        self.assertEqual(first["ui_map"], second["ui_map"])

    def test_the_ui_map_is_a_lowercase_sha256_digest(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        self.assertRegex(manifest["ui_map"], r"^[0-9a-f]{64}$")

    def test_changing_a_semantic_name_changes_the_ui_map(self):
        baseline = home_registry().build_manifest(build="b" * 64)
        changed = UiRefRegistry()
        changed.declare(
            UiRefDeclaration(
                ref="home.root",
                semantic_zh="工作台概览",
                kind="region",
                view="home",
                source=anchor("render_home"),
            )
        )
        changed.declare(
            UiRefDeclaration(
                ref="home.record-list",
                semantic_zh="工作记录列表",
                kind="list",
                view="home",
                source=anchor("render_record_list"),
            )
        )
        self.assertNotEqual(baseline["ui_map"], changed.build_manifest(build="b" * 64)["ui_map"])

    def test_a_new_build_receipt_does_not_change_the_ui_map(self):
        """A comment-only source change must not invalidate every feedback token."""
        first = home_registry().build_manifest(build="b" * 64)
        second = home_registry().build_manifest(build="c" * 64)
        self.assertNotEqual(first["build"], second["build"])
        self.assertEqual(first["ui_map"], second["ui_map"])

    def test_the_manifest_records_the_build_receipt_it_was_generated_with(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        self.assertEqual(manifest["build"], "b" * 64)

    def test_a_build_receipt_that_is_not_a_digest_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            home_registry().build_manifest(build="not-a-digest")


class ParentRelationshipTests(unittest.TestCase):
    """Broken relationships must fail the build, not ship in the manifest."""

    def test_a_declared_parent_is_accepted(self):
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
                ref="home.record-list",
                semantic_zh="工作记录列表",
                kind="list",
                view="home",
                source=anchor("render_record_list"),
                parent="home.root",
            )
        )
        manifest = registry.build_manifest(build="b" * 64)
        parents = {entry["ref"]: entry["parent"] for entry in manifest["refs"]}
        self.assertEqual(parents["home.record-list"], "home.root")
        self.assertIsNone(parents["home.root"])

    def test_a_manifest_with_an_undeclared_parent_is_rejected(self):
        registry = UiRefRegistry()
        registry.declare(
            UiRefDeclaration(
                ref="home.record-list",
                semantic_zh="工作记录列表",
                kind="list",
                view="home",
                source=anchor("render_record_list"),
                parent="home.ghost",
            )
        )
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build="b" * 64)

    def test_a_declaration_that_parents_itself_is_rejected(self):
        registry = UiRefRegistry()
        registry.declare(
            UiRefDeclaration(
                ref="home.root",
                semantic_zh="工作台首页",
                kind="region",
                view="home",
                source=anchor("render_home"),
                parent="home.root",
            )
        )
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build="b" * 64)

    def test_a_parent_cycle_is_rejected(self):
        registry = UiRefRegistry()
        registry.declare(
            UiRefDeclaration(
                ref="home.first",
                semantic_zh="甲区域",
                kind="region",
                view="home",
                source=anchor("render_first"),
                parent="home.second",
            )
        )
        registry.declare(
            UiRefDeclaration(
                ref="home.second",
                semantic_zh="乙区域",
                kind="region",
                view="home",
                source=anchor("render_second"),
                parent="home.first",
            )
        )
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build="b" * 64)

    def test_validate_reports_every_broken_relationship_before_the_build(self):
        registry = UiRefRegistry()
        registry.declare(
            UiRefDeclaration(
                ref="home.record-list",
                semantic_zh="工作记录列表",
                kind="list",
                view="home",
                source=anchor("render_record_list"),
                parent="home.ghost",
            )
        )
        problems = registry.validate()
        self.assertEqual(len(problems), 1)
        self.assertIn("home.ghost", problems[0])


class ResolvingAReferenceTests(unittest.TestCase):
    """Resolution returns the structural/code result only, and never guesses."""

    def test_a_declared_reference_resolves_to_its_code_declaration(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        result = resolve(manifest, "home.root", ui_map=manifest["ui_map"])
        self.assertEqual(result["outcome"], "found")
        self.assertEqual(result["semantic_zh"], "工作台首页")
        self.assertEqual(result["source"]["symbol"], "render_home")

    def test_an_unknown_reference_is_reported_not_guessed(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        result = resolve(manifest, "home.ghost", ui_map=manifest["ui_map"])
        self.assertEqual(result["outcome"], "not-found")
        self.assertNotIn("source", result)

    def test_a_mismatched_ui_map_is_incompatible_rather_than_silently_substituted(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        result = resolve(manifest, "home.root", ui_map="0" * 64)
        self.assertEqual(result["outcome"], "incompatible")
        self.assertNotIn("source", result)

    def test_an_incompatible_result_does_not_leak_the_current_declaration(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        result = resolve(manifest, "home.root", ui_map="0" * 64)
        self.assertNotIn("semantic_zh", result)

    def test_resolution_never_returns_a_local_absolute_path(self):
        manifest = home_registry().build_manifest(build="b" * 64)
        result = resolve(manifest, "home.root", ui_map=manifest["ui_map"])
        self.assertFalse(result["source"]["repo_path"].startswith("/"))


if __name__ == "__main__":
    unittest.main()
