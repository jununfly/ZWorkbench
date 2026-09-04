from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_capability_broker" / "v1"
import sys

sys.path.insert(0, str(FIXTURE))
sys.path.insert(0, str(REPO_ROOT / "evaluation" / "runner"))

from capability_broker import POLICY_SCHEMA, SCHEMA, process_request  # noqa: E402
from run_w8_broker_capability_surface import policy_for  # noqa: E402


class W8CapabilityBrokerTests(unittest.TestCase):
    def make_policy(self, root: Path):
        return policy_for(root / "workspace")

    def test_external_dns_is_denied_without_calling_system_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit = root / "audit.jsonl"
            with patch("capability_broker.socket.getaddrinfo", side_effect=AssertionError("system resolver must not be called")) as resolver:
                response = process_request(
                    {"schema": SCHEMA, "request_id": "dns-1", "operation": "dns.resolve", "resource_class": "dns", "hostname": "api.example.com"},
                    self.make_policy(root),
                    audit,
                )
            self.assertEqual(response["decision"], "deny")
            self.assertEqual(response["reason"], "dns_name_not_allowlisted")
            resolver.assert_not_called()
            self.assertEqual(len(audit.read_text(encoding="utf-8").splitlines()), 1)

    def test_loopback_dns_uses_static_broker_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            response = process_request(
                {"schema": SCHEMA, "request_id": "dns-2", "operation": "dns.resolve", "resource_class": "dns", "hostname": "localhost"},
                self.make_policy(root),
                root / "audit.jsonl",
            )
            self.assertEqual(response["decision"], "allow")
            self.assertEqual(response["resolved_addresses"], ["127.0.0.1"])
            self.assertEqual(response["resolution_mode"], "static-broker-allowlist")
            self.assertEqual(response["external_io_count"], 0)

    def test_credential_request_is_denied_without_echoing_resource_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            response = process_request(
                {"schema": SCHEMA, "request_id": "credential-1", "operation": "credential.read", "resource_class": "credential", "target": "credential://provider/api-key"},
                self.make_policy(root),
                root / "audit.jsonl",
            )
            self.assertEqual(response["decision"], "deny")
            self.assertEqual(response["reason"], "credential_access_not_allowlisted")
            self.assertNotIn("api-key", json.dumps(response))
            self.assertEqual(response["physical_effect_count"], 0)

    def test_outside_write_is_denied_and_audit_is_durable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.txt"
            outside.write_text("original\n", encoding="utf-8")
            audit = root / "audit.jsonl"
            response = process_request(
                {"schema": SCHEMA, "request_id": "write-1", "operation": "effect.write", "resource_class": "effect", "target": str(outside), "content": "must-not-write"},
                self.make_policy(root),
                audit,
            )
            self.assertEqual(response["decision"], "deny")
            self.assertEqual(response["reason"], "target_outside_workspace")
            self.assertEqual(outside.read_text(encoding="utf-8"), "original\n")
            self.assertEqual(json.loads(audit.read_text(encoding="utf-8"))["effect_status"], "not-performed")

    def test_inside_write_records_claim_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            audit = root / "audit.jsonl"
            response = process_request(
                {"schema": SCHEMA, "request_id": "write-2", "operation": "effect.write", "resource_class": "effect", "target": str(workspace / "allowed.txt"), "content": "allowed"},
                self.make_policy(root),
                audit,
            )
            records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(response["effect_status"], "completed")
            self.assertEqual([record["phase"] for record in records], ["decision", "complete"])
            self.assertEqual(records[0]["physical_effect_count"], 0)
            self.assertEqual(records[1]["physical_effect_count"], 1)
            self.assertEqual((workspace / "allowed.txt").read_text(encoding="utf-8"), "allowed")

    def test_unknown_protocol_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            response = process_request({}, self.make_policy(root), root / "audit.jsonl")
            self.assertEqual(response["decision"], "deny")
            self.assertEqual(response["reason"], "request_schema_mismatch")
            self.assertEqual(response["schema"], SCHEMA)
            self.assertEqual(self.make_policy(root)["schema"], POLICY_SCHEMA)


if __name__ == "__main__":
    unittest.main()
