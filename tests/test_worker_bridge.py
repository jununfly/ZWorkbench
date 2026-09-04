from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from zworkbench import (
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_handshake" / "v1" / "worker_fixture.py"


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


class WorkerBridgeTests(unittest.TestCase):
    def _case(self, scenario: str = "success"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        owner.create_run("parent-1", "dsh.bootstrap", {"operation": "bootstrap"})
        owner.start_run("parent-1")
        bridge = WorkerBridge(
            owner,
            sys.executable,
            case_root,
            worker_args=(str(FIXTURE), "--scenario", scenario),
            worker_artifact_identity=ComponentIdentity(
                name="codex-worker-fixture",
                version="1.0.0",
                digest=digest("worker-artifact"),
                source="pinned-fixture",
            ),
            worker_schema_identity=ComponentIdentity(
                name="codex-app-server-fixture",
                version="v1",
                digest=digest("worker-schema"),
                source="pinned-fixture-schema",
            ),
            provider_identity=ProviderIdentity(
                provider="fake-loopback",
                model="fixture-model",
                endpoint="http://127.0.0.1:11434",
                transport="loopback-only",
            ),
            policy_digest=digest("policy"),
            environment_digest=digest("environment"),
            workspace_digest=digest("workspace"),
        )
        return temporary, case_root, owner, bridge

    def _close_case(self) -> None:
        bridge = getattr(self, "bridge", None)
        owner = getattr(self, "owner", None)
        temporary = getattr(self, "temporary", None)
        if bridge is not None:
            bridge.close()
        if owner is not None:
            owner.close()
        if temporary is not None:
            temporary.cleanup()
        for name in ("bridge", "owner", "temporary"):
            if hasattr(self, name):
                delattr(self, name)

    def tearDown(self) -> None:
        self._close_case()

    def _run(self, scenario: str = "success"):
        self._close_case()
        self.temporary, self.case_root, self.owner, self.bridge = self._case(scenario)
        return self.bridge.handshake(
            "parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            timeout=1.0,
        )

    def test_handshake_binds_complete_identity_and_keeps_parent_open(self) -> None:
        result = self._run()

        self.assertEqual(result.status, "handshake_complete")
        self.assertTrue(result.identity.is_complete())
        self.assertEqual(result.identity.parent_run_id, "parent-1")
        self.assertEqual(result.identity.child_run_id, "child-1")
        self.assertEqual(result.identity.dsh_session_id, "dsh-session-1")
        self.assertEqual(result.identity.codex_thread_id, "codex-thread-1")
        self.assertEqual(result.identity.codex_turn_id, "codex-turn-1")
        self.assertEqual(self.bridge.process, None)

        parent = self.owner.get_run("parent-1")
        child = self.owner.get_run("child-1")
        self.assertEqual(parent["status"], "running")
        self.assertEqual(child["status"], "completed")
        self.assertEqual(child["metadata"]["parent_run_id"], "parent-1")
        self.assertEqual(child["metadata"]["attempt_id"], "attempt-1")
        self.assertIn("worker.handshake", {item["kind"] for item in child["results"]})
        self.assertIn("worker.exit", {item["kind"] for item in child["results"]})
        self.assertEqual(parent["effects"], [])
        self.assertEqual(child["effects"], [])

    def test_unknown_identity_safe_stops_both_runs_without_semantic_success(self) -> None:
        with self.assertRaises(WorkerBridgeError) as raised:
            self._run("unknown")

        self.assertEqual(raised.exception.code, "handshake_identity_incomplete")
        parent = self.owner.get_run("parent-1")
        child = self.owner.get_run("child-1")
        self.assertEqual(parent["status"], "safe_stopped")
        self.assertEqual(child["status"], "safe_stopped")
        self.assertNotIn("semantic", {item["kind"] for item in child["results"]})
        self.assertIsNotNone([item for item in child["results"] if item["kind"] == "worker.exit"])

    def test_schema_mismatch_and_nonzero_exit_fail_closed(self) -> None:
        for scenario, expected_code in (("mismatch", "handshake_schema_unknown"), ("nonzero", "worker_exit_nonzero")):
            with self.subTest(scenario=scenario):
                with self.assertRaises(WorkerBridgeError) as raised:
                    self._run(scenario)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
                self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")

    def test_identity_provenance_and_unknown_wire_fail_closed(self) -> None:
        scenarios = (
            ("identity-mismatch", "handshake_identity_mismatch"),
            ("provenance-mismatch", "handshake_provenance_mismatch"),
            ("unknown-message", "handshake_message_unknown"),
            ("unknown-field", "handshake_field_unknown"),
            ("crash", "handshake_response_missing"),
        )
        for scenario, expected_code in scenarios:
            with self.subTest(scenario=scenario):
                with self.assertRaises(WorkerBridgeError) as raised:
                    self._run(scenario)
                self.assertEqual(raised.exception.code, expected_code)
                parent = self.owner.get_run("parent-1")
                child = self.owner.get_run("child-1")
                self.assertEqual(parent["status"], "safe_stopped")
                self.assertEqual(child["status"], "safe_stopped")
                self.assertIn("worker.error", {item["kind"] for item in child["results"]})
                self.assertIn("worker.exit", {item["kind"] for item in child["results"]})
                self.assertNotIn("semantic", {item["kind"] for item in child["results"]})
                self.assertIsNone(self.bridge.process)

    def test_unknown_wire_and_timeout_leave_no_live_bridge_process(self) -> None:
        for scenario, expected_code in (("malformed", "handshake_invalid_json"), ("hang", "worker_timeout")):
            with self.subTest(scenario=scenario):
                with self.assertRaises(WorkerBridgeError) as raised:
                    self._run(scenario)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertIsNone(self.bridge.process)
                self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")


if __name__ == "__main__":
    unittest.main()
