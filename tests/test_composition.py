from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import tempfile
import unittest

from zworkbench.composition import (
    CompositionOwner,
    EVIDENCE_SOURCE_NATIVE,
    EVIDENCE_SOURCE_OUTER_COMPOSED,
    EVIDENCE_SOURCE_PLUGIN_COMPOSED,
    IntegrityError,
    InvalidTransition,
    NotFoundError,
    ProviderAccessDenied,
    RetryBudgetExhausted,
)


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
        self.owner.record_result("run-1", "adapter", {"thread_id": "thread-1"}, "thread", evidence_source=EVIDENCE_SOURCE_NATIVE)
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

    def test_begin_recovery_is_explicit_and_rejects_unresolved_effects(self) -> None:
        self._run()
        recovering = self.owner.begin_recovery("run-1", "worker timeout")
        self.assertEqual(recovering["status"], "recovering")
        self.assertEqual(self.owner.start_run("run-1")["status"], "running")

        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.mark_effect_uncertain(claim.effect_id, "worker interrupted")
        with self.assertRaises(InvalidTransition):
            self.owner.begin_recovery("run-1", "retry worker")

    def test_effect_operation_cannot_cross_run(self) -> None:
        self._run("run-1")
        self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.create_run("run-2", "unit-test", {})
        self.owner.start_run("run-2")
        denied = self.owner.claim_effect("run-2", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.assertEqual(denied.reason, "effect_belongs_to_other_run")
        self.assertEqual(self.owner.get_run("run-2")["status"], "safe_stopped")

    def test_f13_detects_broken_parent_run_link_as_identity_violation(self) -> None:
        self.owner.create_run(
            "run-1", "unit-test", {"prompt": "x"}, metadata={"parent_run_id": "ghost-run"}
        )
        violations = self.owner.detect_identity_violations("run-1")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["kind"], "broken_parent_run_id")
        self.assertEqual(violations[0]["ref_id"], "ghost-run")

        result = self.owner.safe_stop_on_identity_violation("run-1")
        self.assertTrue(result["safe_stopped"])
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")

        reconciled = self.owner.reconcile_identity("run-1")
        self.assertEqual(reconciled["outcome"], "unknown")
        self.assertEqual(reconciled["status"], "safe_stopped")

    def test_f13_reconcile_resolves_after_fixing_the_link(self) -> None:
        self.owner.create_run(
            "run-1", "unit-test", {"prompt": "x"}, metadata={"parent_run_id": "ghost-run"}
        )
        self.owner.safe_stop_on_identity_violation("run-1")
        connection = sqlite3.connect(str(self.db))
        connection.execute("UPDATE runs SET metadata_json = '{}' WHERE run_id = 'run-1'")
        connection.commit()
        connection.close()
        reconciled = self.owner.reconcile_identity("run-1")
        self.assertEqual(reconciled["outcome"], "resolved")
        self.assertEqual(reconciled["violations"], [])
        # safe-stopped is terminal: reconciliation records the decision but the
        # run stays stopped (honest fail-closed semantics, like reconcile_effect).
        self.assertEqual(self.owner.get_run("run-1")["status"], "safe_stopped")

    def test_f13_detects_orphan_effect_run_after_run_deleted(self) -> None:
        self._run("run-1")
        self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        connection = sqlite3.connect(str(self.db))
        connection.execute("DELETE FROM runs WHERE run_id = 'run-1'")
        connection.commit()
        connection.close()
        violations = self.owner.detect_identity_violations()
        self.assertIn("orphan_effects_run", {v["kind"] for v in violations})

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

    def test_owner_evidence_writers_reject_raw_credentials(self) -> None:
        # NOTE: create_run is intentionally NOT asserted here. Run input/metadata
        # is the harness's own run definition (redaction model: owner stores raw,
        # view layer redacts) and must not be rejected by value-level hygiene.
        # Credential hygiene is enforced only at the true external-evidence seams
        # below (see roadmap node 1-6-5 for the scoping decision).
        with self.assertRaises(ValueError):
            self.owner.record_result(
                "run-1", "adapter", {"authorization": "Bearer secret"}, evidence_source=EVIDENCE_SOURCE_NATIVE
            )
        with self.assertRaises(ValueError):
            self.owner.record_replay_metadata(
                "run-1",
                "credential-replay",
                "recorded_view",
                "events-sha",
                "env-sha",
                {"provider": "fake", "api_key": "secret"},
            )

    def test_external_receipt_rejects_raw_credentials_and_secret_values(self) -> None:
        # 1-6-1: external_receipt must go through secret rejection (field name)
        # AND value-level scanning before it is persisted in the unique owner.
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        # Field-name level: a raw credential key must be rejected.
        with self.assertRaises(ValueError):
            self.owner.complete_effect(claim.effect_id, {"delivered": True}, {"api_key": "sk-secret"})
        # Value-level: benign field name but a secret-shaped value must be rejected.
        with self.assertRaises(ValueError):
            self.owner.complete_effect(claim.effect_id, {"delivered": True}, {"receipt": "AKIAIOSFODNN7EXAMPLE"})
        # Allowed: an identity-reference suffix is not a raw credential.
        stored = self.owner.complete_effect(claim.effect_id, {"delivered": True}, {"api_key_ref": "vault://secret/42"})
        self.assertEqual(stored["external_receipt"], {"api_key_ref": "vault://secret/42"})

    def test_reconcile_applied_rejects_secret_valued_receipt(self) -> None:
        # 1-6-1 symmetry: the applied-reconcile path also persists evidence as
        # external_receipt and must reject secret-shaped values.
        self._run()
        claim = self.owner.claim_effect("run-1", "op-1", "write", "fixture-sink", "idem-1", "idempotent")
        self.owner.mark_effect_uncertain(claim.effect_id, {"error": "worker interrupted"})
        with self.assertRaises(ValueError):
            self.owner.reconcile_effect(claim.effect_id, "applied", {"receipt": "AKIAIOSFODNN7EXAMPLE"})
        # A benign applied reconcile still persists its receipt.
        stored = self.owner.reconcile_effect(claim.effect_id, "applied", {"receipt": "r-1"})
        self.assertEqual(stored["external_receipt"], {"receipt": "r-1"})


class ProviderExitLedgerTests(unittest.TestCase):
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

    def test_default_path_ledger_is_unknown_delegated_and_never_claims_remote_zero_residue(self) -> None:
        self._run()
        entry = self.owner.record_provider_exit_ledger(
            "run-1",
            {"provider": "fake-loopback", "model": "fake-model", "endpoint": "http://127.0.0.1:11434"},
        )
        self.assertEqual(entry["provider"], "fake-loopback")
        self.assertEqual(entry["endpoint"], "http://127.0.0.1:11434")
        self.assertEqual(entry["account_scope"], "unknown")
        self.assertEqual(entry["exit_mode"], "inventory-only")
        self.assertEqual(entry["exit_status"], "unknown/safe-stop")
        self.assertEqual(entry["provider_remote_zero_residue"], "unknown/delegated")
        self.assertEqual(set(entry["statuses"].values()), {"unknown"})
        self.assertEqual(entry["unknown_fields"], sorted(entry["statuses"].keys()))
        events = self.owner.events("run-1")
        self.assertTrue(any(e["type"] == "provider.exit.ledger.recorded" for e in events))

    def test_ledger_rejects_raw_credentials_in_provider_identity(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_exit_ledger("run-1", {"provider": "fake", "api_key": "sk-secret"})

    def test_local_state_fingerprint_must_be_hex_or_unknown(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_exit_ledger("run-1", {"provider": "fake"}, local_state_fingerprint="not-hex")
        entry = self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake"}, local_state_fingerprint="a" * 64
        )
        self.assertEqual(entry["local_state_fingerprint"], "a" * 64)

    def test_ledger_survives_reopen_and_appears_in_snapshot(self) -> None:
        self._run()
        self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        digest_before = self.owner.state_digest()
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            ledger = reopened.provider_exit_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["provider_remote_zero_residue"], "unknown/delegated")
            self.assertEqual(reopened.snapshot()["provider_exit_ledger"][0]["provider"], "fake-loopback")
            self.assertEqual(reopened.state_digest(), digest_before)

    def test_ledger_for_run_returns_all_entries_in_order(self) -> None:
        self._run()
        self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        entries = self.owner.provider_exit_ledger_for_run("run-1")
        self.assertEqual(len(entries), 2)

    def test_get_missing_ledger_entry_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_exit_ledger("missing")


    def test_record_once_is_idempotent_across_harness_and_adapter(self) -> None:
        # 1-3-2 pairing contract: the harness and adapter share one run; the
        # adapter writes the Provider ledger, the harness must not duplicate it.
        self._run()
        identity = {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        first = self.owner.record_provider_exit_ledger_once("run-1", identity)
        second = self.owner.record_provider_exit_ledger_once("run-1", identity)
        self.assertEqual(first["ledger_id"], second["ledger_id"])
        self.assertEqual(len(self.owner.provider_exit_ledger_for_run("run-1")), 1)

    def test_record_once_preserves_append_only_base_semantics(self) -> None:
        # The base API remains append-only; _once is the deliberate guard the
        # harness/adapter rely on to keep a single Provider accounting per run.
        self._run()
        identity = {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        self.owner.record_provider_exit_ledger_once("run-1", identity)
        self.owner.record_provider_exit_ledger("run-1", identity)
        self.assertEqual(len(self.owner.provider_exit_ledger_for_run("run-1")), 2)


class ProviderFallbackLedgerTests(unittest.TestCase):
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

    def test_reason_required_denies_empty_and_none(self) -> None:
        # Node 1-1-1 regression: a fallback without an explicit reason must be
        # rejected (reason-required fail-closed), never silently admitted.
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_fallback(
                "run-1", from_provider="primary", to_provider="secondary",
                reason="", degradation_mode="fallback", attempt=1,
            )
        with self.assertRaises(ValueError):
            self.owner.record_provider_fallback(
                "run-1", from_provider="primary", to_provider="secondary",
                reason=None, degradation_mode="fallback", attempt=1,
            )

    def test_records_fallback_with_all_fields(self) -> None:
        self._run()
        entry = self.owner.record_provider_fallback(
            "run-1", from_provider="primary", to_provider="secondary",
            reason="RATE_LIMIT", degradation_mode="fallback", attempt=1,
            failure_code="RATE_LIMIT", http_status=429,
            local_state_fingerprint="a" * 64,
        )
        self.assertEqual(entry["from_provider"], "primary")
        self.assertEqual(entry["to_provider"], "secondary")
        self.assertEqual(entry["reason"], "RATE_LIMIT")
        self.assertEqual(entry["degradation_mode"], "fallback")
        self.assertEqual(entry["attempt"], 1)
        self.assertEqual(entry["failure_code"], "RATE_LIMIT")
        self.assertEqual(entry["http_status"], 429)
        self.assertEqual(entry["local_state_fingerprint"], "a" * 64)
        events = self.owner.events("run-1")
        self.assertTrue(any(e["type"] == "provider.fallback.ledger.recorded" for e in events))

    def test_degradation_mode_must_be_valid(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_fallback(
                "run-1", from_provider="primary", to_provider="secondary",
                reason="RATE_LIMIT", degradation_mode="explode", attempt=1,
            )

    def test_attempt_must_be_non_negative_int(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_fallback(
                "run-1", from_provider="primary", to_provider="secondary",
                reason="RATE_LIMIT", degradation_mode="fallback", attempt=-1,
            )

    def test_local_state_fingerprint_must_be_hex_or_unknown(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_fallback(
                "run-1", from_provider="primary", to_provider="secondary",
                reason="RATE_LIMIT", degradation_mode="fallback", attempt=1,
                local_state_fingerprint="not-hex",
            )

    def test_survives_reopen_and_appears_in_snapshot(self) -> None:
        self._run()
        self.owner.record_provider_fallback(
            "run-1", from_provider="primary", to_provider="secondary",
            reason="RATE_LIMIT", degradation_mode="fallback", attempt=1,
        )
        digest_before = self.owner.state_digest()
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            ledger = reopened.provider_fallback_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["reason"], "RATE_LIMIT")
            self.assertEqual(reopened.snapshot()["provider_fallback_ledger"][0]["to_provider"], "secondary")
            self.assertEqual(reopened.state_digest(), digest_before)

    def test_for_run_returns_all_entries_in_order(self) -> None:
        self._run()
        self.owner.record_provider_fallback(
            "run-1", from_provider="primary", to_provider="secondary",
            reason="RATE_LIMIT", degradation_mode="fallback", attempt=1,
        )
        self.owner.record_provider_fallback(
            "run-1", from_provider="secondary", to_provider=None,
            reason="UPSTREAM_UNAVAILABLE", degradation_mode="safe_stop", attempt=2,
            failure_code="UPSTREAM_UNAVAILABLE", http_status=503,
        )
        entries = self.owner.provider_fallback_ledger_for_run("run-1")
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["degradation_mode"] for e in entries], ["fallback", "safe_stop"])

    def test_get_missing_ledger_entry_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_fallback_ledger("missing")


class ProviderAttemptLedgerTests(unittest.TestCase):
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

    def test_records_terminal_attempt_with_all_fields(self) -> None:
        self._run()
        entry = self.owner.record_provider_attempt(
            "run-1", provider_id="primary", request_id="req-1",
            attempt_number=2, status="failed", failure_code="RATE_LIMIT",
        )
        self.assertEqual(entry["provider_id"], "primary")
        self.assertEqual(entry["request_id"], "req-1")
        self.assertEqual(entry["attempt_number"], 2)
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["failure_code"], "RATE_LIMIT")
        events = self.owner.events("run-1")
        self.assertTrue(any(e["type"] == "provider.attempt.ledger.recorded" for e in events))

    def test_succeeded_attempt_without_failure_code(self) -> None:
        self._run()
        entry = self.owner.record_provider_attempt(
            "run-1", provider_id="primary", request_id="req-1",
            attempt_number=1, status="succeeded",
        )
        self.assertEqual(entry["status"], "succeeded")
        self.assertIsNone(entry["failure_code"])

    def test_status_must_be_terminal(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_attempt(
                "run-1", provider_id="primary", request_id="req-1",
                attempt_number=1, status="started",
            )

    def test_attempt_number_must_be_positive_int(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_attempt(
                "run-1", provider_id="primary", request_id="req-1",
                attempt_number=0, status="failed",
            )

    def test_required_fields_rejected(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_attempt(
                "run-1", provider_id="", request_id="req-1",
                attempt_number=1, status="failed",
            )
        with self.assertRaises(ValueError):
            self.owner.record_provider_attempt(
                "run-1", provider_id="primary", request_id="req-1",
                attempt_number=1, status="succeeded", failure_code=123,
            )

    def test_for_run_counts_attempts_per_provider_in_order(self) -> None:
        # Node 1-1-2 regression: attempts must be owner-backed and countable
        # per provider per run, in deterministic attempt order.
        self._run()
        self.owner.record_provider_attempt("run-1", provider_id="primary", request_id="req-1", attempt_number=1, status="failed", failure_code="RATE_LIMIT")
        self.owner.record_provider_attempt("run-1", provider_id="secondary", request_id="req-1", attempt_number=2, status="failed", failure_code="TIMEOUT")
        self.owner.record_provider_attempt("run-1", provider_id="tertiary", request_id="req-1", attempt_number=3, status="succeeded")
        entries = self.owner.provider_attempt_ledger_for_run("run-1")
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["attempt_number"] for e in entries], [1, 2, 3])
        self.assertEqual([e["provider_id"] for e in entries], ["primary", "secondary", "tertiary"])
        # downstream budget accounting can derive per-provider attempt counts
        counts = {}
        for entry in entries:
            counts[entry["provider_id"]] = counts.get(entry["provider_id"], 0) + 1
        self.assertEqual(counts, {"primary": 1, "secondary": 1, "tertiary": 1})

    def test_survives_reopen_and_appears_in_snapshot(self) -> None:
        self._run()
        self.owner.record_provider_attempt("run-1", provider_id="primary", request_id="req-1", attempt_number=1, status="succeeded")
        digest_before = self.owner.state_digest()
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            ledger = reopened.provider_attempt_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["provider_id"], "primary")
            self.assertEqual(reopened.snapshot()["provider_attempt_ledger"][0]["status"], "succeeded")
            self.assertEqual(reopened.state_digest(), digest_before)

    def test_get_missing_ledger_entry_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_attempt_ledger("missing")


class ProviderRetryBudgetTests(unittest.TestCase):
    # Node 1-1-3: a Provider-level retry ceiling owned by the single durable
    # owner, plus a consumption ledger for every cross-Provider retry.

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def _run(self) -> None:
        self.owner.create_run("run-1", "provider.read-only", {"request": "fixture"})
        self.owner.start_run("run-1")

    def test_declare_and_read_budget(self) -> None:
        self.owner.declare_provider_retry_budget("primary", max_retries=3, declared_by="owner")
        budget = self.owner.get_provider_retry_budget("primary")
        self.assertEqual(budget["provider_id"], "primary")
        self.assertEqual(budget["max_retries"], 3)
        self.assertEqual(budget["declared_by"], "owner")
        self.assertEqual(len(self.owner.provider_retry_budgets()), 1)

    def test_undeclared_budget_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_retry_budget("ghost")

    def test_declare_is_idempotent_upsert(self) -> None:
        self.owner.declare_provider_retry_budget("primary", max_retries=2, declared_by="owner")
        self.owner.declare_provider_retry_budget("primary", max_retries=5, declared_by="operator")
        budget = self.owner.get_provider_retry_budget("primary")
        self.assertEqual(budget["max_retries"], 5)
        self.assertEqual(budget["declared_by"], "operator")
        self.assertEqual(len(self.owner.provider_retry_budgets()), 1)

    def test_consumption_records_each_retry_with_failure_class_target_reason(self) -> None:
        self._run()
        self.owner.declare_provider_retry_budget("primary", max_retries=5, declared_by="owner")
        self.owner.record_provider_retry_budget_consumption(
            "run-1", provider_id="primary", request_id="req-1", attempt_number=1,
            failure_class="RATE_LIMIT", target="secondary", reason="RATE_LIMIT",
        )
        self.owner.record_provider_retry_budget_consumption(
            "run-1", provider_id="primary", request_id="req-1", attempt_number=2,
            failure_class="TIMEOUT", target="secondary", reason="TIMEOUT",
        )
        entries = self.owner.provider_retry_budget_ledger_for_run("run-1")
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["attempt_number"] for e in entries], [1, 2])
        self.assertEqual([e["failure_class"] for e in entries], ["RATE_LIMIT", "TIMEOUT"])
        self.assertEqual([e["target"] for e in entries], ["secondary", "secondary"])
        self.assertEqual([e["bound"] for e in entries], ["enforced", "enforced"])

    def test_exhaustion_is_fail_closed(self) -> None:
        # The ceiling is enforced: one over the max raises and writes nothing.
        self._run()
        self.owner.declare_provider_retry_budget("primary", max_retries=2, declared_by="owner")
        for attempt in (1, 2):
            self.owner.record_provider_retry_budget_consumption(
                "run-1", provider_id="primary", request_id="req-1", attempt_number=attempt,
                failure_class="RATE_LIMIT", target="secondary", reason="RATE_LIMIT",
            )
        with self.assertRaises(RetryBudgetExhausted):
            self.owner.record_provider_retry_budget_consumption(
                "run-1", provider_id="primary", request_id="req-1", attempt_number=3,
                failure_class="RATE_LIMIT", target="secondary", reason="RATE_LIMIT",
            )
        # nothing was written for the rejected third retry
        self.assertEqual(len(self.owner.provider_retry_budget_ledger_for_run("run-1")), 2)

    def test_undeclared_provider_still_recorded_as_undeclared(self) -> None:
        # Baseline loopback/fake Providers have no declared ceiling; the retry is
        # still captured (audit signal) without blocking the path.
        self._run()
        self.owner.record_provider_retry_budget_consumption(
            "run-1", provider_id="loopback", request_id="req-1", attempt_number=1,
            failure_class="UNKNOWN", target=None, reason="UNKNOWN",
        )
        entries = self.owner.provider_retry_budget_ledger_for_run("run-1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["bound"], "undeclared")
        self.assertIsNone(entries[0]["target"])

    def test_reason_required_fail_closed(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_retry_budget_consumption(
                "run-1", provider_id="primary", request_id="req-1", attempt_number=1,
                failure_class="RATE_LIMIT", target="secondary", reason="",
            )

    def test_survives_reopen_and_appears_in_snapshot(self) -> None:
        self._run()
        self.owner.declare_provider_retry_budget("primary", max_retries=3, declared_by="owner")
        self.owner.record_provider_retry_budget_consumption(
            "run-1", provider_id="primary", request_id="req-1", attempt_number=1,
            failure_class="RATE_LIMIT", target="secondary", reason="RATE_LIMIT",
        )
        digest_before = self.owner.state_digest()
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            ledger = reopened.provider_retry_budget_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["bound"], "enforced")
            self.assertEqual(reopened.snapshot()["provider_retry_budget"][0]["max_retries"], 3)
            self.assertEqual(reopened.state_digest(), digest_before)


class ProviderAccessGateLedgerTests(unittest.TestCase):
    # Node 1-1-4: the controlled boundary between the loopback/fake baseline and
    # a real Provider is recorded per run so every run's classification (real vs
    # baseline) is auditable; the reason-required rule stays fail-closed.

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def _run(self) -> None:
        self.owner.create_run("run-1", "provider.read-only", {"request": "fixture"})
        self.owner.start_run("run-1")

    def test_record_and_read_real_decision(self) -> None:
        self._run()
        ledger_id = self.owner.record_provider_access_gate(
            "run-1", "real", True, "explicit real_provider_gate enabled; real Provider profile selected",
            provider_id="custom", profile_name="ark",
        )
        entry = self.owner.get_provider_access_gate(ledger_id)
        self.assertEqual(entry["classification"], "real")
        self.assertTrue(entry["gate_enabled"])
        self.assertEqual(entry["provider_id"], "custom")
        self.assertEqual(entry["profile_name"], "ark")

    def test_record_and_read_baseline_decision(self) -> None:
        self._run()
        ledger_id = self.owner.record_provider_access_gate(
            "run-1", "baseline", False, "no real Provider profile; loopback/fake baseline",
            provider_id="fake-loopback", profile_name=None,
        )
        entry = self.owner.get_provider_access_gate(ledger_id)
        self.assertEqual(entry["classification"], "baseline")
        self.assertFalse(entry["gate_enabled"])
        self.assertIsNone(entry["profile_name"])

    def test_for_run_returns_recorded_decision(self) -> None:
        self._run()
        self.owner.record_provider_access_gate(
            "run-1", "baseline", False, "no real Provider profile; loopback/fake baseline",
        )
        entries = self.owner.provider_access_gate_ledger_for_run("run-1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["classification"], "baseline")

    def test_invalid_classification_rejected(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_access_gate("run-1", "weird", False, "nope")

    def test_reason_required_fail_closed(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_provider_access_gate("run-1", "baseline", False, "")
        with self.assertRaises(ValueError):
            self.owner.record_provider_access_gate("run-1", "baseline", False, "   ")

    def test_missing_entry_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_access_gate("missing")

    def test_survives_reopen_and_appears_in_snapshot(self) -> None:
        self._run()
        self.owner.record_provider_access_gate(
            "run-1", "baseline", False, "no real Provider profile; loopback/fake baseline",
        )
        digest_before = self.owner.state_digest()
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            ledger = reopened.provider_access_gate_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["classification"], "baseline")
            self.assertIn("provider_access_gate_ledger", reopened.snapshot())
            self.assertEqual(reopened.state_digest(), digest_before)


class EvidenceSourceClassificationTests(unittest.TestCase):
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

    def test_record_result_requires_evidence_source(self) -> None:
        self._run()
        with self.assertRaises(TypeError):
            self.owner.record_result("run-1", "adapter", {"x": 1}, "source")

    def test_record_event_requires_evidence_source(self) -> None:
        self._run()
        with self.assertRaises(TypeError):
            self.owner.record_event("run-1", "worker.started", {"x": 1})

    def test_record_result_rejects_invalid_evidence_source(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.record_result("run-1", "adapter", {"x": 1}, "source", evidence_source="made-up")

    def test_record_result_persists_and_round_trips_evidence_source(self) -> None:
        self._run()
        recorded = self.owner.record_result(
            "run-1", "adapter", {"x": 1}, "source", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED
        )
        self.assertEqual(recorded["evidence_source"], EVIDENCE_SOURCE_OUTER_COMPOSED)
        reopened = CompositionOwner(self.db)
        try:
            run = reopened.get_run("run-1")
            self.assertEqual({r["evidence_source"] for r in run["results"]}, {EVIDENCE_SOURCE_OUTER_COMPOSED})
        finally:
            reopened.close()

    def test_record_event_persists_evidence_source(self) -> None:
        self._run()
        recorded = self.owner.record_event(
            "run-1", "worker.started", {"x": 1}, evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED
        )
        self.assertEqual(recorded["evidence_source"], EVIDENCE_SOURCE_OUTER_COMPOSED)

    def test_plugin_composed_is_an_allowed_evidence_source(self) -> None:
        self._run()
        recorded = self.owner.record_result(
            "run-1", "adapter", {"x": 1}, "source", evidence_source=EVIDENCE_SOURCE_PLUGIN_COMPOSED
        )
        self.assertEqual(recorded["evidence_source"], EVIDENCE_SOURCE_PLUGIN_COMPOSED)

    def test_schema_migration_adds_evidence_source_to_v1_database(self) -> None:
        import sqlite3 as _sqlite
        import os

        self.owner.close()
        # Start from a clean path: drop the v2 schema created by setUp so we can
        # reconstruct a legacy v1 database by hand.
        self.db.unlink()
        # Build a v1 database by hand: no evidence_source column, user_version=1.
        connection = _sqlite.connect(str(self.db))
        connection.executescript(
            """
            CREATE TABLE owner_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE runs(
                run_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                input_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE results(
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        connection.close()

        with CompositionOwner(self.db) as migrated:
            health = CompositionOwner._check_database_integrity(self.db)
            self.assertGreaterEqual(health.get("user_version", 0), 2)
            columns = {
                row["name"]
                for row in migrated._require_connection().execute("PRAGMA table_info(results)")
            }
            self.assertIn("evidence_source", columns)
            migrated.create_run("run-1", "unit-test", {"prompt": "fixture"})
            migrated.start_run("run-1")
            recorded = migrated.record_result(
                "run-1", "adapter", {"x": 1}, "source", evidence_source=EVIDENCE_SOURCE_NATIVE
            )
            self.assertEqual(recorded["evidence_source"], EVIDENCE_SOURCE_NATIVE)


class RunLevelAttemptNotFirstClassTests(unittest.TestCase):
    """1-6-2 (decided): owner does NOT hold a run-level attempt first-class entity.

    Run-level retry is expressed indirectly via effect_attempts (the effect-level
    first-class entity): one run retry == re-claiming the effect (attempt increments).
    runs table has no attempt column and there is no run_attempts table.
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def _schema_tables(self) -> set[str]:
        conn = sqlite3.connect(self.db)
        try:
            return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()

    def _runs_columns(self) -> list[str]:
        conn = sqlite3.connect(self.db)
        try:
            return [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
        finally:
            conn.close()

    def test_runs_table_has_no_attempt_column(self) -> None:
        self.assertNotIn("attempt", self._runs_columns())

    def test_no_run_attempts_first_class_table(self) -> None:
        self.assertNotIn("run_attempts", self._schema_tables())

    def test_run_retry_expressed_via_effect_attempts(self) -> None:
        self.owner.create_run("run-1", "unit-test", {"prompt": "fixture"})
        self.owner.start_run("run-1")
        request = self.owner.request_approval("run-1", "op-1", "deploy", "sink", "idem-1", "publish")
        grant = self.owner.approve(request["approval_id"])
        claim = self.owner.claim_effect(
            "run-1", "op-1", "deploy", "sink", "idem-1", "approval-required", grant["token"]
        )
        self.owner.complete_effect(claim.effect_id, {"delivered": True})
        # effect_attempts captured the attempt (effect-level first-class entity)
        conn = sqlite3.connect(self.db)
        try:
            effect_attempt_rows = list(conn.execute("SELECT * FROM effect_attempts"))
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("SELECT * FROM run_attempts")
        finally:
            conn.close()
        self.assertTrue(effect_attempt_rows)


class OwnerIsolatedAuditTests(unittest.TestCase):
    """1-6-3 (decided): audit_owner_isolated promotes the 'no second canonical
    state' invariant from discipline to a testable contract (CI assertion carrier).
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def test_owner_is_unique_with_no_extra_tables(self) -> None:
        report = self.owner.audit_owner_isolated()
        self.assertTrue(report["owner_is_unique"])
        self.assertEqual(report["non_canonical_tables"], [])
        self.assertEqual(report["actual_canonical_count"], report["expected_canonical_count"])

    def test_audit_reports_extra_table_as_second_canonical_state(self) -> None:
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("CREATE TABLE second_canonical (id TEXT PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()
        report = self.owner.audit_owner_isolated()
        self.assertFalse(report["owner_is_unique"])
        self.assertIn("second_canonical", report["non_canonical_tables"])


class UnknownTerminologyTwoLayerTests(unittest.TestCase):
    """1-6-4 (decided): unknown terminology has two distinct layers.

    Layer 1 (remote/delegated): when a remote identity is genuinely unknown, the
    literal string "unknown" (or "unknown/delegated" caliber) is STORED -- we
    record that we do not know the remote state.
    Layer 2 (internal identity): when an internal durable-identity reference is
    missing, the run is safe-stopped and NO fabricated "unknown" value is stored;
    the gap is surfaced as a terminal safe-stop + identity-violation event.
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def test_layer1_remote_unknown_is_stored_literally(self) -> None:
        self.owner.create_run("run-1", "unit-test", {"prompt": "x"})
        self.owner.record_provider_exit_ledger("run-1", {})
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT provider, endpoint, provider_remote_zero_residue "
                "FROM provider_exit_ledger WHERE run_id = 'run-1'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "unknown")  # provider missing -> literal unknown stored (layer 1)
        self.assertEqual(row[1], "unknown")  # endpoint missing -> literal unknown stored (layer 1)
        self.assertEqual(row[2], "unknown/delegated")  # remote residue caliber stored literally

    def test_layer2_internal_identity_missing_safe_stops_without_unknown_value(self) -> None:
        self.owner.create_run(
            "run-1", "unit-test", {"prompt": "x"}, metadata={"parent_run_id": "ghost-run"}
        )
        violations = self.owner.detect_identity_violations("run-1")
        self.assertEqual(violations[0]["kind"], "broken_parent_run_id")
        result = self.owner.safe_stop_on_identity_violation("run-1")
        self.assertTrue(result["safe_stopped"])
        run = self.owner.get_run("run-1")
        self.assertEqual(run["status"], "safe_stopped")
        # The internal gap is surfaced as a terminal safe-stop + identity-violation
        # event; no fabricated "unknown" value is stored as an identity column.
        event_types = {e["type"] for e in self.owner.events("run-1")}
        self.assertIn("run.identity.violation", event_types)


class DeclaredExposureTests(unittest.TestCase):
    """1-4-1: Q4 preflight-class deny enforced via declared_side_effects/exposure.

    The declaration is opt-in at preflight: claim_effect only enforces it when
    one exists for the run.  Any breach safe-stops the run (fail-closed).
    """

    def _owner(self, tmp: Path) -> CompositionOwner:
        owner = CompositionOwner(tmp / "owner.sqlite3")
        owner.create_run("run-q4", "effect", {"x": 1})
        return owner

    def test_declare_and_get_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owner = self._owner(root)
            declared = owner.declare_exposure(
                "run-q4",
                declared_side_effects=["idempotent", "approval-required"],
                exposure={"workspace_root": "/tmp/ws", "network": True, "credentials": False, "subprocess": False},
            )
            self.assertEqual(declared["declared_side_effects"], ["approval-required", "idempotent"])
            got = owner.get_declared_exposure("run-q4")
            assert got is not None
            self.assertEqual(got["exposure"]["workspace_root"], "/tmp/ws")
            self.assertTrue(got["exposure"]["network"])
            self.assertFalse(got["exposure"]["credentials"])
            # Idempotent re-declare replaces the boundary.
            owner.declare_exposure("run-q4", declared_side_effects=["idempotent"], exposure={"workspace_root": "/tmp/ws2"})
            self.assertEqual(owner.get_declared_exposure("run-q4")["declared_side_effects"], ["idempotent"])
            self.assertEqual(owner.get_declared_exposure("run-q4")["exposure"]["workspace_root"], "/tmp/ws2")
            owner.close()

    def test_claim_allowed_within_declared_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            ws.mkdir()
            owner = self._owner(root)
            owner.declare_exposure(
                "run-q4",
                declared_side_effects=["idempotent"],
                exposure={"workspace_root": str(ws), "network": False, "credentials": False, "subprocess": False},
            )
            claim = owner.claim_effect("run-q4", "op1", "act", str(ws / "file"), "k1", "idempotent", required_exposure={"workspace"})
            self.assertTrue(claim.executable)
            self.assertEqual(claim.status, "claimed")
            owner.close()

    def test_claim_denied_side_effect_not_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            ws.mkdir()
            owner = self._owner(root)
            owner.declare_exposure("run-q4", declared_side_effects=["approval-required"], exposure={"workspace_root": str(ws)})
            claim = owner.claim_effect("run-q4", "op2", "act", str(ws / "file"), "k2", "idempotent")
            self.assertFalse(claim.executable)
            self.assertEqual(claim.reason, "side_effect_not_declared")
            self.assertEqual(owner.get_run("run-q4")["status"], "safe_stopped")
            owner.close()

    def test_claim_denied_workspace_out_of_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            ws.mkdir()
            outside = root / "outside" / "file"
            owner = self._owner(root)
            owner.declare_exposure("run-q4", declared_side_effects=["idempotent"], exposure={"workspace_root": str(ws)})
            claim = owner.claim_effect("run-q4", "op3", "act", str(outside), "k3", "idempotent", required_exposure={"workspace"})
            self.assertFalse(claim.executable)
            self.assertEqual(claim.reason, "workspace_out_of_bounds")
            self.assertEqual(owner.get_run("run-q4")["status"], "safe_stopped")
            owner.close()

    def test_claim_denied_exposure_not_declared(self) -> None:
        for capability in ("network", "credentials", "subprocess"):
            with self.subTest(capability=capability), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ws = root / "ws"
                ws.mkdir()
                owner = self._owner(root)
                owner.declare_exposure(
                    "run-q4",
                    declared_side_effects=["idempotent"],
                    exposure={"workspace_root": str(ws), "network": False, "credentials": False, "subprocess": False},
                )
                claim = owner.claim_effect("run-q4", "op-x", "act", str(ws / "file"), "k-x", "idempotent", required_exposure={capability})
                self.assertFalse(claim.executable)
                self.assertEqual(claim.reason, "exposure_not_declared")
                owner.close()

    def test_claim_proceeds_without_declaration_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owner = self._owner(root)
            # No declaration: legacy behaviour, claim allowed (idempotent, no approval).
            claim = owner.claim_effect("run-q4", "op5", "act", "/some/resource", "k5", "idempotent")
            self.assertTrue(claim.executable)
            self.assertEqual(claim.status, "claimed")
            owner.close()


if __name__ == "__main__":
    unittest.main()
