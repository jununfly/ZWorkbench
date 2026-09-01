from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_optional_provider_probe as probe  # noqa: E402


class OptionalProviderProbeTests(unittest.TestCase):
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
        body = b'{"id":"resp_123","model":"ark-code-latest","output":"staging-fixture-001"}'
        shape = probe.response_shape(body)
        serialized = json.dumps(shape, ensure_ascii=False)
        self.assertNotIn("resp_123", serialized)
        self.assertNotIn("staging-fixture-001", serialized)
        self.assertTrue(shape["fixture_token_present"])
        self.assertEqual(shape["response_id_sha256"], probe.digest(b"resp_123"))


if __name__ == "__main__":
    unittest.main()
