from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from zworkbench import (
    CompositionOwner,
    WorkerBridge,
    WorkerBridgeError,
)
from zworkbench.worker_contract import (
    ComponentIdentity,
    IdentityChain,
    ProviderIdentity,
)
from zworkbench.worker_bridge import FailStopError


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_lifecycle" / "v1" / "worker_fixture.py"


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FailStopContractTests(unittest.TestCase):
    def _build(self, *, recovery_mode: bool = False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        owner.create_run("parent-1", "dsh.bootstrap", {"operation": "fail-stop"})
        owner.start_run("parent-1")
        owner.create_run(
            "child-1",
            "worker.read_only_coding",
            {"operation": "read_only_coding"},
            {"parent_run_id": "parent-1"},
        )
        owner.start_run("child-1")
        bridge = WorkerBridge(
            owner,
            sys.executable,
            case_root,
            worker_args=(str(FIXTURE), "--scenario", "success"),
            worker_artifact_identity=ComponentIdentity(
                name="codex-worker-lifecycle-fixture",
                version="1.0.0",
                digest=digest("lifecycle-worker-artifact"),
                source="pinned-fixture",
            ),
            worker_schema_identity=ComponentIdentity(
                name="codex-app-server-fixture",
                version="v1",
                digest=digest("lifecycle-worker-schema"),
                source="pinned-fixture-schema",
            ),
            provider_identity=ProviderIdentity(
                provider="fake-loopback",
                model="fixture-model",
                endpoint="http://127.0.0.1:11434",
                transport="loopback-only",
            ),
            policy_digest=digest("lifecycle-policy"),
            environment_digest=digest("lifecycle-environment"),
            workspace_digest=digest("lifecycle-workspace"),
            recovery_mode=recovery_mode,
        )
        return temporary, owner, bridge

    def tearDown(self) -> None:
        for attr in ("bridge", "owner"):
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, "close"):
                obj.close()
        temporary = getattr(self, "temporary", None)
        if temporary is not None:
            temporary.cleanup()

    # --- assert_clean_termination: the single fail-stop chokepoint ---
    def test_assert_clean_termination_passes_when_clean(self) -> None:
        _, owner, bridge = self._build()
        bridge._process_group_clean = True
        bridge.assert_clean_termination()  # must not raise

    def test_assert_clean_termination_fails_when_dirty(self) -> None:
        _, owner, bridge = self._build()
        bridge._process_group_clean = False
        with self.assertRaises(FailStopError):
            bridge.assert_clean_termination()

    def test_assert_clean_termination_fails_when_unknown(self) -> None:
        _, owner, bridge = self._build()
        bridge._process_group_clean = None
        with self.assertRaises(FailStopError):
            bridge.assert_clean_termination()

    # --- failure-terminal boundary: proven-dirty / unverifiable -> fail-stop ---
    def test_record_failure_fail_stops_when_cleanup_unverified(self) -> None:
        _, owner, bridge = self._build()
        bridge._process_group_clean = False
        bridge._last_exit_receipt = {"process_group_clean": False, "orphan_processes": None}
        error = WorkerBridgeError("boom", code="worker_exit_nonzero")
        with self.assertRaises(FailStopError):
            bridge._record_failure("parent-1", "child-1", error)
        # The run is forced to failed; it is never silently safe-stopped.
        self.assertEqual(owner.get_run("parent-1")["status"], "failed")
        self.assertEqual(owner.get_run("child-1")["status"], "failed")

    def test_record_failure_safe_stops_when_cleanup_verified(self) -> None:
        _, owner, bridge = self._build()
        bridge._process_group_clean = True
        bridge._last_exit_receipt = {"process_group_clean": True, "orphan_processes": 0}
        error = WorkerBridgeError("boom", code="worker_exit_nonzero")
        # Verified cleanup: no fail-stop; the run is safe-stopped.
        bridge._record_failure("parent-1", "child-1", error)
        self.assertEqual(owner.get_run("parent-1")["status"], "safe_stopped")
        self.assertEqual(owner.get_run("child-1")["status"], "safe_stopped")

    # --- success-terminal boundary: a clean result is impossible when unverified ---
    def _craft_valid_coding(self, bridge: WorkerBridge):
        identity_chain = IdentityChain(
            parent_run_id="parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            worker_run_id="child-1",
            codex_thread_id="thread-1",
            codex_turn_id="turn-1",
            event_id="event-1",
            artifact_id="artifact-1",
        )
        provider_identity = ProviderIdentity(
            provider="fake-loopback",
            model="fixture-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        )
        artifact_identity = ComponentIdentity(
            name="codex-worker-lifecycle-fixture",
            version="1.0.0",
            digest=digest("lifecycle-worker-artifact"),
            source="pinned-fixture",
        )
        schema_identity = ComponentIdentity(
            name="codex-app-server-fixture",
            version="v1",
            digest=digest("lifecycle-worker-schema"),
            source="pinned-fixture-schema",
        )
        request = SimpleNamespace(
            provider_identity=provider_identity,
            worker_artifact_identity=artifact_identity,
            worker_schema_identity=schema_identity,
            replay_mode="normal",
            policy_digest=digest("lifecycle-policy"),
            environment_digest=digest("lifecycle-environment"),
            workspace_digest=digest("lifecycle-workspace"),
        )
        handshake = SimpleNamespace(identity=identity_chain)
        artifact_root = bridge.case_root / "artifacts"
        artifact_root.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, dict[str, object]] = {}
        for name in ("diff", "tests", "semantic", "runtime_events"):
            content = name.encode("utf-8")
            path = artifact_root / name
            path.write_bytes(content)
            artifacts[name] = {
                "path": name,
                "digest": _sha256_bytes(content),
                "bytes": len(content),
            }
        response = SimpleNamespace(
            message_type="result",
            identity=identity_chain,
            provider_identity=provider_identity,
            worker_artifact_identity=artifact_identity,
            worker_schema_identity=schema_identity,
            replay_mode="normal",
            policy_digest=digest("lifecycle-policy"),
            environment_digest=digest("lifecycle-environment"),
            workspace_digest=digest("lifecycle-workspace"),
            payload={
                "status": "completed",
                "operation": "read_only_coding",
                "semantic_result": {"answer": "ok"},
                "artifacts": artifacts,
            },
        )
        return response, request, handshake, artifact_root

    def test_validate_coding_result_fail_stops_when_cleanup_unverified(self) -> None:
        _, owner, bridge = self._build()
        # Cleanup was not provably clean: the success path must fail-stop
        # before the caller can complete_run the parent Run.
        bridge._process_group_clean = False
        response, request, handshake, artifact_root = self._craft_valid_coding(bridge)
        with self.assertRaises(FailStopError):
            bridge._validate_coding_result(response, request, handshake, artifact_root)

    def test_validate_coding_result_allows_completed_when_clean(self) -> None:
        _, owner, bridge = self._build()
        # Provably clean: the guard passes and a completed result is produced.
        bridge._process_group_clean = True
        response, request, handshake, artifact_root = self._craft_valid_coding(bridge)
        result = bridge._validate_coding_result(response, request, handshake, artifact_root)
        self.assertEqual(result.status, "completed")


if __name__ == "__main__":
    unittest.main()
