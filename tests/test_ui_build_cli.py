"""Behavior tests for the `ui-build` command.

The seam under test is the command's observable result and, crucially, that the
artifacts it writes are exactly what the read-only `ui-ref` query path reads.
That linkage is the R1 closed loop: `ui-build` produces the stored manifest a
review token's ref/ui_map/build resolves against, so the AI side (token ->
code) is reachable without starting a business run.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.cli import CLI_SCHEMA, main
from zworkbench.ui_manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


class UiBuildCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_the_command_reports_the_expected_shape(self):
        code, payload = run_cli([
            "ui-build", "--root", str(REPO_ROOT), "--store", str(self.store),
        ])
        self.assertEqual(code, 0)
        self.assertEqual(payload["schema"], CLI_SCHEMA)
        self.assertEqual(payload["command"], "ui-build")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(
            sorted(payload["views"]), ["home", "record-view", "task-detail"]
        )

    def test_the_command_stores_one_manifest_per_view(self):
        _, payload = run_cli([
            "ui-build", "--root", str(REPO_ROOT), "--store", str(self.store),
        ])
        self.assertEqual(len(list(self.store.glob("*.json"))), 3)
        # Every view is stored under its own ui_map.build identity.
        for identity in payload["views"].values():
            found = load_manifest(
                self.store, ui_map=identity["ui_map"], build=identity["build"]
            )
            self.assertEqual(found["outcome"], "found")

    def test_the_command_reports_the_shared_build_receipt(self):
        _, payload = run_cli([
            "ui-build", "--root", str(REPO_ROOT), "--store", str(self.store),
        ])
        builds = {identity["build"] for identity in payload["views"].values()}
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds.pop(), payload["build"])

    def test_the_built_artifacts_are_resolvable_through_ui_ref(self):
        """The R1 loop: build, then resolve a real reference via ui-ref."""

        _, payload = run_cli([
            "ui-build", "--root", str(REPO_ROOT), "--store", str(self.store),
        ])

        # Pick the home view identity and a real reference from its manifest,
        # exactly as a review token would carry ref/ui_map/build.
        home = payload["views"]["home"]
        manifest = load_manifest(
            self.store, ui_map=home["ui_map"], build=home["build"]
        )["manifest"]
        ref = manifest["refs"][0]["ref"]

        code, resolved = run_cli([
            "ui-ref", "--store", str(self.store), "resolve", ref,
            "--ui-map", home["ui_map"], "--build", home["build"],
        ])
        self.assertEqual(code, 0)
        self.assertEqual(resolved["result"]["outcome"], "found")
        self.assertEqual(resolved["result"]["ref"], ref)
        self.assertIn("source", resolved["result"])

    def test_the_help_text_is_available_without_a_store(self):
        with self.assertRaises(SystemExit) as raised:
            run_cli(["ui-build", "--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
