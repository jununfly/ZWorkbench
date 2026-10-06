"""Behaviour tests for the UI manifest build entry point.

The seam under test is the build command's observable result: what it leaves in
the artifact store, and whether the existing read-only query path can find it.
Nothing here inspects how the manifests are assembled.

The PRD requires the manifest to be a build artifact rather than something a
test conjures. Until this entry point existed, `write_manifest` was only ever
called from tests, so "the build generates the manifest" was a claim with no
mechanism behind it.
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_build import (
    ROOT_SOURCES,
    build_ui_artifacts,
    served_source_root_and_sources,
)
from zworkbench.ui_manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]


class BuildingTheArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.store = Path(self.enterContext(TemporaryDirectory())) \
            if hasattr(self, "enterContext") else None
        if self.store is None:
            tmp = TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.store = Path(tmp.name)

    def test_the_build_stores_one_manifest_per_view(self):
        result = build_ui_artifacts(REPO_ROOT, self.store)
        self.assertEqual(sorted(result["views"]), ["home", "record-view", "task-detail"])
        self.assertEqual(len(list(self.store.glob("*.json"))), 3)

    def test_a_stored_manifest_is_readable_by_exact_identity(self):
        result = build_ui_artifacts(REPO_ROOT, self.store)
        for view, identity in result["views"].items():
            with self.subTest(view=view):
                found = load_manifest(
                    self.store, ui_map=identity["ui_map"], build=identity["build"]
                )
                self.assertEqual(found["outcome"], "found")

    def test_every_view_shares_one_build_receipt(self):
        """A receipt pins the whole source snapshot, not one module each."""
        result = build_ui_artifacts(REPO_ROOT, self.store)
        builds = {identity["build"] for identity in result["views"].values()}
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds.pop(), result["receipt"]["build"])

    def test_the_receipt_pins_every_source_a_manifest_points_at(self):
        """The expected set comes from the manifests, not from ROOT_SOURCES.

        Comparing the receipt against the very constant that produced it would
        pass by construction: dropping a source would silently move both sides.
        The manifests independently record where each reference is declared, so
        they are the honest source of truth for what must be pinned.
        """
        result = build_ui_artifacts(REPO_ROOT, self.store)
        declared = set()
        for identity in result["views"].values():
            found = load_manifest(
                self.store, ui_map=identity["ui_map"], build=identity["build"]
            )
            for entry in found["manifest"]["refs"]:
                declared.add(entry["source"]["repo_path"])
        pinned = {entry["repo_path"] for entry in result["receipt"]["sources"]}
        self.assertTrue(
            declared <= pinned,
            "sources declared but not pinned: {0}".format(sorted(declared - pinned)),
        )

    def test_a_change_in_shared_machinery_moves_the_build_identity(self):
        """A receipt that ignored shared code would report a stale identity."""
        before = build_ui_artifacts(REPO_ROOT, self.store)["receipt"]["build"]
        shared = REPO_ROOT / "src/zworkbench/ui_ref.py"
        original = shared.read_bytes()
        self.addCleanup(shared.write_bytes, original)
        shared.write_bytes(original + b"\n# build identity probe\n")
        after = build_ui_artifacts(REPO_ROOT, self.store)["receipt"]["build"]
        self.assertNotEqual(before, after)

    def test_rebuilding_unchanged_sources_reproduces_the_same_identity(self):
        first = build_ui_artifacts(REPO_ROOT, self.store)
        second = build_ui_artifacts(REPO_ROOT, self.store)
        self.assertEqual(first["views"], second["views"])
        self.assertEqual(first["receipt"]["build"], second["receipt"]["build"])


class LayoutAgnosticBuildTests(unittest.TestCase):
    """The build must serve identically from a source checkout and from an
    installed wheel (see the 2026-10-06 wheel-layout fix).  A build that
    assumed ``src/zworkbench`` two parents above the package crashed on
    ``pip install`` with FileNotFoundError, so these lock the layout split.
    """

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.store = Path(self.tmp.name) / "store"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_source_checkout_keeps_the_src_prefix(self):
        root, sources = served_source_root_and_sources()
        self.assertTrue((root / "src/zworkbench/ui_declare.py").exists())
        self.assertEqual(sources, ROOT_SOURCES)
        for relative in sources:
            self.assertTrue(relative.startswith("src/zworkbench/"))

    def test_installed_wheel_layout_strips_the_prefix(self):
        """When the declaring modules sit directly under ``root`` (installed
        wheel), ``build_ui_artifacts`` must drop the ``src/zworkbench/`` prefix
        and still produce a valid receipt -- not raise FileNotFoundError.
        """
        pkg = Path(self.tmp.name) / "zworkbench"
        pkg.mkdir()
        for relative in ROOT_SOURCES:
            src = REPO_ROOT / relative
            (pkg / src.name).write_bytes(src.read_bytes())
        # The resolver would treat this flat package as the installed layout.
        self.assertTrue((pkg / "ui_declare.py").exists())

        receipt = build_ui_artifacts(pkg, self.store)["receipt"]
        self.assertIn("build", receipt)
        for entry in receipt["sources"]:
            self.assertNotIn(
                "src/zworkbench/",
                entry["repo_path"],
                "installed layout must not carry the source prefix",
            )
            self.assertTrue((pkg / entry["repo_path"]).is_file())

    def test_installed_layout_receipt_matches_a_real_flat_read(self):
        pkg = Path(self.tmp.name) / "zworkbench"
        pkg.mkdir()
        for relative in ROOT_SOURCES:
            src = REPO_ROOT / relative
            (pkg / src.name).write_bytes(src.read_bytes())
        receipt = build_ui_artifacts(pkg, self.store)["receipt"]
        # Every declared source resolves to a real file under the flat package.
        for entry in receipt["sources"]:
            self.assertEqual(
                entry["content_digest"],
                __import__("hashlib")
                .sha256((pkg / entry["repo_path"]).read_bytes())
                .hexdigest(),
            )



if __name__ == "__main__":
    unittest.main()
