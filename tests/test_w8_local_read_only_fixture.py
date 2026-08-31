from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from evaluation.fixtures.w8_local_read_only.v1.fixture_adapters import (
    FIXTURE_ADAPTER_SCHEMA,
    FixtureSuccessAdapter,
    FixtureUnknownBoundary,
    FixtureUnknownBoundaryAdapter,
)
from evaluation.runner.run_w8_local_read_only import (
    MANIFEST,
    run_case,
    run_suite,
)


class W8LocalReadOnlyFixtureTests(unittest.TestCase):
    def test_manifest_declares_two_expected_scenarios(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema"], "zworkbench-w8-local-read-only-fixture/v1")
        self.assertEqual(
            [item["name"] for item in manifest["scenarios"]],
            ["success", "unknown_boundary"],
        )

    def test_success_fixture_completes_with_no_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_case(Path(temporary), "success")

            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["observed"]["orchestration_status"], "completed")
            self.assertEqual(summary["observed"]["owner_run_status"], "completed")
            self.assertEqual(summary["observed"]["semantic_text"], "fixture-ok")
            self.assertTrue(summary["checks"]["recorded_view_present"])
            self.assertEqual(summary["observed"]["effects_count"], 0)
            self.assertTrue(summary["observed"]["adapter_closed"])

    def test_unknown_boundary_fixture_safe_stops_and_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_case(Path(temporary), "unknown_boundary")

            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["expected_outcome"], "expected_fail_closed")
            self.assertEqual(summary["observed"]["orchestration_status"], "expected_fail_closed")
            self.assertEqual(summary["observed"]["owner_run_status"], "safe_stopped")
            self.assertEqual(summary["observed"]["exception_kind"], "FixtureUnknownBoundary")
            self.assertIsNone(summary["observed"]["semantic_text"])
            self.assertTrue(summary["checks"]["unknown_boundary_not_reported_as_success"])
            self.assertTrue(summary["observed"]["adapter_closed"])

    def test_suite_uses_independent_case_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "evidence"
            summary = run_suite(output_dir)

            self.assertEqual(summary["status"], "pass")
            roots = [Path(item["case_root"]) for item in summary["scenarios"]]
            self.assertEqual(len(roots), 2)
            self.assertNotEqual(roots[0], roots[1])
            self.assertNotEqual(roots[0] / "state" / "composition.sqlite3", roots[1] / "state" / "composition.sqlite3")
            self.assertTrue(all((root / "workspace").is_dir() for root in roots))
            self.assertTrue(all((root / "codex-home").is_dir() for root in roots))

    def test_fixture_adapters_have_expected_shape_and_unknown_exception(self) -> None:
        self.assertTrue(FIXTURE_ADAPTER_SCHEMA.endswith("/v1"))
        self.assertTrue(callable(FixtureSuccessAdapter.execute))
        self.assertTrue(callable(FixtureUnknownBoundaryAdapter.execute))
        self.assertTrue(issubclass(FixtureUnknownBoundary, RuntimeError))


if __name__ == "__main__":
    unittest.main()
