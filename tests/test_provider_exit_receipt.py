from __future__ import annotations

import argparse
import json
import unittest

from scripts import record_provider_exit_receipt as receipt


def make_args(**overrides):
    values = {
        "provider": "volcengine-ark",
        "region": "cn-beijing",
        "account_scope": "personal",
        "project_fingerprint": "1" * 64,
        "inventory_fingerprint": "2" * 64,
        "evidence_fingerprint": "3" * 64,
        "local_state_fingerprint": "unknown",
        "exit_mode": "inventory-only",
        "task_status": "unknown",
        "webhook_status": "unknown",
        "backup_status": "unknown",
        "data_status": "unknown",
        "key_status": "not-touched",
        "billing_status": "not-reviewed",
        "subscription_status": "active",
        "account_status": "active",
        "local_status": "retained-for-evidence",
        "action_status": "not-performed",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ProviderExitReceiptTests(unittest.TestCase):
    def test_inventory_only_preserves_unknown_and_never_claims_remote_zero_residue(self) -> None:
        result = receipt.build_receipt(make_args())
        self.assertEqual(result["exit_status"], "unknown/safe-stop")
        self.assertEqual(result["unknown_fields"], ["backup_or_snapshot", "coding_data", "local_state_fingerprint", "task_or_run", "webhook_or_integration"])
        self.assertEqual(result["provider_remote_zero_residue"], "unknown/delegated")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("fixture-secret", serialized)
        self.assertNotIn("Bearer ", serialized)

    def test_authorized_manual_receipt_stays_delegated_even_when_actions_are_confirmed(self) -> None:
        result = receipt.build_receipt(
            make_args(
                exit_mode="authorized-manual-exit",
                task_status="identified-stopped",
                webhook_status="disabled",
                backup_status="retained-by-policy",
                data_status="confirmed",
                key_status="deleted",
                billing_status="settled",
                subscription_status="cancelled",
                account_status="closure-submitted",
                action_status="confirmed",
                local_state_fingerprint="4" * 64,
            )
        )
        self.assertEqual(result["exit_status"], "provider-receipt-recorded-final-residue-unknown")
        self.assertEqual(result["unknown_fields"], [])
        self.assertEqual(result["provider_remote_zero_residue"], "unknown/delegated")

    def test_unknown_or_raw_credential_shaped_fingerprint_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(project_fingerprint="fixture-secret"))
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(region="us-east-1"))


if __name__ == "__main__":
    unittest.main()
