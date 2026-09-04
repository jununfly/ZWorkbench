from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_optional_provider_probe as probe  # noqa: E402


class OptionalProviderProbeTests(unittest.TestCase):
    def _preflight(self, **overrides):
        value = {
            "region": "cn-beijing",
            "project_fingerprint": "a" * 64,
            "budget_requests": 1,
            "max_duration_seconds": 30,
            "key_scope_confirmed": True,
            "data_retention_confirmed": True,
            "remote_inventory_confirmed": True,
            "exit_path_confirmed": True,
            "one_time_authorization_confirmed": True,
        }
        value.update(overrides)
        return value

    def test_empty_credential_stops_without_network_and_only_records_fingerprint(self) -> None:
        result = probe.run(probe.DEFAULT_ENDPOINT, probe.DEFAULT_MODEL, b"")
        self.assertEqual(result["outcome"], "input_empty")
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(result["retry_count"], 0)
        self.assertNotIn("Authorization", json.dumps(result))

    def test_raw_credential_is_not_part_of_redacted_result(self) -> None:
        secret = b"sk-test-secret-that-must-not-be-written"
        result = probe.base_result(probe.DEFAULT_ENDPOINT, probe.DEFAULT_MODEL, secret)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(secret.decode("ascii"), serialized)
        self.assertEqual(result["credential"]["api_key_fingerprint"], probe.digest(secret))

    def test_endpoint_is_fixed_to_ark_coding_responses_host(self) -> None:
        probe.validate_endpoint(probe.DEFAULT_ENDPOINT)
        with self.assertRaises(ValueError):
            probe.validate_endpoint("https://example.invalid/api/coding/v3/responses")
        with self.assertRaises(ValueError):
            probe.validate_endpoint("http://ark.cn-beijing.volces.com/api/coding/v3/responses")

    def test_response_shape_does_not_persist_response_body(self) -> None:
        body = b'{"id":"resp_123","model":"ark-code-latest","output":[{"content":[{"text":"{\\"status\\":\\"ok\\",\\"answer\\":\\"staging-fixture-001\\"}"}]}]}'
        shape = probe.response_shape(body)
        serialized = json.dumps(shape, ensure_ascii=False)
        self.assertNotIn("resp_123", serialized)
        self.assertNotIn("staging-fixture-001", serialized)
        self.assertTrue(shape["fixture_token_present"])
        self.assertEqual(shape["response_id_sha256"], probe.digest(b"resp_123"))
        self.assertTrue(shape["response_status_ok"])
        self.assertTrue(shape["response_answer_fixture"])
        self.assertTrue(shape["semantic_fixture_exact"])

    def test_real_credential_cannot_run_without_verified_human_preflight(self) -> None:
        result = probe.run(probe.DEFAULT_ENDPOINT, probe.DEFAULT_MODEL, b"sk-test-secret")
        self.assertEqual(result["outcome"], "preflight_blocked")
        self.assertEqual(result["request_count"], 0)
        self.assertNotIn("sk-test-secret", json.dumps(result))

    def test_preflight_requires_identity_gates_and_bounded_budget(self) -> None:
        verified = probe.validate_preflight(self._preflight(), repeats=1)
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["project_fingerprint"], "a" * 64)
        with self.assertRaises(ValueError):
            probe.validate_preflight(self._preflight(remote_inventory_confirmed=False))
        with self.assertRaises(ValueError):
            probe.validate_preflight(self._preflight(project_fingerprint="not-a-fingerprint"))
        with self.assertRaises(ValueError):
            probe.validate_preflight(self._preflight(budget_requests=1), repeats=2)
        with self.assertRaises(ValueError):
            probe.validate_preflight(self._preflight(region="en_beijing"), repeats=1)

    def test_project_fingerprint_must_not_reuse_api_key_fingerprint(self) -> None:
        secret = b"sk-test-secret"
        result = probe.run_repeated(
            probe.DEFAULT_ENDPOINT,
            probe.DEFAULT_MODEL,
            secret,
            preflight=self._preflight(project_fingerprint=probe.digest(secret)),
            repeats=1,
        )
        self.assertEqual(result["outcome"], "preflight_blocked")
        self.assertEqual(result["error_type"], "CredentialProjectIdentityCollisionError")
        self.assertEqual(result["request_count"], 0)
        self.assertNotIn(secret.decode("ascii"), json.dumps(result))

    def test_five_explicit_semantic_requests_are_not_retries(self) -> None:
        response = {
            "json": True,
            "fixture_token_present": True,
            "semantic_fixture_exact": True,
            "response_model": "auto",
        }
        one = {"outcome": "http_success", "request_count": 1, "response": response}
        with patch.object(probe, "run", side_effect=[one.copy() for _ in range(5)]) as mocked:
            result = probe.run_repeated(
                probe.DEFAULT_ENDPOINT,
                probe.DEFAULT_MODEL,
                b"sk-test-secret",
                preflight=self._preflight(budget_requests=5),
                repeats=5,
            )
        self.assertEqual(result["outcome"], "http_success")
        self.assertEqual(result["compatibility_status"], "verified-for-authorized-read-only-staging")
        self.assertEqual(result["request_count"], 5)
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(mocked.call_count, 5)


if __name__ == "__main__":
    unittest.main()
