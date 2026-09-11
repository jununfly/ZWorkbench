"""Reference lifecycle and mapping-version compatibility.

A reference is an identity. Visual churn must not change it, a semantic change
must not silently inherit it, and a version the caller cannot produce evidence
for must not be answered from the current manifest.
"""

import unittest

from zworkbench.ui_ref import (
    SourceAnchor,
    UiRefDeclaration,
    UiRefRegistry,
    UiRefValidationError,
    resolve,
)

BUILD = "b" * 64
OTHER_BUILD = "c" * 64


def anchor(symbol="render_home", digest="a" * 64):
    return SourceAnchor(
        repo_path="src/zworkbench/ui_home.py", symbol=symbol, content_digest=digest
    )


def declare(registry, ref, **kwargs):
    kwargs.setdefault("semantic_zh", "语义名")
    kwargs.setdefault("kind", "region")
    kwargs.setdefault("view", "home")
    kwargs.setdefault("source", anchor())
    registry.declare(UiRefDeclaration(ref=ref, **kwargs))
    return registry


def registry_with(*refs, **kwargs):
    registry = UiRefRegistry()
    for ref in refs:
        declare(registry, ref, **kwargs)
    return registry


class VisualChurnTests(unittest.TestCase):
    """1-7-1 — copy, layout and ordering changes must not move an identity."""

    def _manifest(self, semantic_zh, kind, order):
        registry = UiRefRegistry()
        for ref in order:
            declare(registry, ref, semantic_zh=semantic_zh, kind=kind)
        return registry.build_manifest(build=BUILD)

    def test_declaration_order_does_not_change_the_mapping_version(self):
        forward = self._manifest("运行事实", "region", ("home.a", "home.b"))
        reverse = self._manifest("运行事实", "region", ("home.b", "home.a"))
        self.assertEqual(forward["ui_map"], reverse["ui_map"])

    def test_an_accessible_name_change_does_not_change_the_reference(self):
        registry = registry_with("home.run-facts")
        manifest = registry.build_manifest(build=BUILD)
        renamed = registry_with("home.run-facts", accessible_name="运行事实区域")
        self.assertEqual(
            [entry["ref"] for entry in manifest["refs"]],
            [entry["ref"] for entry in renamed.build_manifest(build=BUILD)["refs"]],
        )

    def test_a_semantic_name_change_is_a_semantic_change_and_moves_ui_map(self):
        before = self._manifest("运行事实", "region", ("home.a",))
        after = self._manifest("运行摘要", "region", ("home.a",))
        self.assertNotEqual(before["ui_map"], after["ui_map"])

    def test_a_source_only_change_does_not_change_ui_map(self):
        registry = registry_with("home.a")
        first = registry.build_manifest(build=BUILD)
        moved = UiRefRegistry()
        declare(moved, "home.a", source=anchor(digest="d" * 64))
        self.assertEqual(first["ui_map"], moved.build_manifest(build=BUILD)["ui_map"])


class LifecycleDeclarationTests(unittest.TestCase):
    """1-7-1 — alias, replaced-by and retirement are declared, not inferred."""

    def test_an_alias_records_a_renamed_identity(self):
        registry = UiRefRegistry()
        declare(registry, "home.facts", alias_of=("home.run-facts",))
        entry = registry.build_manifest(build=BUILD)["refs"][0]
        self.assertEqual(entry["alias_of"], ["home.run-facts"])

    def test_a_retired_reference_names_its_replacement(self):
        registry = UiRefRegistry()
        declare(registry, "home.summary")
        declare(registry, "home.facts", retired=True, replaced_by="home.summary")
        refs = {e["ref"]: e for e in registry.build_manifest(build=BUILD)["refs"]}
        self.assertTrue(refs["home.facts"]["retired"])
        self.assertEqual(refs["home.facts"]["replaced_by"], "home.summary")

    def test_lifecycle_metadata_participates_in_the_mapping_version(self):
        plain = registry_with("home.a").build_manifest(build=BUILD)
        aliased = UiRefRegistry()
        declare(aliased, "home.a", alias_of=("home.old",))
        self.assertNotEqual(plain["ui_map"], aliased.build_manifest(build=BUILD)["ui_map"])

    def test_a_reference_cannot_alias_itself(self):
        registry = UiRefRegistry()
        declare(registry, "home.a", alias_of=("home.a",))
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build=BUILD)

    def test_two_references_cannot_claim_the_same_alias(self):
        registry = UiRefRegistry()
        declare(registry, "home.a", alias_of=("home.old",))
        declare(registry, "home.b", alias_of=("home.old",))
        with self.assertRaises(UiRefValidationError) as caught:
            registry.build_manifest(build=BUILD)
        self.assertIn("home.old", str(caught.exception))

    def test_an_alias_cannot_collide_with_a_live_reference(self):
        registry = UiRefRegistry()
        declare(registry, "home.a")
        declare(registry, "home.b", alias_of=("home.a",))
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build=BUILD)

    def test_a_replacement_target_must_exist(self):
        registry = UiRefRegistry()
        declare(registry, "home.a", retired=True, replaced_by="home.ghost")
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build=BUILD)

    def test_a_replacement_chain_cannot_form_a_cycle(self):
        registry = UiRefRegistry()
        declare(registry, "home.a", retired=True, replaced_by="home.b")
        declare(registry, "home.b", retired=True, replaced_by="home.a")
        with self.assertRaises(UiRefValidationError) as caught:
            registry.build_manifest(build=BUILD)
        self.assertIn("cycle", str(caught.exception).lower())

    def test_a_replacement_cannot_point_at_itself(self):
        registry = UiRefRegistry()
        declare(registry, "home.a", retired=True, replaced_by="home.a")
        with self.assertRaises(UiRefValidationError):
            registry.build_manifest(build=BUILD)

    def test_a_replacement_requires_retirement(self):
        """Rejected at declaration time: a live reference with a replacement is
        contradictory, and failing early beats failing at build."""
        registry = UiRefRegistry()
        declare(registry, "home.b")
        with self.assertRaises(UiRefValidationError):
            declare(registry, "home.a", replaced_by="home.b")


class MappingLineageTests(unittest.TestCase):
    """1-7-2 — the current version points at exactly one previous version."""

    def test_a_manifest_records_the_previous_mapping_version(self):
        previous = registry_with("home.a").build_manifest(build=BUILD)
        current = registry_with("home.a", "home.b").build_manifest(
            build=BUILD, previous_ui_map=previous["ui_map"]
        )
        self.assertEqual(current["previous_ui_map"], previous["ui_map"])

    def test_a_manifest_without_lineage_declares_it_explicitly(self):
        self.assertIsNone(registry_with("home.a").build_manifest(build=BUILD)["previous_ui_map"])

    def test_lineage_does_not_participate_in_the_mapping_version(self):
        without = registry_with("home.a").build_manifest(build=BUILD)
        with_lineage = registry_with("home.a").build_manifest(
            build=BUILD, previous_ui_map="f" * 64
        )
        self.assertEqual(without["ui_map"], with_lineage["ui_map"])

    def test_a_manifest_cannot_name_itself_as_its_predecessor(self):
        manifest = registry_with("home.a").build_manifest(build=BUILD)
        with self.assertRaises(UiRefValidationError):
            registry_with("home.a").build_manifest(
                build=BUILD, previous_ui_map=manifest["ui_map"]
            )

    def test_a_malformed_predecessor_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            registry_with("home.a").build_manifest(build=BUILD, previous_ui_map="nope")


class ResolutionOutcomeTests(unittest.TestCase):
    """1-7-3 — every cross-version outcome is explicit."""

    def setUp(self):
        self.previous = registry_with("home.facts").build_manifest(build=BUILD)
        current = UiRefRegistry()
        declare(current, "home.run-facts", alias_of=("home.facts",))
        declare(current, "home.legacy-panel", retired=True, replaced_by="home.run-facts")
        self.current = current.build_manifest(
            build=BUILD, previous_ui_map=self.previous["ui_map"]
        )

    def test_a_current_reference_is_found(self):
        result = resolve(self.current, "home.run-facts", ui_map=self.current["ui_map"])
        self.assertEqual(result["outcome"], "found")

    def test_an_aliased_reference_migrates_to_the_same_identity(self):
        result = resolve(
            self.current,
            "home.facts",
            ui_map=self.previous["ui_map"],
            previous_manifest=self.previous,
        )
        self.assertEqual(result["outcome"], "migrated")
        self.assertEqual(result["ref"], "home.run-facts")
        self.assertEqual(result["identity"], "same-semantics")

    def test_a_retired_reference_is_never_reported_as_the_same_identity(self):
        result = resolve(
            self.current, "home.legacy-panel", ui_map=self.current["ui_map"]
        )
        self.assertEqual(result["outcome"], "retired")
        self.assertEqual(result["replacement"], "home.run-facts")
        self.assertEqual(result["identity"], "different-semantics")
        self.assertNotEqual(result.get("ref"), "home.run-facts")

    def test_an_older_version_is_incompatible(self):
        result = resolve(self.current, "home.facts", ui_map="9" * 64)
        self.assertEqual(result["outcome"], "incompatible")
        self.assertNotIn("source", result)

    def test_the_previous_version_without_evidence_is_incompatible(self):
        result = resolve(self.current, "home.facts", ui_map=self.previous["ui_map"])
        self.assertEqual(result["outcome"], "incompatible")
        self.assertEqual(result["reason"], "previous-manifest-required")

    def test_a_wrong_previous_manifest_is_refused(self):
        decoy = registry_with("home.other").build_manifest(build=OTHER_BUILD)
        result = resolve(
            self.current,
            "home.facts",
            ui_map=self.previous["ui_map"],
            previous_manifest=decoy,
        )
        self.assertEqual(result["outcome"], "incompatible")

    def test_an_unchanged_reference_resolves_within_the_window(self):
        previous = registry_with("home.stable", "home.gone").build_manifest(build=BUILD)
        current = registry_with("home.stable").build_manifest(
            build=BUILD, previous_ui_map=previous["ui_map"]
        )
        result = resolve(
            current, "home.stable", ui_map=previous["ui_map"], previous_manifest=previous
        )
        self.assertEqual(result["outcome"], "found")

    def test_a_dropped_reference_without_retirement_is_not_found(self):
        previous = registry_with("home.stable", "home.gone").build_manifest(build=BUILD)
        current = registry_with("home.stable").build_manifest(
            build=BUILD, previous_ui_map=previous["ui_map"]
        )
        result = resolve(
            current, "home.gone", ui_map=previous["ui_map"], previous_manifest=previous
        )
        self.assertEqual(result["outcome"], "not-found")

    def test_a_reference_whose_semantics_changed_is_never_silently_reused(self):
        previous = registry_with("home.a", semantic_zh="运行事实").build_manifest(build=BUILD)
        current = registry_with("home.a", semantic_zh="账单摘要").build_manifest(
            build=BUILD, previous_ui_map=previous["ui_map"]
        )
        result = resolve(
            current, "home.a", ui_map=previous["ui_map"], previous_manifest=previous
        )
        self.assertEqual(result["outcome"], "incompatible")
        self.assertEqual(result["reason"], "semantics-changed")

    def test_no_outcome_ever_falls_back_to_a_css_guess(self):
        for ui_map in ("9" * 64, self.previous["ui_map"]):
            result = resolve(self.current, "home.facts", ui_map=ui_map)
            self.assertNotIn("selector", result)
            self.assertNotIn("css", repr(result).lower())


class CompatibilityWindowTests(unittest.TestCase):
    """1-7-4 — a synthesised previous version proves the window is one wide."""

    def setUp(self):
        self.v1 = registry_with("home.facts").build_manifest(build=BUILD)
        v2 = UiRefRegistry()
        declare(v2, "home.run-facts", alias_of=("home.facts",))
        self.v2 = v2.build_manifest(build=BUILD, previous_ui_map=self.v1["ui_map"])
        v3 = UiRefRegistry()
        declare(v3, "home.run-facts")
        self.v3 = v3.build_manifest(build=BUILD, previous_ui_map=self.v2["ui_map"])

    def test_the_adjacent_previous_version_is_honoured(self):
        result = resolve(
            self.v2, "home.facts", ui_map=self.v1["ui_map"], previous_manifest=self.v1
        )
        self.assertEqual(result["outcome"], "migrated")

    def test_a_two_step_older_version_is_incompatible_even_with_evidence(self):
        result = resolve(
            self.v3, "home.facts", ui_map=self.v1["ui_map"], previous_manifest=self.v1
        )
        self.assertEqual(result["outcome"], "incompatible")
        self.assertEqual(result["reason"], "outside-compatibility-window")

    def test_an_alias_is_not_inherited_across_two_versions(self):
        self.assertNotIn(
            "home.facts",
            [alias for e in self.v3["refs"] for alias in (e["alias_of"] or ())],
        )


if __name__ == "__main__":
    unittest.main()
