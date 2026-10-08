from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from zworkbench import (
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
)
from zworkbench.composition import RetryBudgetExhausted
from zworkbench.dsh_runtime import DshRuntimeAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_handshake" / "v1" / "worker_fixture.py"
DSH_FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_dsh_bootstrap" / "v1"


def _digest(label: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _dsh_id_from_fixture() -> str:
    manifest = json.loads((DSH_FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    profile = manifest.get("profile") or {}
    name = profile.get("name") or profile.get("id") or profile.get("profile_id")
    return f"dsh:{name}" if name else f"dsh:{DSH_FIXTURE.resolve().as_posix()}"


class CrossLayerRetryWiringTests(unittest.TestCase):
    """Node 1-5-4: real call sites in dsh_runtime / worker_bridge tally into the
    owner-owned cross-layer retry + run-restart ledgers, fail-closed on exhaustion.
    """

    # -- Worker layer --------------------------------------------------------

    def _worker_case(self, scenario: str = "success"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        owner.create_run("parent-1", "dsh.bootstrap", {"operation": "bootstrap"})
        owner.start_run("parent-1")
        bridge = WorkerBridge(
            owner,
            __import__("sys").executable,
            case_root,
            worker_args=(str(WORKER_FIXTURE), "--scenario", scenario),
            worker_artifact_identity=ComponentIdentity(
                name="codex-worker-fixture",
                version="1.0.0",
                digest=_digest("worker-artifact"),
                source="pinned-fixture",
            ),
            worker_schema_identity=ComponentIdentity(
                name="codex-app-server-fixture",
                version="v1",
                digest=_digest("worker-schema"),
                source="pinned-fixture-schema",
            ),
            provider_identity=ProviderIdentity(
                provider="fake-loopback",
                model="fixture-model",
                endpoint="http://127.0.0.1:11434",
                transport="loopback-only",
            ),
            policy_digest=_digest("policy"),
            environment_digest=_digest("environment"),
            workspace_digest=_digest("workspace"),
        )
        return temporary, case_root, owner, bridge

    def _close(self, objs):
        for obj in objs:
            if hasattr(obj, "close"):
                obj.close()
            elif isinstance(obj, tempfile.TemporaryDirectory):
                obj.cleanup()

    def test_worker_retry_tallied_on_success(self) -> None:
        temporary, _case_root, owner, bridge = self._worker_case()
        try:
            owner.declare_worker_retry_budget("codex-worker-fixture", max_retries=5, declared_by="test")
            result = bridge.handshake(
                "parent-1",
                child_run_id="child-1",
                attempt_id="attempt-1",
                dsh_session_id="dsh-session-1",
                dsh_turn_id="dsh-turn-1",
                timeout=1.0,
            )
            self.assertEqual(result.status, "handshake_complete")
            ledger = owner.worker_retry_budget_ledger_for_run("parent-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["worker_id"], "codex-worker-fixture")
            self.assertEqual(ledger[0]["bound"], "enforced")
            self.assertEqual(ledger[0]["attempt_number"], 1)
        finally:
            self._close([bridge, owner, temporary])

    def test_worker_retry_fail_closed_when_budget_exhausted(self) -> None:
        temporary, _case_root, owner, bridge = self._worker_case()
        try:
            owner.declare_worker_retry_budget("codex-worker-fixture", max_retries=0, declared_by="test")
            with self.assertRaises(RetryBudgetExhausted):
                bridge.handshake(
                    "parent-1",
                    child_run_id="child-1",
                    attempt_id="attempt-1",
                    dsh_session_id="dsh-session-1",
                    dsh_turn_id="dsh-turn-1",
                    timeout=1.0,
                )
            # fail-closed before any process spawned: parent still running, no child.
            self.assertEqual(owner.get_run("parent-1")["status"], "running")
            self.assertIsNone(bridge.process)
        finally:
            self._close([bridge, owner, temporary])

    # -- DSH layer -----------------------------------------------------------

    def _dsh_case(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        bundle = root / "runtime"
        shutil.copytree(DSH_FIXTURE, bundle)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["launch"]["args"] = ["--scenario", "success"]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        return temporary, case_root, manifest_path, owner

    def test_dsh_retry_tallied_on_success_undeclared(self) -> None:
        temporary, case_root, manifest_path, owner = self._dsh_case()
        try:
            adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
            result = adapter.execute("run-1")
            self.assertEqual(result.status, "completed")
            ledger = owner.dsh_retry_budget_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["bound"], "undeclared")
            self.assertEqual(ledger[0]["attempt_number"], 1)
        finally:
            self._close([owner, temporary])

    def test_dsh_retry_fail_closed_when_budget_exhausted(self) -> None:
        temporary, case_root, manifest_path, owner = self._dsh_case()
        try:
            dsh_id = _dsh_id_from_fixture()
            owner.declare_dsh_retry_budget(dsh_id, max_retries=0, declared_by="test")
            adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
            with self.assertRaises(RetryBudgetExhausted):
                adapter.execute("run-1")
            # fail-closed before the DSH process spawned (no subprocess), and the
            # bootstrap attempt is refused; the run row exists but stays running.
            self.assertIsNone(adapter.process)
            self.assertEqual(owner.get_run("run-1")["status"], "running")
        finally:
            self._close([owner, temporary])

    # -- Run-restart layer ---------------------------------------------------

    def test_run_restart_tallied_and_fail_closed(self) -> None:
        temporary, case_root, manifest_path, owner = self._dsh_case()
        try:
            adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
            # first execution is a normal bootstrap (no restart tally)
            self.assertEqual(adapter.execute("run-1").status, "completed")
            # budget is declared once the run exists (declare_run_restart_budget
            # requires the run row)
            owner.declare_run_restart_budget("run-1", max_restarts=0, declared_by="test")
            self.assertEqual(len(owner.run_restart_ledger_for_run("run-1")), 0)
            # second execution is a restart and is refused fail-closed
            with self.assertRaises(RetryBudgetExhausted):
                adapter.execute("run-1")
        finally:
            self._close([owner, temporary])

    def test_run_restart_allowed_within_budget(self) -> None:
        temporary, case_root, manifest_path, owner = self._dsh_case()
        try:
            adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
            self.assertEqual(adapter.execute("run-1").status, "completed")
            owner.declare_run_restart_budget("run-1", max_restarts=2, declared_by="test")
            self.assertEqual(adapter.execute("run-1").status, "completed")
            ledger = owner.run_restart_ledger_for_run("run-1")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["trigger"], "dsh_bootstrap_restart")
            self.assertEqual(ledger[0]["bound"], "enforced")
        finally:
            self._close([owner, temporary])


if __name__ == "__main__":
    unittest.main()
