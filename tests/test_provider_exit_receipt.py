from __future__ import annotations

import argparse
import json
from pathlib import Path
import unittest

from scripts import record_provider_exit_receipt as receipt


def make_args(**overrides):
    values = {
        "provider": "volcengine-ark",
        "region": "cn-beijing",
        "account_scope": "personal",
        "provider_console_observation": "unknown",
        "provider_request_response_surface": "unknown",
        "task_surface_observation": "unknown",
        "backup_surface_observation": "unknown",
        "retention_surface_observation": "unknown",
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
        self.assertEqual(result["unknown_fields"], ["backup_or_snapshot", "backup_surface_observation", "coding_data", "local_state_fingerprint", "provider_console_observation", "provider_request_response_surface", "retention_surface_observation", "task_or_run", "task_surface_observation", "webhook_or_integration"])
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
                provider_console_observation="no-visible-error",
                provider_request_response_surface="not-exposed-by-provider",
                task_surface_observation="visible-with-status",
                backup_surface_observation="visible-with-status",
                retention_surface_observation="visible-with-status",
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

    def test_account_scope_is_a_redacted_category_not_an_account_identifier(self) -> None:
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(account_scope="owner@example.com"))
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(account_scope="ark-project-123"))

    def test_library_rejects_unknown_exit_mode(self) -> None:
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(exit_mode="delete-everything"))

    def test_console_observation_and_non_exposed_surface_are_recorded_separately(self) -> None:
        result = receipt.build_receipt(
            make_args(
                provider_console_observation="no-visible-error",
                provider_request_response_surface="not-exposed-by-provider",
                task_status="none-observed",
                webhook_status="none-observed",
                backup_status="none-observed",
                data_status="not-requested",
                local_state_fingerprint="4" * 64,
                task_surface_observation="visible-with-status",
                backup_surface_observation="visible-with-status",
                retention_surface_observation="visible-with-status",
            )
        )
        self.assertEqual(result["provider_console_observation"], "no-visible-error")
        self.assertEqual(result["provider_request_response_surface"], "not-exposed-by-provider")
        self.assertEqual(result["unknown_fields"], [])
        self.assertEqual(result["exit_status"], "inventory-recorded-exit-not-performed")
        self.assertEqual(result["provider_remote_zero_residue"], "unknown/delegated")
        self.assertIn("product observability only", " ".join(result["non_claims"]))

    def test_visible_console_error_safe_stops_without_claiming_remote_exit(self) -> None:
        result = receipt.build_receipt(
            make_args(
                provider_console_observation="visible-error",
                provider_request_response_surface="not-exposed-by-provider",
                task_status="none-observed",
                webhook_status="none-observed",
                backup_status="none-observed",
                data_status="not-requested",
                local_state_fingerprint="4" * 64,
                task_surface_observation="visible-with-status",
                backup_surface_observation="visible-with-status",
                retention_surface_observation="visible-with-status",
            )
        )
        self.assertEqual(result["unknown_fields"], [])
        self.assertEqual(result["exit_status"], "unknown/safe-stop")

    def test_unknown_observability_values_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(provider_console_observation="healthy"))
        with self.assertRaises(ValueError):
            receipt.build_receipt(make_args(provider_request_response_surface="hidden"))

    def test_not_exposed_surfaces_are_recorded_without_inference_of_absence(self) -> None:
        result = receipt.build_receipt(
            make_args(
                provider_console_observation="no-visible-error",
                provider_request_response_surface="not-exposed-by-provider",
                task_surface_observation="not-exposed-by-provider",
                backup_surface_observation="not-exposed-by-provider",
                retention_surface_observation="not-exposed-by-provider",
                task_status="unknown",
                webhook_status="none-observed",
                backup_status="unknown",
                data_status="unknown",
                local_state_fingerprint="4" * 64,
            )
        )
        self.assertEqual(result["statuses"]["task_or_run"], "not-exposed-by-provider")
        self.assertEqual(result["statuses"]["backup_or_snapshot"], "not-exposed-by-provider")
        self.assertEqual(result["statuses"]["coding_data"], "not-exposed-by-provider")
        self.assertEqual(result["unknown_fields"], [])
        self.assertEqual(result["provider_observability_status"], "pass-with-owner-attestation")
        self.assertEqual(result["exit_status"], "inventory-recorded-exit-not-performed")
        self.assertEqual(result["provider_remote_zero_residue"], "unknown/delegated")

    def test_surface_and_status_mismatch_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            receipt.build_receipt(
                make_args(
                    task_surface_observation="visible-with-status",
                    task_status="unknown",
                )
            )
        with self.assertRaises(ValueError):
            receipt.build_receipt(
                make_args(
                    backup_surface_observation="unknown",
                    backup_status="none-observed",
                )
            )

    def test_inventory_wizard_has_no_provider_side_action_path(self) -> None:
        wizard = Path(__file__).parents[1] / "scripts" / "optional-provider-exit.sh"
        source = wizard.read_text(encoding="utf-8")
        self.assertIn('EXIT_MODE="inventory-only"', source)
        self.assertIn('ACTION_STATUS="not-performed"', source)
        self.assertIn('PROVIDER_CONSOLE_OBSERVATION="${ZWB_PROVIDER_CONSOLE_OBSERVATION:-}"', source)
        self.assertIn('PROVIDER_REQUEST_RESPONSE_SURFACE="${ZWB_PROVIDER_REQUEST_RESPONSE_SURFACE:-}"', source)
        self.assertIn('TASK_SURFACE_OBSERVATION="${ZWB_PROVIDER_TASK_SURFACE_OBSERVATION:-}"', source)
        self.assertIn('BACKUP_SURFACE_OBSERVATION="${ZWB_PROVIDER_BACKUP_SURFACE_OBSERVATION:-}"', source)
        self.assertIn('RETENTION_SURFACE_OBSERVATION="${ZWB_PROVIDER_RETENTION_SURFACE_OBSERVATION:-}"', source)
        self.assertIn('--provider-console-observation "$PROVIDER_CONSOLE_OBSERVATION"', source)
        self.assertIn('--provider-request-response-surface "$PROVIDER_REQUEST_RESPONSE_SURFACE"', source)
        self.assertIn('--task-surface-observation "$TASK_SURFACE_OBSERVATION"', source)
        self.assertIn('--backup-surface-observation "$BACKUP_SURFACE_OBSERVATION"', source)
        self.assertIn('--retention-surface-observation "$RETENTION_SURFACE_OBSERVATION"', source)
        self.assertNotIn("ask EXIT_MODE", source)
        self.assertNotIn("ask ACTION_STATUS", source)
        self.assertNotIn("authorized-manual-exit", source)
        self.assertNotIn("Perform only the exact actions", source)
        self.assertNotIn("https://www.volcengine.com/docs/6256/157919", source)


if __name__ == "__main__":
    unittest.main()
