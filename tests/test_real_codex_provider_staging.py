from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_real_codex_provider_staging as staging  # noqa: E402


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

# Simulate the real Codex shell snapshot behavior: inherited environment values
# may be written under CODEX_HOME. The runner must keep that runtime home out
# of shareable evidence and remove it before producing summary.json.
Path(os.environ["CODEX_HOME"], "simulated-shell-snapshot").write_bytes(os.environ["ARK_API_KEY"].encode())

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        continue
    if method == "initialize":
        result = {}
    elif method == "thread/start":
        result = {"thread": {"id": "thread-real-staging"}}
    elif method == "turn/start":
        result = {"turn": {"id": "turn-real-staging"}}
    elif method == "thread/read":
        result = {"thread": {"id": "thread-real-staging"}}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)
    if method == "turn/start":
        delta = json.dumps({"answer": "staging-fixture-001", "status": "ok"}, separators=(",", ":"))
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "item/agentMessage/delta",
            "params": {"turnId": "turn-real-staging", "delta": delta},
        }), flush=True)
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {"threadId": "thread-real-staging", "turn": {"id": "turn-real-staging", "status": "completed"}},
        }), flush=True)
'''


class RealCodexProviderStagingTests(unittest.TestCase):
    def _fake_codex(self, root: Path) -> Path:
        path = root / "codex"
        path.write_text(FAKE_CODEX, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_validation_rejects_wrong_region_and_unpinned_base_url(self) -> None:
        with self.assertRaises(ValueError):
            staging.validate_inputs(
                staging.DEFAULT_BASE_URL,
                staging.DEFAULT_MODEL,
                "en_beijing",
                "a" * 64,
                staging.DEFAULT_CREDENTIAL_ENV,
                90,
            )
        with self.assertRaises(ValueError):
            staging.validate_base_url("https://example.invalid/api/coding/v3")

    def test_persisted_event_summary_drops_prompt_and_response_payload(self) -> None:
        raw = {
            "direction": "outbound",
            "message": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "turn/start",
                "params": {"threadId": "thread-1", "input": [{"text": "private prompt"}]},
            },
        }
        safe = staging._safe_event(raw)
        encoded = json.dumps(safe)
        self.assertNotIn("private prompt", encoded)
        self.assertNotIn("thread-1", encoded)
        self.assertEqual(safe["message"]["params"]["input_count"], 1)

    def test_case_local_fake_codex_turn_records_owner_correlation_without_raw_key(self) -> None:
        secret = b"sk-test-secret"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex = self._fake_codex(root)
            output = root / "case"
            summary = staging.run_staging(
                output,
                codex,
                region="cn-beijing",
                project_fingerprint="a" * 64,
                key=secret,
                timeout=5,
            )
            self.assertEqual(summary["outcome"], "http_and_codex_success")
            self.assertEqual(summary["compatibility_status"], "verified-for-authorized-read-only-codex-staging")
            self.assertEqual(summary["request_count"], 1)
            self.assertEqual(summary["owner_correlation"]["thread_id"], "thread-real-staging")
            self.assertEqual(summary["owner_correlation"]["turn_id"], "turn-real-staging")
            self.assertTrue(summary["semantic"]["fixture_exact"])
            self.assertEqual(summary["safety"]["effect_count"], 0)
            self.assertFalse(summary["safety"]["raw_credential_persisted"])
            self.assertTrue(summary["safety"]["ephemeral_runtime_home_cleaned"])
            self.assertFalse((output / "codex-home").exists())
            for path in output.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret, path.read_bytes())
            event_log = output / "events" / "codex-redacted.jsonl"
            self.assertNotIn(staging.FIXTURE_PROMPT, event_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
