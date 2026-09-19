"""Installation and documentation contract for the two UI reference skills."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ui_reference_support import runtime_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = REPO_ROOT / "skills" / "ui-reference-protocol"
RUNTIME = REPO_ROOT / "skills" / "ui-reference-runtime"
PROFILE = PROTOCOL / "examples" / "minimal-profile.json"
R1 = REPO_ROOT / "docs" / "prds" / "r1-ui-reference-registry.md"
R2 = REPO_ROOT / "docs" / "prds" / "r2-ui-reference-skills.md"
BINDING = REPO_ROOT / "docs" / "references" / "ui-reference-skills.md"
CONFORMANCE = (
    REPO_ROOT
    / "evaluation"
    / "fixtures"
    / "ui_reference_portability"
    / "v1"
    / "conformance.json"
)


class IndependentInstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._install(PROTOCOL, self.root / "protocol")
        self._install(RUNTIME, self.root / "runtime")
        shutil.copy2(PROFILE, self.root / "profile.json")
        self.addCleanup(self.tmp.cleanup)

    def _install(self, source, destination):
        package = json.loads(
            (source / "SKILL-PACKAGE.json").read_text(encoding="utf-8")
        )
        for relative in package["files"]:
            source_file = source / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)

    @staticmethod
    def _declared_files_digest(source, package):
        entries = []
        for relative in sorted(package["files"]):
            if relative == "SKILL-PACKAGE.json":
                continue
            content = (source / relative).read_bytes()
            entries.append(
                {"path": relative, "sha256": hashlib.sha256(content).hexdigest()}
            )
        payload = json.dumps(
            entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def test_package_manifests_are_closed_versioned_and_have_no_implicit_dependencies(self):
        for source, expected_name in ((PROTOCOL, "ui-reference-protocol"), (RUNTIME, "ui-reference-runtime")):
            with self.subTest(skill=expected_name):
                package = json.loads(
                    (source / "SKILL-PACKAGE.json").read_text(encoding="utf-8")
                )
                self.assertEqual(package["schema"], "codex-skill-package/v1")
                self.assertEqual(package["name"], expected_name)
                self.assertEqual(package["version"], "1")
                self.assertEqual(package["dependencies"], [])
                self.assertEqual(package["install"]["rollback"], "remove-installed-directory")
                listed = set(package["files"])
                self.assertEqual(len(listed), len(package["files"]))
                self.assertTrue(listed)
                for relative in listed:
                    self.assertTrue((source / relative).is_file(), relative)
                    self.assertNotIn("__pycache__", relative)

    def test_package_sources_have_reproducible_digest_provenance(self):
        for source, expected_name in ((PROTOCOL, "ui-reference-protocol"), (RUNTIME, "ui-reference-runtime")):
            with self.subTest(skill=expected_name):
                package = json.loads(
                    (source / "SKILL-PACKAGE.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    set(package["source"]),
                    {"kind", "revision", "digest_scope", "content_digest"},
                )
                self.assertEqual(package["source"]["kind"], "local-declared-files")
                self.assertEqual(package["source"]["revision"], "working-tree")
                self.assertEqual(
                    package["source"]["digest_scope"],
                    "declared-files-excluding-manifest",
                )
                self.assertEqual(
                    package["source"]["content_digest"],
                    self._declared_files_digest(source, package),
                )
                self.assertNotIn("registry", json.dumps(package).lower())

    def test_protocol_and_runtime_validators_agree_on_profile_acceptance(self):
        protocol_validator = self.root / "protocol" / "scripts" / "validate_profile.py"
        runtime_checker = self.root / "runtime" / "scripts" / "runtime_status.py"
        valid_evidence = runtime_evidence(self.root / "profile.json")

        accepted = subprocess.run(
            [sys.executable, str(protocol_validator), str(self.root / "profile.json")],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        checked = subprocess.run(
            [sys.executable, str(runtime_checker), str(self.root / "profile.json")],
            cwd=self.root,
            input=json.dumps(valid_evidence),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(accepted.returncode == 0, json.loads(checked.stdout)["status"] == "implemented")

        invalid = json.loads((self.root / "profile.json").read_text(encoding="utf-8"))
        invalid["contract"]["schemas"]["manifest"] = "ui-ref-manifest/v2"
        (self.root / "invalid-profile.json").write_text(json.dumps(invalid), encoding="utf-8")
        rejected = subprocess.run(
            [sys.executable, str(protocol_validator), str(self.root / "invalid-profile.json")],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        invalid_evidence = runtime_evidence(self.root / "invalid-profile.json")
        held = subprocess.run(
            [sys.executable, str(runtime_checker), str(self.root / "invalid-profile.json")],
            cwd=self.root,
            input=json.dumps(invalid_evidence),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(json.loads(held.stdout)["status"], "HOLD")

    def test_shared_conformance_corpus_is_checked_by_both_skill_validators(self):
        corpus = json.loads(CONFORMANCE.read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema"], "ui-ref-conformance/v1")
        self.assertGreaterEqual(len(corpus["cases"]), 5)
        seen_classes = {case["class"] for case in corpus["cases"]}
        self.assertTrue({"positive", "negative", "security", "unknown"} <= seen_classes)

        for case in corpus["cases"]:
            with self.subTest(case=case["name"]):
                profile = json.loads(PROFILE.read_text(encoding="utf-8"))
                for path, value in case.get("profile_patch", {}).items():
                    cursor = profile
                    parts = path.split(".")
                    for part in parts[:-1]:
                        cursor = cursor[part]
                    cursor[parts[-1]] = value

                with tempfile.TemporaryDirectory() as directory:
                    directory = Path(directory)
                    profile_path = directory / "profile.json"
                    profile_path.write_text(json.dumps(profile), encoding="utf-8")
                    evidence = runtime_evidence(
                        profile_path, **case.get("evidence_patch", {})
                    )
                    protocol_validator = self.root / "protocol" / "scripts" / "validate_profile.py"
                    runtime_checker = self.root / "runtime" / "scripts" / "runtime_status.py"
                    accepted = subprocess.run(
                        [sys.executable, str(protocol_validator), str(profile_path)],
                        cwd=self.root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    checked = subprocess.run(
                        [sys.executable, str(runtime_checker), str(profile_path)],
                        cwd=self.root,
                        input=json.dumps(evidence),
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                report = json.loads(checked.stdout)
                self.assertEqual(
                    accepted.returncode == 0,
                    case["expected"]["protocol"] == "accepted",
                )
                self.assertEqual(report["status"], case["expected"]["runtime"])
                self.assertEqual(report["reason"], case["expected"]["reason"])

    def test_protocol_skill_runs_without_the_repository(self):
        validator = self.root / "protocol" / "scripts" / "validate_profile.py"
        status = self.root / "protocol" / "scripts" / "profile_status.py"
        result = subprocess.run(
            [sys.executable, str(validator), str(self.root / "profile.json")],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        audited = subprocess.run(
            [
                sys.executable,
                str(status),
                "--mode",
                "audit",
                "--profile",
                str(self.root / "profile.json"),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(audited.returncode, 0, audited.stderr)
        self.assertEqual(json.loads(audited.stdout)["status"], "implemented")

    def test_runtime_skill_runs_without_the_protocol_skill_or_project_modules(self):
        checker = self.root / "runtime" / "scripts" / "runtime_status.py"
        evidence = runtime_evidence(
            self.root / "profile.json",
            browser="unknown",
            rendered={"declared": 1, "undeclared": 0},
            runtime_adapter="independent-fixture@1",
            environment="installation-test@1",
        )
        result = subprocess.run(
            [sys.executable, str(checker), str(self.root / "profile.json")],
            cwd=self.root,
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")

    def test_runtime_skill_has_no_implicit_protocol_import_or_apply_authority(self):
        files = list((self.root / "runtime").rglob("*"))
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in files
            if path.is_file() and path.suffix in {".md", ".py"}
        )

        self.assertNotIn("ui-reference-protocol/scripts", text)
        self.assertNotIn("from ui_reference_protocol", text)
        self.assertIn("generated diff", text)
        self.assertIn("applying", text)
        self.assertIn("rollback", text)

    def test_r1_remains_the_product_source_and_r2_is_indexed(self):
        self.assertTrue(R1.is_file())
        self.assertIn("R1", R1.read_text(encoding="utf-8"))
        r2 = R2.read_text(encoding="utf-8")
        self.assertIn("status: accepted", r2)
        self.assertIn("implementation-status: complete", r2)
        self.assertIn("r1-ui-reference-registry.md", r2)
        self.assertIn("r2-ui-reference-skills.md", (REPO_ROOT / "docs" / "prds" / "README.md").read_text(encoding="utf-8"))

    def test_the_binding_doc_points_to_both_independent_skill_packages(self):
        binding = BINDING.read_text(encoding="utf-8")

        self.assertIn("ui-reference-protocol/SKILL.md", binding)
        self.assertIn("ui-reference-runtime/SKILL.md", binding)
        self.assertIn("generated diff", binding)
        self.assertIn("rollback", binding)
        self.assertIn("deferred", binding)
        self.assertIn("run_ui_reference_skill_lifecycle.py", binding)
        for operation in ("install", "upgrade", "rollback", "uninstall"):
            self.assertIn(operation, binding)


if __name__ == "__main__":
    unittest.main()
