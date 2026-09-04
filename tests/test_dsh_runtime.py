from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from zworkbench.composition import CompositionOwner
from zworkbench.dsh_runtime import (
    DshBootstrapProtocolError,
    DshManifestError,
    DshProcessError,
    DshRuntimeAdapter,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_dsh_bootstrap" / "v1"


class DshRuntimeAdapterTests(unittest.TestCase):
    def _case(self, temporary: str, *, scenario: str = "success", manifest_update=None):
        root = Path(temporary)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        bundle = root / "runtime"
        shutil.copytree(FIXTURE, bundle)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["launch"]["args"] = ["--scenario", scenario]
        if manifest_update is not None:
            manifest_update(manifest)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        return case_root, manifest_path, owner

    def test_success_starts_pinned_artifact_and_records_parent_session_and_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(temporary)
            try:
                adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
                result = adapter.execute("run-h1-success")

                self.assertEqual(result.status, "completed")
                self.assertEqual(result.dsh_session_id, "fixture-dsh-session-1")
                self.assertEqual(result.raw_event_count, 2)
                self.assertTrue(result.bootstrap_event_digest.startswith("sha256:"))
                self.assertTrue((case_root / "dsh-home").is_dir())
                self.assertIsNone(adapter.process)
                run = owner.get_run("run-h1-success")
                self.assertEqual(run["status"], "completed")
                self.assertEqual(run["metadata"]["runtime_mode"], "artifact")
                self.assertEqual(
                    [event["type"] for event in owner.events("run-h1-success")].count("dsh.bootstrap.started"),
                    1,
                )
                exit_results = [item for item in run["results"] if item["kind"] == "dsh.exit"]
                self.assertEqual(exit_results[0]["value"]["exit_code"], 0)
                self.assertFalse(exit_results[0]["value"]["shell"])
            finally:
                owner.close()

    def test_artifact_digest_mismatch_safe_stops_without_starting_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(temporary)
            artifact = manifest_path.parent / "dsh_bootstrap_fixture.py"
            artifact.write_bytes(artifact.read_bytes() + b"# tampered\n")
            try:
                adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
                with self.assertRaises(DshManifestError) as raised:
                    adapter.execute("run-h1-tampered")
                self.assertEqual(raised.exception.code, "artifact_digest_mismatch")
                self.assertIsNone(adapter.process)
                self.assertEqual(owner.get_run("run-h1-tampered")["status"], "safe_stopped")
                self.assertEqual(
                    [item["kind"] for item in owner.get_run("run-h1-tampered")["results"]],
                    ["dsh.error"],
                )
            finally:
                owner.close()

    def test_unknown_manifest_field_safe_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(
                temporary,
                manifest_update=lambda manifest: manifest.update({"future_field": True}),
            )
            try:
                with self.assertRaises(DshManifestError) as raised:
                    DshRuntimeAdapter(owner, manifest_path, case_root).execute("run-h1-unknown-field")
                self.assertEqual(raised.exception.code, "manifest_field_shape_invalid")
                self.assertEqual(owner.get_run("run-h1-unknown-field")["status"], "safe_stopped")
            finally:
                owner.close()

    def test_case_local_path_escape_safe_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(
                temporary,
                manifest_update=lambda manifest: manifest["workspace"].update({"path": "../outside"}),
            )
            try:
                with self.assertRaises(DshManifestError) as raised:
                    DshRuntimeAdapter(owner, manifest_path, case_root).execute("run-h1-path-escape")
                self.assertEqual(raised.exception.code, "case_path_escape")
                self.assertEqual(owner.get_run("run-h1-path-escape")["status"], "safe_stopped")
            finally:
                owner.close()

    def test_unknown_bootstrap_message_safe_stops_and_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(temporary, scenario="unknown")
            try:
                with self.assertRaises(DshBootstrapProtocolError) as raised:
                    DshRuntimeAdapter(owner, manifest_path, case_root).execute("run-h1-unknown-wire")
                self.assertEqual(raised.exception.code, "bootstrap_message_unknown")
                run = owner.get_run("run-h1-unknown-wire")
                self.assertEqual(run["status"], "safe_stopped")
                self.assertNotIn("semantic", {item["kind"] for item in run["results"]})
                self.assertNotEqual(
                    [item for item in run["results"] if item["kind"] == "dsh.exit"][0]["value"]["exit_code"],
                    0,
                )
                self.assertTrue(any(event["type"] == "dsh.bootstrap.rejected" for event in owner.events("run-h1-unknown-wire")))
            finally:
                owner.close()

    def test_nonzero_exit_records_receipt_and_safe_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_root, manifest_path, owner = self._case(temporary, scenario="nonzero")
            try:
                with self.assertRaises(DshProcessError) as raised:
                    DshRuntimeAdapter(owner, manifest_path, case_root).execute("run-h1-nonzero")
                self.assertEqual(raised.exception.code, "process_exit_nonzero")
                run = owner.get_run("run-h1-nonzero")
                self.assertEqual(run["status"], "safe_stopped")
                exit_results = [item for item in run["results"] if item["kind"] == "dsh.exit"]
                self.assertEqual(exit_results[0]["value"]["exit_code"], 7)
            finally:
                owner.close()

    def test_owner_event_seam_is_idempotent_and_rejects_raw_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            owner = CompositionOwner(Path(temporary) / "owner.sqlite3")
            try:
                owner.create_run("run-event", "unit-test", {})
                first = owner.record_event("run-event", "fixture.event", {"value": "ok"}, "event-1")
                second = owner.record_event("run-event", "fixture.event", {"value": "ok"}, "event-1")
                self.assertEqual(first["event_id"], second["event_id"])
                with self.assertRaises(ValueError):
                    owner.record_event("run-event", "fixture.event", {"token": "must-not-persist"})
            finally:
                owner.close()

if __name__ == "__main__":
    unittest.main()
