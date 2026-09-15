"""Public contract tests for the portable UI Reference Protocol Profile."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-protocol"
    / "scripts"
    / "validate_profile.py"
)
EXAMPLE = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-protocol"
    / "examples"
    / "minimal-profile.json"
)
PROFILE_STATUS = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-protocol"
    / "scripts"
    / "profile_status.py"
)
DECLARATION_VALIDATOR = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-protocol"
    / "scripts"
    / "validate_declarations.py"
)
PROTOCOL_SKILL = REPO_ROOT / ".codex" / "skills" / "ui-reference-protocol"


def valid_profile():
    return {
        "schema": "ui-reference-profile/v1",
        "protocol": {"name": "semantic-ui-reference", "version": "1"},
        "identity": {
            "reference_pattern": "project.view.unit",
            "mapping_identity": "semantic-manifest",
            "build_identity": "source-receipt",
            "source_provenance": "repository-relative-content-identity",
        },
        "contract": {
            "semantic_scope": ["declared-ui-elements", "interactive-actions"],
            "identity_separation": [
                "semantic",
                "accessible",
                "presentation",
                "source",
                "mapping",
                "build",
            ],
            "schemas": {
                "manifest": "ui-ref-manifest/v1",
                "token": "ui-ref/v1",
            },
            "fields": {
                "declaration": {
                    "reference": "ref",
                    "semantic_name": "semantic",
                    "accessible_name": "accessible_name",
                    "presentation": "presentation",
                    "parent": "parent",
                },
                "manifest": {
                    "reference": "ref",
                    "mapping_identity": "ui_map",
                    "build_identity": "build",
                    "source_provenance": "source",
                },
                "token": {
                    "reference": "ref",
                    "mapping_identity": "ui_map",
                    "build_identity": "build",
                    "viewport": "viewport",
                    "display_state": "state",
                    "instance": "instance",
                },
                "deep_link": {
                    "reference": "ui_ref",
                    "mapping_identity": "ui_map",
                },
                "source": {
                    "repository_relative_anchor": "repo_path",
                    "symbol": "symbol",
                    "content_identity": "content_digest",
                },
            },
            "enums": {
                "viewport": ["compact", "wide"],
                "display_state": ["normal", "empty", "unknown"],
            },
            "lifecycle": {
                "alias_field": "alias_of",
                "replacement_field": "replaced_by",
                "retired_field": "retired",
                "compatibility_window": "one-previous-mapping",
            },
        },
        "instances": {
            "scope": "review-session",
            "handle": "random-memory-only",
            "outcomes": ["ambiguous", "unavailable", "expired"],
        },
        "migration": {
            "policy": "explicit-only",
            "outcomes": ["migrated", "retired", "incompatible"],
        },
        "token": {
            "max_bytes": 1024,
            "fields": [
                "protocol",
                "reference",
                "mapping_identity",
                "build_identity",
                "viewport",
                "display_state",
                "instance",
            ],
        },
        "deep_link": {
            "fields": ["reference", "mapping_identity"],
            "side_effects": False,
        },
        "security": {
            "forbidden_data": [
                "prompt",
                "event-body",
                "credential",
                "absolute-path",
            ],
            "remote_requests": False,
            "persistent_storage": False,
        },
        "trust": {
            "token_role": "locator-only",
            "state_owner": "project-owned",
            "review_state": "ephemeral",
            "effects": "none",
        },
        "host": {
            "capabilities": [
                "rendered-surface",
                "manifest-artifact",
                "source-provenance",
                "review-session",
                "local-navigation",
            ],
            "missing_policy": "unknown",
        },
        "review": {
            "default": "disabled",
            "explicit_enable": True,
            "pointer_passthrough": True,
            "user_initiated_clipboard": True,
            "teardown": "release-all-resources",
        },
        "evidence": {
            "required": ["profile", "artifact", "environment"],
            "unknown_policy": "preserve-unknown",
        },
        "acceptance": {
            "required": [
                "declaration-manifest",
                "rendered-reference",
                "exact-resolution",
                "negative-security",
            ],
            "threshold": "all-required",
            "unknown_policy": "preserve-unknown",
        },
    }


class UIReferenceProfileContractTests(unittest.TestCase):
    def run_validator(self, profile):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_a_valid_profile_is_accepted_and_canonical(self):
        first = self.run_validator(valid_profile())
        second = self.run_validator(valid_profile())

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(json.loads(first.stdout)["schema"], "ui-reference-profile/v1")

    def test_profile_lists_are_canonicalised_without_changing_contract(self):
        profile = valid_profile()
        profile["host"]["capabilities"] = list(
            reversed(profile["host"]["capabilities"])
        )
        profile["acceptance"]["required"] = list(
            reversed(profile["acceptance"]["required"])
        )

        result = self.run_validator(profile)

        self.assertEqual(result.returncode, 0, result.stderr)
        canonical = json.loads(result.stdout)
        self.assertEqual(
            canonical["host"]["capabilities"],
            sorted(profile["host"]["capabilities"]),
        )
        self.assertEqual(
            canonical["acceptance"]["required"],
            sorted(profile["acceptance"]["required"]),
        )

    def test_profile_declares_executable_field_mappings_and_identity_separation(self):
        result = self.run_validator(valid_profile())

        self.assertEqual(result.returncode, 0, result.stderr)
        canonical = json.loads(result.stdout)
        self.assertEqual(
            canonical["contract"]["fields"]["manifest"]["mapping_identity"],
            "ui_map",
        )
        self.assertEqual(
            set(canonical["contract"]["identity_separation"]),
            {"semantic", "accessible", "presentation", "source", "mapping", "build"},
        )

    def test_profile_rejects_a_field_mapping_that_collapses_identity_domains(self):
        profile = valid_profile()
        profile["contract"]["fields"]["token"]["mapping_identity"] = "ref"

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mapping_identity", result.stderr)

    def test_profile_rejects_a_lifecycle_contract_with_an_implicit_window(self):
        profile = valid_profile()
        profile["contract"]["lifecycle"]["compatibility_window"] = "implicit"

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compatibility_window", result.stderr)

    def test_an_unknown_profile_field_is_rejected(self):
        profile = valid_profile()
        profile["operator_note"] = "free text"

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown fields", result.stderr)

    def test_a_profile_missing_host_capability_is_rejected(self):
        profile = valid_profile()
        profile["host"]["capabilities"].remove("source-provenance")

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required capability", result.stderr)

    def test_a_profile_that_allows_effects_is_rejected(self):
        profile = valid_profile()
        profile["trust"]["effects"] = "project-owner"

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trust.effects", result.stderr)

    def test_profile_with_sensitive_path_data_is_rejected(self):
        profile = valid_profile()
        profile["identity"]["mapping_identity"] = "/Users/alice/project"

        result = self.run_validator(profile)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forbidden data", result.stderr)

    def test_profile_with_other_absolute_path_shapes_is_rejected(self):
        for path in ("/private/tmp/project", "file:///tmp/project", r"C:\\Users\\alice\\project"):
            profile = valid_profile()
            profile["identity"]["mapping_identity"] = path

            result = self.run_validator(profile)

            self.assertNotEqual(result.returncode, 0, path)
            self.assertIn("forbidden data", result.stderr)

    def test_duplicate_profile_fields_are_rejected(self):
        raw = (
            '{"schema":"ui-reference-profile/v1",'
            '"schema":"ui-reference-profile/v1"}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(raw, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_a_protocol_name_containing_sk_is_not_treated_as_a_secret(self):
        profile = valid_profile()
        profile["protocol"]["name"] = "task-ui-reference"

        result = self.run_validator(profile)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_project_neutral_example_is_accepted(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(EXAMPLE)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("zworkbench", result.stdout.lower())

    def test_design_mode_reports_a_profile_target(self):
        result = subprocess.run(
            [sys.executable, str(PROFILE_STATUS), "--mode", "design"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "design")
        self.assertEqual(report["status"], "target")

    def test_design_mode_reports_discovered_conventions_and_profile_identity(self):
        discovery = {
            "conventions": {
                "reference_attribute": "data-ref",
                "renderer": "static-html",
                "manifest_artifact": "catalog-manifest",
                "source_anchor": "repository-relative-content-identity",
                "host_boundary": "loopback-document",
                "browser": "cdp-compatible",
                "local_navigation": "relative-entry-point",
            },
            "capabilities": [
                "rendered-surface",
                "manifest-artifact",
                "source-provenance",
                "review-session",
                "local-navigation",
            ],
            "assumptions": ["the fixture owns its review session"],
            "unknowns": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            discovery_path = Path(directory) / "discovery.json"
            discovery_path.write_text(json.dumps(discovery), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROFILE_STATUS),
                    "--mode",
                    "design",
                    "--profile",
                    str(EXAMPLE),
                    "--discovery",
                    str(discovery_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "implemented")
        self.assertTrue(report["profile_identity"])
        self.assertEqual(report["unknowns"], [])
        self.assertIn("rendered-surface", report["required_capabilities"])
        self.assertEqual(report["conventions"]["reference_attribute"], "data-ref")
        self.assertEqual(report["conventions"]["renderer"], "static-html")
        self.assertEqual(report["conventions"]["host_boundary"], "loopback-document")
        self.assertEqual(report["conventions"]["browser"], "cdp-compatible")
        self.assertIn("owner", report)
        self.assertIn("rollback_path", report)

    def test_design_mode_preserves_unknown_when_discovery_lacks_a_required_capability(self):
        discovery = {
            "conventions": {
                "reference_attribute": "data-ref",
                "renderer": "static-html",
                "manifest_artifact": "catalog-manifest",
                "source_anchor": "repository-relative-content-identity",
                "host_boundary": "loopback-document",
                "browser": "cdp-compatible",
                "local_navigation": "relative-entry-point",
            },
            "capabilities": ["rendered-surface"],
            "assumptions": [],
            "unknowns": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            discovery_path = Path(directory) / "discovery.json"
            discovery_path.write_text(json.dumps(discovery), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROFILE_STATUS),
                    "--mode",
                    "design",
                    "--profile",
                    str(EXAMPLE),
                    "--discovery",
                    str(discovery_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "unknown")
        self.assertIn("manifest-artifact", report["unknowns"])

    def test_audit_mode_reports_missing_profile_as_hold(self):
        result = subprocess.run(
            [
                sys.executable,
                str(PROFILE_STATUS),
                "--mode",
                "audit",
                "--profile",
                "/tmp/profile-that-does-not-exist.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "missing-profile")
        self.assertEqual(report["status"], "HOLD")

    def test_audit_mode_rejects_an_invalid_profile_without_project_facts(self):
        profile = valid_profile()
        del profile["token"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PROFILE_STATUS), "--mode", "audit", "--profile", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "audit")
        self.assertEqual(report["status"], "HOLD")

    def test_audit_mode_accepts_only_a_valid_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.json"
            path.write_text(json.dumps(valid_profile()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PROFILE_STATUS), "--mode", "audit", "--profile", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "implemented")

    def test_protocol_skill_is_project_neutral_and_has_progressive_references(self):
        skill = (PROTOCOL_SKILL / "SKILL.md").read_text(encoding="utf-8")

        self.assertLessEqual(len(skill.splitlines()), 100)
        self.assertIn("references/profile-contract.md", skill)
        self.assertIn("examples/minimal-profile.json", skill)
        self.assertNotIn("ZWorkbench", skill)
        self.assertNotIn("zworkbench", skill.lower())

    def test_protocol_validator_runs_outside_the_project_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(PROFILE_STATUS), "--mode", "audit", "--profile", str(EXAMPLE)],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "implemented")


class UIReferenceDeclarationContractTests(unittest.TestCase):
    def run_validator(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "declarations.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(DECLARATION_VALIDATOR), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def valid_declarations(self):
        return {
            "declarations": [
                {
                    "ref": "catalog.shell",
                    "parent": None,
                    "alias_of": [],
                    "retired": False,
                    "replaced_by": None,
                },
                {
                    "ref": "catalog.card",
                    "parent": "catalog.shell",
                    "alias_of": ["catalog.item"],
                    "retired": False,
                    "replaced_by": None,
                },
                {
                    "ref": "catalog.legacy",
                    "parent": "catalog.shell",
                    "alias_of": [],
                    "retired": True,
                    "replaced_by": "catalog.card",
                },
            ]
        }

    def test_declaration_graph_is_canonical_and_accepts_explicit_migration(self):
        result = self.run_validator(self.valid_declarations())

        self.assertEqual(result.returncode, 0, result.stderr)
        canonical = json.loads(result.stdout)
        self.assertEqual(
            [entry["ref"] for entry in canonical["declarations"]],
            ["catalog.card", "catalog.legacy", "catalog.shell"],
        )

    def test_declaration_graph_rejects_invalid_parent_alias_and_replacement_edges(self):
        cases = {
            "missing-parent": lambda document: document["declarations"].__setitem__(
                1, dict(document["declarations"][1], parent="catalog.missing")
            ),
            "parent-cycle": lambda document: document["declarations"].__setitem__(
                0, dict(document["declarations"][0], parent="catalog.card")
            ),
            "alias-conflict": lambda document: document["declarations"].__setitem__(
                2, dict(document["declarations"][2], alias_of=["catalog.item"])
            ),
            "missing-replacement": lambda document: document["declarations"].__setitem__(
                2, dict(document["declarations"][2], replaced_by="catalog.missing")
            ),
            "replacement-cycle": lambda document: document["declarations"].__setitem__(
                1,
                dict(
                    document["declarations"][1],
                    retired=True,
                    replaced_by="catalog.legacy",
                ),
            ),
            "retired-replacement-target": lambda document: document["declarations"].__setitem__(
                1,
                dict(
                    document["declarations"][1],
                    retired=True,
                    replaced_by="catalog.shell",
                ),
            ),
        }

        for name, mutate in cases.items():
            with self.subTest(name=name):
                document = self.valid_declarations()
                mutate(document)
                result = self.run_validator(document)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("rejected", result.stderr)


if __name__ == "__main__":
    unittest.main()
