"""Behavior tests for the build receipt and the local manifest artifact."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_manifest import (
    build_receipt,
    load_manifest,
    locate_source,
    write_manifest,
)
from zworkbench.ui_ref import (
    SourceAnchor,
    UiRefDeclaration,
    UiRefRegistry,
    UiRefValidationError,
)


def sample_manifest(build: str):
    registry = UiRefRegistry()
    registry.declare(
        UiRefDeclaration(
            ref="home.root",
            semantic_zh="工作台首页",
            kind="region",
            view="home",
            source=SourceAnchor(
                repo_path="ui/home.py",
                symbol="render_home",
                content_digest="a" * 64,
            ),
        )
    )
    return registry.build_manifest(build=build)


class BuildReceiptTests(unittest.TestCase):
    """The receipt pins the source snapshot, including uncommitted edits."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "ui").mkdir()
        (self.root / "ui" / "home.py").write_text("HOME = 1\n", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_the_receipt_is_a_lowercase_sha256_digest(self):
        receipt = build_receipt(self.root, ["ui/home.py"])
        self.assertRegex(receipt["build"], r"^[0-9a-f]{64}$")

    def test_the_same_sources_produce_the_same_receipt(self):
        first = build_receipt(self.root, ["ui/home.py"])
        second = build_receipt(self.root, ["ui/home.py"])
        self.assertEqual(first["build"], second["build"])

    def test_an_uncommitted_edit_changes_the_receipt(self):
        before = build_receipt(self.root, ["ui/home.py"])
        (self.root / "ui" / "home.py").write_text("HOME = 2\n", encoding="utf-8")
        after = build_receipt(self.root, ["ui/home.py"])
        self.assertNotEqual(before["build"], after["build"])

    def test_the_receipt_records_no_local_absolute_path(self):
        receipt = build_receipt(self.root, ["ui/home.py"])
        serialised = json.dumps(receipt, ensure_ascii=False)
        self.assertNotIn(str(self.root), serialised)
        for entry in receipt["sources"]:
            self.assertFalse(entry["repo_path"].startswith("/"))

    def test_an_absolute_source_path_is_rejected(self):
        with self.assertRaises(UiRefValidationError):
            build_receipt(self.root, [str(self.root / "ui" / "home.py")])

    def test_a_missing_source_file_fails_loudly(self):
        with self.assertRaises(OSError):
            build_receipt(self.root, ["ui/absent.py"])

    def test_adding_a_source_file_changes_the_receipt(self):
        (self.root / "ui" / "record.py").write_text("RECORD = 1\n", encoding="utf-8")
        one = build_receipt(self.root, ["ui/home.py"])
        two = build_receipt(self.root, ["ui/home.py", "ui/record.py"])
        self.assertNotEqual(one["build"], two["build"])

    def test_source_order_does_not_change_the_receipt(self):
        (self.root / "ui" / "record.py").write_text("RECORD = 1\n", encoding="utf-8")
        forward = build_receipt(self.root, ["ui/home.py", "ui/record.py"])
        reverse = build_receipt(self.root, ["ui/record.py", "ui/home.py"])
        self.assertEqual(forward["build"], reverse["build"])

class ManifestArtifactQueryTests(unittest.TestCase):
    """Queries are read-only and must never substitute a different version."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_stored_manifest_is_returned_by_its_own_identity(self):
        manifest = sample_manifest("b" * 64)
        write_manifest(self.store, manifest)
        loaded = load_manifest(self.store, ui_map=manifest["ui_map"], build=manifest["build"])
        self.assertEqual(loaded["outcome"], "found")
        self.assertEqual(loaded["manifest"]["ui_map"], manifest["ui_map"])

    def test_an_absent_artifact_is_reported_as_manifest_missing(self):
        manifest = sample_manifest("b" * 64)
        loaded = load_manifest(self.store, ui_map=manifest["ui_map"], build=manifest["build"])
        self.assertEqual(loaded["outcome"], "manifest-missing")
        self.assertNotIn("manifest", loaded)

    def test_a_current_manifest_does_not_stand_in_for_a_different_ui_map(self):
        stored = sample_manifest("b" * 64)
        write_manifest(self.store, stored)
        loaded = load_manifest(self.store, ui_map="0" * 64, build=stored["build"])
        self.assertEqual(loaded["outcome"], "manifest-missing")
        self.assertNotIn("manifest", loaded)

    def test_a_matching_ui_map_with_a_different_build_is_not_substituted(self):
        stored = sample_manifest("b" * 64)
        write_manifest(self.store, stored)
        loaded = load_manifest(self.store, ui_map=stored["ui_map"], build="c" * 64)
        self.assertEqual(loaded["outcome"], "manifest-missing")

    def test_two_builds_of_the_same_semantics_are_both_retrievable(self):
        first = sample_manifest("b" * 64)
        second = sample_manifest("c" * 64)
        self.assertEqual(first["ui_map"], second["ui_map"])
        write_manifest(self.store, first)
        write_manifest(self.store, second)
        for manifest in (first, second):
            loaded = load_manifest(
                self.store, ui_map=manifest["ui_map"], build=manifest["build"]
            )
            self.assertEqual(loaded["outcome"], "found")
            self.assertEqual(loaded["manifest"]["build"], manifest["build"])

    def test_a_stored_artifact_round_trips_without_losing_declarations(self):
        manifest = sample_manifest("b" * 64)
        write_manifest(self.store, manifest)
        loaded = load_manifest(self.store, ui_map=manifest["ui_map"], build=manifest["build"])
        self.assertEqual(loaded["manifest"]["refs"], manifest["refs"])

class SourceLocationTests(unittest.TestCase):
    """Code location verifies content identity before claiming a hit."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "ui").mkdir()
        self.source = self.root / "ui" / "home.py"
        self.source.write_text("def render_home():\n    return 1\n", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def _manifest_for_current_source(self):
        import hashlib

        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        registry = UiRefRegistry()
        registry.declare(
            UiRefDeclaration(
                ref="home.root",
                semantic_zh="工作台首页",
                kind="region",
                view="home",
                source=SourceAnchor(
                    repo_path="ui/home.py",
                    symbol="render_home",
                    content_digest=digest,
                ),
            )
        )
        return registry.build_manifest(build="b" * 64)

    def test_matching_source_content_locates_the_declaration(self):
        manifest = self._manifest_for_current_source()
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertEqual(located["outcome"], "found")
        self.assertEqual(located["symbol"], "render_home")
        self.assertEqual(located["repo_path"], "ui/home.py")

    def test_a_changed_source_file_is_a_source_mismatch(self):
        manifest = self._manifest_for_current_source()
        self.source.write_text("def render_home():\n    return 2\n", encoding="utf-8")
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertEqual(located["outcome"], "source-mismatch")

    def test_a_mismatch_keeps_the_historical_provenance_hint(self):
        manifest = self._manifest_for_current_source()
        self.source.write_text("changed\n", encoding="utf-8")
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertEqual(located["repo_path"], "ui/home.py")
        self.assertEqual(located["symbol"], "render_home")

    def test_a_mismatch_does_not_claim_a_precise_current_hit(self):
        manifest = self._manifest_for_current_source()
        self.source.write_text("changed\n", encoding="utf-8")
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertNotEqual(located["outcome"], "found")
        self.assertNotIn("line", located)

    def test_a_deleted_source_file_is_a_source_mismatch_not_a_crash(self):
        manifest = self._manifest_for_current_source()
        self.source.unlink()
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertEqual(located["outcome"], "source-mismatch")

    def test_an_undeclared_reference_is_not_found(self):
        manifest = self._manifest_for_current_source()
        located = locate_source(manifest, "home.ghost", root=self.root)
        self.assertEqual(located["outcome"], "not-found")

    def test_location_never_returns_a_local_absolute_path(self):
        manifest = self._manifest_for_current_source()
        located = locate_source(manifest, "home.root", root=self.root)
        self.assertNotIn(str(self.root), json.dumps(located, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
