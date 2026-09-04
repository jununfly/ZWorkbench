from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from zworkbench import ComponentIdentity, CompositionOwner, ProviderIdentity, UNKNOWN
from zworkbench.replay import (
    CassetteIdentity,
    OwnerBackedReplayService,
    ReplayIdentity,
)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class OwnerBackedReplayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.owner = CompositionOwner(self.root / "state" / "composition.sqlite3")
        self.owner.create_run("source-run", "replay-fixture", {"prompt": "fixture"})
        self.owner.start_run("source-run")
        self.owner.record_event("source-run", "fixture.started", {"source": "h5"})
        self.owner.complete_run("source-run", {"answer": "fixture-ok"})
        self.service = OwnerBackedReplayService(self.owner)

        self.provider = ProviderIdentity(
            provider="fake-loopback",
            model="fake-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        )
        self.base_identity = ReplayIdentity(
            harness_identity=ComponentIdentity("dsh", "fixture-v1", "sha256:dsh", "fixture"),
            plugin_identities=(),
            worker_identity=ComponentIdentity("codex-worker", "fixture-v1", "sha256:worker", "fixture"),
            provider_identity=self.provider,
            tool_schema_digest="sha256:tools",
            policy_digest="sha256:policy",
            workspace_digest="sha256:workspace",
            environment_digest="sha256:environment",
            owner_schema="zworkbench-composition-owner/v1",
            source_event_digest=self.service.owner_event_digest("source-run"),
            cassette_identity=None,
        )

    def tearDown(self) -> None:
        self.owner.close()
        self.temporary.cleanup()

    def _cassette(self) -> tuple[Path, ReplayIdentity]:
        path = self.root / "cassette.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "zworkbench.replay-cassette/v1",
                    "sealed": True,
                    "cassette_id": "cassette-1",
                    "source_run_id": "source-run",
                    "source_event_digest": self.base_identity.source_event_digest,
                    "environment_digest": self.base_identity.environment_digest,
                    "provider_identity": self.provider.to_dict(),
                    "interactions": [{"request": {"prompt": "fixture"}, "response": {"answer": "fixture-ok"}}],
                    "tool_results": [],
                    "expected_semantic_result": {"answer": "fixture-ok"},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path, replace(
            self.base_identity,
            cassette_identity=CassetteIdentity("cassette-1", sha256_file(path)),
        )

    def test_recorded_view_reads_owner_facts_without_mutating_owner(self) -> None:
        before = self.owner.state_digest()

        result = self.service.recorded_view("source-run", self.base_identity, "view-1")

        self.assertEqual(result["status"], "viewed")
        self.assertTrue(result["view_only"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual(result["semantic_result"], {"answer": "fixture-ok"})
        self.assertEqual(result["provenance"]["owner_schema"], "zworkbench-composition-owner/v1")
        self.assertEqual(self.owner.state_digest(), before)

    def test_simulated_replay_is_cassette_only_and_does_not_mutate_owner(self) -> None:
        cassette, identity = self._cassette()
        before = self.owner.state_digest()

        result = self.service.simulated_replay(cassette, identity, "simulation-1")

        self.assertEqual(result["status"], "simulated")
        self.assertTrue(result["cassette_only"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual(result["provider_requests"], 0)
        self.assertEqual(result["tool_invocations"], 0)
        self.assertEqual(result["semantic_result"], {"answer": "fixture-ok"})
        self.assertEqual(self.owner.state_digest(), before)

    def test_live_replay_is_explicitly_denied_without_external_execution(self) -> None:
        cassette, identity = self._cassette()
        before = self.owner.state_digest()

        result = self.service.live_replay(cassette, identity, "live-1")

        self.assertEqual(result["status"], "denied")
        self.assertTrue(result["safe_denial"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual(result["policy_decision"]["decision"], "deny")
        self.assertEqual(result["policy_decision"]["reason"], "live_replay_disabled_by_default")
        self.assertEqual(self.owner.state_digest(), before)

    def test_missing_identity_is_unknown_and_safe_stopped(self) -> None:
        cassette, identity = self._cassette()
        incomplete = replace(identity, policy_digest=UNKNOWN, worker_identity=replace(identity.worker_identity, digest=UNKNOWN))

        result = self.service.simulated_replay(cassette, incomplete, "missing-identity")

        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["safe_stop"])
        self.assertIn("policy_digest", result["missing_identity"])
        self.assertIn("worker_identity.digest", result["missing_identity"])
        self.assertEqual(result["execution_performed"], False)

    def test_missing_or_tampered_cassette_is_unknown_and_safe_stopped(self) -> None:
        cassette, identity = self._cassette()
        missing = self.service.simulated_replay(self.root / "missing.json", identity, "missing-cassette")
        self.assertEqual(missing["status"], "unknown")
        self.assertTrue(missing["safe_stop"])
        self.assertIn("cassette_missing", missing["reason"])

        cassette.write_text(cassette.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        tampered = self.service.simulated_replay(cassette, identity, "tampered-cassette")
        self.assertEqual(tampered["status"], "unknown")
        self.assertTrue(tampered["safe_stop"])
        self.assertEqual(tampered["reason"], "cassette_digest_mismatch")

    def test_recorded_view_digest_mismatch_is_not_presented_as_success(self) -> None:
        identity = replace(self.base_identity, source_event_digest="sha256:wrong")

        result = self.service.recorded_view("source-run", identity, "wrong-source")

        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["safe_stop"])
        self.assertEqual(result["reason"], "source_event_digest_mismatch")

    def test_simulated_replay_requires_an_existing_owner_source_run(self) -> None:
        cassette, identity = self._cassette()
        cassette_data = json.loads(cassette.read_text(encoding="utf-8"))
        cassette_data["source_run_id"] = "missing-source-run"
        cassette.write_text(json.dumps(cassette_data, sort_keys=True) + "\n", encoding="utf-8")
        identity = replace(identity, cassette_identity=CassetteIdentity("cassette-1", sha256_file(cassette)))

        result = self.service.simulated_replay(cassette, identity, "missing-source-run")

        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["safe_stop"])
        self.assertEqual(result["reason"], "owner_source_run_missing")


if __name__ == "__main__":
    unittest.main()
