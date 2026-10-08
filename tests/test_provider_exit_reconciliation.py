from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from scripts import record_provider_exit_receipt as receipt

from src.zworkbench.composition import CompositionOwner, NotFoundError


def build_valid_receipt(**overrides) -> dict:
    values = {
        "provider": "volcengine-ark",
        "region": "cn-beijing",
        "account_scope": "personal",
        "provider_console_observation": "no-visible-error",
        "provider_request_response_surface": "not-exposed-by-provider",
        "task_surface_observation": "visible-with-status",
        "backup_surface_observation": "visible-with-status",
        "retention_surface_observation": "visible-with-status",
        "project_fingerprint": "1" * 64,
        "inventory_fingerprint": "2" * 64,
        "evidence_fingerprint": "3" * 64,
        "local_state_fingerprint": "4" * 64,
        "exit_mode": "authorized-manual-exit",
        "task_status": "identified-stopped",
        "webhook_status": "disabled",
        "backup_status": "exported",
        "data_status": "confirmed",
        "key_status": "deleted",
        "billing_status": "settled",
        "subscription_status": "cancelled",
        "account_status": "closure-submitted",
        "local_status": "stopped-and-cleaned",
        "action_status": "confirmed",
    }
    values.update(overrides)
    return receipt.build_receipt(argparse.Namespace(**values))


class ProviderExitReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "state" / "composition.sqlite3"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()
        self.tempdir.cleanup()

    def _run(self, run_id: str = "run-1") -> None:
        self.owner.create_run(run_id, "unit-test", {"prompt": "fixture"})
        self.owner.start_run(run_id)

    def test_default_path_evidence_class_is_local_inventory(self) -> None:
        # C7: the default loopback/fake path is structurally a local inventory,
        # never an owner-backed Provider clearance claim.
        self._run()
        entry = self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        self.assertEqual(entry["evidence_class"], "local-inventory")
        self.assertEqual(entry["provider_remote_zero_residue"], "unknown/delegated")

    def test_attach_owner_receipt_appends_owner_backed_entry(self) -> None:
        # C7: owner-backed evidence supplements (does not replace) the local
        # inventory entry, and stays unknown/delegated.
        self._run()
        self.owner.record_provider_exit_ledger(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        redacted = build_valid_receipt()
        attached = self.owner.attach_provider_exit_receipt("run-1", redacted)
        self.assertEqual(attached["evidence_class"], "owner-backed")
        self.assertEqual(attached["exit_status"], redacted["exit_status"])
        self.assertEqual(attached["provider_remote_zero_residue"], "unknown/delegated")
        entries = self.owner.provider_exit_ledger_for_run("run-1")
        self.assertEqual(len(entries), 2)

    def test_owner_backed_and_local_inventory_coexist(self) -> None:
        # The durable distinction "本地退出 ≠ Provider 退出" is queryable.
        self._run()
        self.owner.record_provider_exit_ledger_once(
            "run-1", {"provider": "fake-loopback", "endpoint": "http://127.0.0.1:11434"}
        )
        self.owner.attach_provider_exit_receipt("run-1", build_valid_receipt())
        classes = {e["evidence_class"] for e in self.owner.provider_exit_ledger_for_run("run-1")}
        self.assertEqual(classes, {"local-inventory", "owner-backed"})

    def test_attach_rejects_non_v2_schema(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.attach_provider_exit_receipt("run-1", {"schema": "wrong/v1"})

    def test_attach_rejects_receipt_claiming_provider_clearance(self) -> None:
        # Fail-closed: a tampered receipt that claims remote zero residue must
        # be rejected so local/owner evidence never becomes a Provider proof.
        self._run()
        tampered = build_valid_receipt()
        tampered["provider_remote_zero_residue"] = "cleared"
        with self.assertRaises(ValueError):
            self.owner.attach_provider_exit_receipt("run-1", tampered)

    def test_attach_rejects_secret_shaped_value(self) -> None:
        self._run()
        tampered = build_valid_receipt()
        tampered["notes"] = "leaked sk-" + "a" * 20
        with self.assertRaises(ValueError):
            self.owner.attach_provider_exit_receipt("run-1", tampered)

    def test_attach_rejects_non_mapping_receipt(self) -> None:
        self._run()
        with self.assertRaises(ValueError):
            self.owner.attach_provider_exit_receipt("run-1", "not-a-receipt")  # type: ignore[arg-type]

    def test_attached_entry_survives_reopen(self) -> None:
        self._run()
        self.owner.attach_provider_exit_receipt("run-1", build_valid_receipt())
        self.owner.close()
        with CompositionOwner(self.db) as reopened:
            entries = reopened.provider_exit_ledger_for_run("run-1")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["evidence_class"], "owner-backed")

    def test_get_missing_ledger_entry_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.owner.get_provider_exit_ledger("missing")


if __name__ == "__main__":
    unittest.main()
