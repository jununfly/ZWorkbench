from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from zworkbench.composition import CompositionOwner, IntegrityError, InvalidTransition


class CompositionOwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db = self.root / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def _run(self, run_id: str = "run-1") -> None:
        self.owner.create_run(run_id, "unit-test", {"prompt": "fixture"})
        self.owner.start_run(run_id)

    def test_run_and_state_survive_reopen(self) -> None:
        self._run()
        self.owner.record_result("run-1", "adapter", {"thread_id": "thread-1"}, "thread")
        self.owner.record_replay_metadata("run-1", "replay-1", "recorded_view", "events-sha", "env-sha", {"provider": "fake"})
        self.owner.complete_run("run-1", {"answer": "ok"})
        digest_before = self.owner.state_digest()
        self.owner.close()

        with CompositionOwner(self.db) as reopened:
            run = reopened.get_run("run-1")
            self.assertEqual(run["status"], "completed")
            self.assertIn("semantic", {item["kind"] for item in run["results"]})
            self.assertEqual(reopened.snapshot()["replays"][0]["mode"], "recorded_view")
            self.assertEqual(reopened.state_digest(), digest_before)
            self.assertGreaterEqual(len(reopened.events("run-1")), 5)

    def test_approval_is_exact_and_token_is_one_use(self) -> None:
        self._run()
        request = self.owner.request_approval("run-1", "op-1", "deploy", "fixture-sink", "idem-1", "publish result")
        denied = self.owner.claim_effect("run-1", "op-1", "deploy", "fixture-sink", "idem-1", "approval-required")
        self.assertFalse(denied.executable)
        self.assertEqual(denied.reason, "approval_missing_or_not_approved")

        grant = self.owner.approve(request["approval_id"])
        claim = self.owner.claim_effect(
            "run-1", "op-1", "deploy", "fixture-sink", "idem-1", "approval-required", grant["token"]
        )
        self.assertTrue(claim.executable)
        self.owner.complete_effect(claim.effect_id, {"delivered": True})
        replay = self.owner.claim_effect(
            "run-1", "op-1", "deploy", "fixture-sink", "idem-1", "approval-required", grant["token"]
        )
        self.assertEqual(replay.status, "already_completed")
        self.assertEqual(self.owner.get_run("run-1")["effects"][0]["physical_effect_count"], 1)

    def test_approval_scope_mismatch_safe_stops_before_effect(self) -> None:
        self._run()
        request = self.owner.request_approval("run-1", "op-1", "deploy", "fixture-sink", "idem-1", "publish")
        grant = self.owner.approve(request["approval_id"])
        denied = self.owner.claim_effect(
            "run-1", "op-1", "delete", "fixture-sink", "idem-1", "approval-required", grant["token"]
        )
        self.assertFalse(denied.executable)
        self.assertEqual(denied.reason, "approval_scope_mismatch")
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("run-1")["effects"], [])

    def test_uncertain_effect_reconciles_to_one_bounded_retry(self) -> None:
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.assertTrue(claim.executable)
        self.owner.mark_effect_uncertain(claim.effect_id, {"error": "worker interrupted"})
        blocked = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.assertEqual(blocked.status, "recovery_required")
        self.owner.reconcile_effect(claim.effect_id, "not-applied", {"sink_count": 0})
        retry = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.assertTrue(retry.executable)
        self.assertEqual(retry.attempt, 2)
        self.owner.complete_effect(retry.effect_id, {"delivered": True}, {"receipt": "r-1"})
        self.owner.complete_run("run-1", "ok")
        effect = self.owner.get_run("run-1")["effects"][0]
        self.assertEqual(effect["attempt"], 2)
        self.assertEqual(effect["physical_effect_count"], 1)

    def test_unknown_reconcile_is_terminal_and_completion_is_blocked(self) -> None:
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.mark_effect_uncertain(claim.effect_id, "timeout")
        self.owner.reconcile_effect(claim.effect_id, "unknown", {"diagnosis": "sink unavailable"})
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")
        with self.assertRaises(InvalidTransition):
            self.owner.complete_run("run-1", "must not complete")

    def test_fail_run_persists_safe_stop_before_reporting_unresolved_effect(self) -> None:
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.mark_effect_uncertain(claim.effect_id, "worker interrupted")
        with self.assertRaises(InvalidTransition):
            self.owner.fail_run("run-1", "worker failed")
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")
        self.owner.reconcile_effect(claim.effect_id, "applied", {"sink_receipt": "r-1"})
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("run-1")["effects"][0]["physical_effect_count"], 1)

    def test_effect_operation_cannot_cross_run(self) -> None:
        self._run("run-1")
        self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.create_run("run-2", "unit-test", {})
        self.owner.start_run("run-2")
        denied = self.owner.claim_effect("run-2", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.assertEqual(denied.reason, "effect_belongs_to_other_run")
        self.assertEqual(self.owner.get_run("run-2")["status"], "safe_stopped")

    def test_backup_restore_validates_state_and_recovers_corrupt_target(self) -> None:
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.complete_effect(claim.effect_id, {"delivered": True})
        expected_digest = self.owner.state_digest()
        backup_dir = self.root / "backup"
        manifest = self.owner.backup(backup_dir)
        self.assertEqual(manifest["state_digest"], expected_digest)
        self.owner.close()
        self.db.write_bytes(b"not a sqlite database")
        restored = CompositionOwner.restore(backup_dir, self.db, replace=True)
        self.assertEqual(restored["state_digest"], expected_digest)
        with CompositionOwner(self.db) as recovered:
            self.assertEqual(recovered.state_digest(), expected_digest)
            export = recovered.export_state(self.root / "export.json")
            exported = json.loads((self.root / "export.json").read_text(encoding="utf-8"))
            self.assertEqual(exported["state_digest"], expected_digest)
            self.assertEqual(export["state_digest"], expected_digest)

    def test_restore_rejects_tampered_backup_and_existing_target(self) -> None:
        self._run()
        backup_dir = self.root / "backup"
        self.owner.backup(backup_dir)
        existing_target = self.root / "existing.sqlite3"
        with CompositionOwner(existing_target):
            with self.assertRaises(FileExistsError):
                CompositionOwner.restore(backup_dir, existing_target)

        manifest_path = backup_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["database_sha256"] = "tampered"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(IntegrityError):
            CompositionOwner.restore(backup_dir, self.root / "restored.sqlite3")

    def test_restore_rejects_state_json_that_is_rehashed_but_not_from_sqlite(self) -> None:
        self._run()
        backup_dir = self.root / "backup-cross-check"
        self.owner.backup(backup_dir)
        state_path = backup_dir / "state.json"
        manifest_path = backup_dir / "manifest.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["runs"] = []
        state_without_metadata = {key: state[key] for key in state if key not in {"exported_at", "state_digest"}}
        state["state_digest"] = CompositionOwner._sha256(
            CompositionOwner._canonical_json_static(state_without_metadata).encode("utf-8")
        )
        state_path.write_text(json.dumps(state), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state_digest"] = state["state_digest"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(IntegrityError):
            CompositionOwner.restore(backup_dir, self.root / "restored-cross-check.sqlite3")

    def test_unknown_effect_class_is_fail_closed(self) -> None:
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "unknown-action", "fixture", "idem-1", "future-class")
        self.assertEqual(claim.status, "denied")
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")

    def test_replay_identity_is_idempotent_and_modes_are_explicit(self) -> None:
        self._run()
        first = self.owner.record_replay_metadata("run-1", "replay-1", "simulated_replay", "events-sha", "env-sha", {"provider": "fake"})
        second = self.owner.record_replay_metadata("run-1", "replay-1", "simulated_replay", "events-sha", "env-sha", {"provider": "fake"})
        self.assertEqual(first["replay_id"], second["replay_id"])
        with self.assertRaises(ValueError):
            self.owner.record_replay_metadata("run-1", "replay-2", "implicit-live", "events-sha", "env-sha", {"provider": "fake"})


if __name__ == "__main__":
    unittest.main()
