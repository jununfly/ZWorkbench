"""Public seam tests for the portable UI reference runtime skill."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_manifest import locate_source
from zworkbench.ui_ref import resolve
from zworkbench.ui_runtime import audit_rendered_html, render_attributes
from zworkbench.ui_token import (
    build_deep_link,
    build_token,
    parse_deep_link,
    parse_token,
)
from ui_reference_support import runtime_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SKILL = REPO_ROOT / "skills" / "ui-reference-runtime"
RUNTIME_STATUS = RUNTIME_SKILL / "scripts" / "runtime_status.py"
PROFILE = (
    REPO_ROOT
    / "skills"
    / "ui-reference-protocol"
    / "examples"
    / "minimal-profile.json"
)


class RuntimeSkillPackagingTests(unittest.TestCase):
    def test_runtime_skill_is_project_neutral_and_short(self):
        skill = (RUNTIME_SKILL / "SKILL.md").read_text(encoding="utf-8")

        self.assertLessEqual(len(skill.splitlines()), 100)
        self.assertIn("references/runtime-contract.md", skill)
        self.assertNotIn("ZWorkbench", skill)
        self.assertNotIn("zworkbench", skill.lower())

    def test_runtime_status_accepts_a_profile_and_static_closure_evidence(self):
        evidence = runtime_evidence(PROFILE)
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "implemented")
        self.assertEqual(report["verification"], "static-closure")
        self.assertFalse(report["complete"])

    def test_runtime_status_accepts_full_runtime_only_when_every_runtime_gate_is_verified(self):
        evidence = runtime_evidence(
            PROFILE,
            scope="full-runtime",
            runtime_gates={
                "dynamic-session": "verified",
                "interaction": "verified",
                "teardown": "verified",
                "coverage-matrix": "verified",
            },
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "implemented")
        self.assertEqual(report["verification"], "full-runtime")
        self.assertTrue(report["complete"])

    def test_runtime_status_preserves_unknown_when_a_full_runtime_gate_is_missing(self):
        evidence = runtime_evidence(
            PROFILE,
            scope="full-runtime",
            runtime_gates={
                "dynamic-session": "verified",
                "interaction": "unknown",
                "teardown": "verified",
                "coverage-matrix": "verified",
            },
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["complete"])
        self.assertIn("interaction", report["uncovered_items"])

    def test_runtime_status_holds_when_rendered_markup_has_an_undeclared_reference(self):
        evidence = runtime_evidence(
            PROFILE, rendered={"declared": 2, "undeclared": 1}
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "HOLD")

    def test_runtime_status_preserves_unknown_when_browser_evidence_is_missing(self):
        evidence = runtime_evidence(PROFILE, browser="unknown")
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")

    def test_runtime_status_preserves_unknown_when_a_required_host_capability_is_missing(self):
        evidence = runtime_evidence(
            PROFILE, host_capabilities=["rendered-surface", "manifest-artifact"]
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["reason"], "host-capability-evidence-missing")
        self.assertIn("source-provenance", report["uncovered_items"])

    def test_runtime_status_preserves_unknown_when_historical_artifact_is_missing(self):
        evidence = runtime_evidence(PROFILE, artifact="missing")
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")

    def test_runtime_status_holds_when_the_profile_is_only_schema_shaped(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile.json"
            profile.write_text('{"schema":"ui-reference-profile/v1"}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(RUNTIME_STATUS), str(profile)],
                input=json.dumps(runtime_evidence(profile)),
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "HOLD")

    def test_runtime_status_checks_unsafe_evidence_before_unknown_capabilities(self):
        evidence = runtime_evidence(
            PROFILE, browser="unknown", side_effects="remote-write"
        )

        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "HOLD")

    def test_runtime_status_returns_hold_for_wrongly_typed_evidence(self):
        evidence = runtime_evidence(PROFILE)
        evidence["browser"] = []

        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "HOLD")

    def test_runtime_status_holds_for_duplicate_evidence_fields(self):
        evidence = runtime_evidence(PROFILE)
        encoded = json.dumps(evidence, separators=(",", ":"))
        encoded = encoded.replace(
            '"browser":"verified"',
            '"browser":"verified","browser":"verified"',
            1,
        )

        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=encoded,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "evidence-json-invalid")

    def test_runtime_status_preserves_explicit_lifecycle_and_resolution_outcomes(self):
        for status in (
            "target",
            "blocked",
            "migrated",
            "retired",
            "incompatible",
            "source-mismatch",
        ):
            with self.subTest(status=status):
                evidence = runtime_evidence(PROFILE, status=status)
                result = subprocess.run(
                    [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
                    input=json.dumps(evidence),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], status)
                self.assertEqual(report["reason"], "evidence-is-not-complete")

    def test_runtime_status_holds_when_manifest_or_token_schema_identity_changes(self):
        for field, value in (
            ("manifest_schema", "ui-ref-manifest/v2"),
            ("token_schema", "ui-ref/v2"),
        ):
            with self.subTest(field=field):
                evidence = runtime_evidence(PROFILE)
                evidence[field] = value
                result = subprocess.run(
                    [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
                    input=json.dumps(evidence),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "HOLD")

    def test_runtime_status_holds_when_evidence_identity_does_not_match_its_content(self):
        evidence = runtime_evidence(PROFILE)
        evidence["rendered"] = {"declared": 99, "undeclared": 0}

        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "evidence-identity-mismatch")


class StaticReferenceVerticalSliceTests(unittest.TestCase):
    """One public contract from declaration through source resolution."""

    def test_static_unit_and_business_button_complete_the_resolution_chain(self):
        manifest = home_manifest()
        view = {
            "workspace": "fixture",
            "intent": "inspect",
            "plan": "next",
            "artifacts": "none",
            "evidence": "local",
            "run_facts": {"status": "running"},
            "preflight_result": "ready",
            "records": [{"title": "one"}],
        }

        self.assertEqual(render_attributes(manifest, "home.root"), {"data-ui-ref": "home.root"})
        self.assertEqual(
            render_attributes(manifest, "home.preflight-run.action"),
            {"data-ui-ref": "home.preflight-run.action"},
        )
        audit = audit_rendered_html(manifest, render_home(view, manifest=manifest))
        self.assertEqual(audit["undeclared"], ())
        self.assertEqual(audit["missing"], ())

        token = build_token(
            manifest,
            "home.preflight-run.action",
            viewport="wide",
            state="running",
        )
        parsed = parse_token(token)
        self.assertEqual(parsed["outcome"], "valid")
        self.assertEqual(
            resolve(manifest, parsed["token"]["ref"], ui_map=manifest["ui_map"])["outcome"],
            "found",
        )
        self.assertEqual(
            locate_source(manifest, parsed["token"]["ref"], root=REPO_ROOT)["outcome"],
            "found",
        )

        link = build_deep_link(manifest, "home.root")
        self.assertEqual(parse_deep_link(link)["outcome"], "valid")


if __name__ == "__main__":
    unittest.main()
