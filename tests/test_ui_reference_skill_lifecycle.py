"""Public lifecycle seam for independently installed UI reference skills."""

import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "evaluation" / "runner" / "run_ui_reference_skill_lifecycle.py"
PROTOCOL = REPO_ROOT / "skills" / "ui-reference-protocol"
RUNTIME = REPO_ROOT / "skills" / "ui-reference-runtime"


class SkillLifecycleTests(unittest.TestCase):
    @staticmethod
    def _declared_files_digest(root, package):
        entries = []
        for relative in sorted(package["files"]):
            if relative == "SKILL-PACKAGE.json":
                continue
            entries.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                }
            )
        payload = json.dumps(
            entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _v2_package(self, root):
        package_root = root / "protocol-v2"
        shutil.copytree(PROTOCOL, package_root)
        (package_root / "SKILL.md").write_text(
            (package_root / "SKILL.md").read_text(encoding="utf-8")
            + "\nVersion two lifecycle fixture.\n",
            encoding="utf-8",
        )
        manifest_path = package_root / "SKILL-PACKAGE.json"
        package = json.loads(manifest_path.read_text(encoding="utf-8"))
        package["version"] = "2"
        package["source"]["content_digest"] = self._declared_files_digest(
            package_root, package
        )
        manifest_path.write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return package_root

    def _tampered_package(self, root):
        package_root = root / "tampered-protocol"
        shutil.copytree(PROTOCOL, package_root)
        skill = package_root / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\nTampered without a new source digest.\n",
            encoding="utf-8",
        )
        return package_root

    def test_install_returns_an_observable_receipt_for_a_declared_skill_package(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "installed" / "protocol"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "install",
                    "--package",
                    str(PROTOCOL),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["schema"], "ui-ref-skill-lifecycle/v1")
            self.assertEqual(receipt["operation"], "install")
            self.assertEqual(receipt["status"], "installed")
            self.assertEqual(receipt["package"]["name"], "ui-reference-protocol")
            self.assertEqual(receipt["residuals"], [])
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(
                receipt["target_identity"],
                "sha256:" + __import__("hashlib").sha256(
                    str(target.resolve()).encode("utf-8")
                ).hexdigest(),
            )
            persisted = target / ".ui-reference-skill-receipt.json"
            self.assertTrue(persisted.is_file())
            persisted_receipt = json.loads(persisted.read_text(encoding="utf-8"))
            self.assertEqual(persisted_receipt["schema"], "ui-ref-skill-lifecycle/v1")
            self.assertEqual(persisted_receipt["operation"], "install")
            self.assertEqual(persisted_receipt["status"], "installed")
            self.assertEqual(persisted_receipt["package"], receipt["package"])
            self.assertNotIn(str(target.resolve()), persisted.read_text(encoding="utf-8"))

    def test_each_independent_skill_package_can_install_and_uninstall_through_the_same_seam(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for package_root, name in ((PROTOCOL, "protocol"), (RUNTIME, "runtime")):
                target = root / name
                installed = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER),
                        "--operation",
                        "install",
                        "--package",
                        str(package_root),
                        "--target",
                        str(target),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(installed.returncode, 0, installed.stderr)
                self.assertEqual(json.loads(installed.stdout)["status"], "installed")

                removed = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER),
                        "--operation",
                        "uninstall",
                        "--target",
                        str(target),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(removed.returncode, 0, removed.stderr)
                self.assertEqual(json.loads(removed.stdout)["residuals"], [])
                self.assertFalse(target.exists())

    def test_upgrade_records_a_new_package_and_keeps_a_valid_rollback_point(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "installed" / "protocol"
            installed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "install",
                    "--package",
                    str(PROTOCOL),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            package_v2 = self._v2_package(root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "upgrade",
                    "--package",
                    str(package_v2),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["operation"], "upgrade")
            self.assertEqual(receipt["status"], "upgraded")
            self.assertEqual(receipt["package"]["version"], "2")
            self.assertTrue(receipt["rollback"]["available"])
            self.assertTrue((target / "SKILL.md").read_text(encoding="utf-8").endswith("Version two lifecycle fixture.\n"))

    def test_rollback_restores_the_previous_version_and_removes_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "installed" / "protocol"
            for operation, package in (("install", PROTOCOL),):
                installed = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER),
                        "--operation",
                        operation,
                        "--package",
                        str(package),
                        "--target",
                        str(target),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(installed.returncode, 0, installed.stderr)
            package_v2 = self._v2_package(root)
            upgraded = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "upgrade",
                    "--package",
                    str(package_v2),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "rollback",
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["operation"], "rollback")
            self.assertEqual(receipt["status"], "rolled-back")
            self.assertEqual(receipt["package"]["version"], "1")
            self.assertFalse(receipt["rollback"]["available"])
            self.assertFalse((target.parent / ".protocol.rollback").exists())
            self.assertFalse((target / "SKILL.md").read_text(encoding="utf-8").endswith("Version two lifecycle fixture.\n"))

    def test_uninstall_after_upgrade_removes_the_active_skill_and_rollback_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "installed" / "protocol"
            installed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "install",
                    "--package",
                    str(PROTOCOL),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            package_v2 = self._v2_package(root)
            upgraded = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "upgrade",
                    "--package",
                    str(package_v2),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "uninstall",
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["status"], "uninstalled")
            self.assertEqual(receipt["residuals"], [])
            self.assertFalse(target.exists())
            self.assertFalse((target.parent / ".protocol.rollback").exists())

    def test_uninstall_removes_only_a_receipted_skill_and_reports_zero_residuals(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "installed" / "protocol"
            installed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "install",
                    "--package",
                    str(PROTOCOL),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "uninstall",
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["operation"], "uninstall")
            self.assertEqual(receipt["status"], "uninstalled")
            self.assertEqual(receipt["residuals"], [])
            self.assertFalse(target.exists())
            self.assertFalse((target.parent / ".protocol.rollback").exists())

    def test_uninstall_holds_without_a_receipt_and_does_not_delete_unmanaged_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unmanaged"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("do not remove", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "uninstall",
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["status"], "HOLD")
            self.assertTrue(sentinel.is_file())

    def test_install_holds_for_a_package_whose_source_digest_was_not_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._tampered_package(root)
            target = root / "installed" / "protocol"

            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--operation",
                    "install",
                    "--package",
                    str(package),
                    "--target",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["status"], "HOLD")
            self.assertIn("digest", receipt["reason"])
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
