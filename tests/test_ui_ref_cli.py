"""Behavior tests for the read-only ui-ref command."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.cli import CLI_SCHEMA, main
from zworkbench.ui_manifest import write_manifest
from zworkbench.ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry


def stored_manifest(store: Path):
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
    manifest = registry.build_manifest(build="b" * 64)
    write_manifest(store, manifest)
    return manifest


def run_cli(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


class UiRefResolveCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name)
        self.manifest = stored_manifest(self.store)
        self.addCleanup(self._tmp.cleanup)

    def test_resolving_a_declared_reference_succeeds(self):
        code, payload = run_cli([
            "ui-ref", "--store", str(self.store),
            "resolve", "home.root",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(code, 0)
        self.assertEqual(payload["schema"], CLI_SCHEMA)
        self.assertEqual(payload["command"], "ui-ref")
        self.assertEqual(payload["result"]["outcome"], "found")
        self.assertEqual(payload["result"]["semantic_zh"], "工作台首页")

    def test_a_missing_artifact_reports_manifest_missing_and_a_nonzero_exit(self):
        code, payload = run_cli([
            "ui-ref", "--store", str(self.store),
            "resolve", "home.root",
            "--ui-map", "0" * 64,
            "--build", self.manifest["build"],
        ])
        self.assertEqual(payload["result"]["outcome"], "manifest-missing")
        self.assertNotEqual(code, 0)

    def test_an_unknown_reference_reports_not_found_and_a_nonzero_exit(self):
        code, payload = run_cli([
            "ui-ref", "--store", str(self.store),
            "resolve", "home.ghost",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(payload["result"]["outcome"], "not-found")
        self.assertNotEqual(code, 0)

    def test_identity_reports_the_stored_artifact_identity(self):
        code, payload = run_cli([
            "ui-ref", "--store", str(self.store), "identity",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"]["ui_map"], self.manifest["ui_map"])
        self.assertEqual(payload["result"]["build"], self.manifest["build"])
        self.assertEqual(payload["result"]["declared"], 1)

    def test_list_reports_the_declared_semantic_units(self):
        code, payload = run_cli([
            "ui-ref", "--store", str(self.store), "list",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(code, 0)
        self.assertEqual(
            payload["result"]["refs"],
            [{"ref": "home.root", "semantic_zh": "工作台首页", "kind": "region", "view": "home"}],
        )

    def test_the_query_never_reports_a_local_absolute_path(self):
        _, payload = run_cli([
            "ui-ref", "--store", str(self.store), "list",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertNotIn(str(self.store), json.dumps(payload, ensure_ascii=False))

    def test_the_query_leaves_the_artifact_directory_unchanged(self):
        before = sorted(path.name for path in self.store.iterdir())
        run_cli([
            "ui-ref", "--store", str(self.store), "identity",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(sorted(path.name for path in self.store.iterdir()), before)

    def test_the_query_creates_no_owner_database(self):
        run_cli([
            "ui-ref", "--store", str(self.store), "identity",
            "--ui-map", self.manifest["ui_map"],
            "--build", self.manifest["build"],
        ])
        self.assertEqual(list(self.store.glob("*.sqlite")), [])
        self.assertEqual(list(self.store.glob("*.db")), [])

    def test_both_identity_halves_are_required(self):
        with self.assertRaises(SystemExit):
            run_cli([
                "ui-ref", "--store", str(self.store),
                "resolve", "home.root",
                "--ui-map", self.manifest["ui_map"],
            ])

    def test_the_help_text_is_available_without_a_stored_artifact(self):
        with self.assertRaises(SystemExit) as raised:
            run_cli(["ui-ref", "--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
