from __future__ import annotations

import hashlib
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
import unittest

from zworkbench import (
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_lifecycle" / "v1" / "worker_fixture.py"


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


class WorkerLifecycleTests(unittest.TestCase):
    def _case(self, scenario: str, *, recovery_mode: bool = False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        (case_root / "workspace").mkdir(parents=True)
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        owner.create_run("parent-1", "dsh.bootstrap", {"operation": "worker-lifecycle"})
        owner.start_run("parent-1")
        bridge = WorkerBridge(
            owner,
            sys.executable,
            case_root,
            worker_args=(str(FIXTURE), "--scenario", scenario),
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
        return temporary, case_root, owner, bridge

    def tearDown(self) -> None:
        bridge = getattr(self, "bridge", None)
        owner = getattr(self, "owner", None)
        temporary = getattr(self, "temporary", None)
        if bridge is not None:
            bridge.close()
        if owner is not None:
            owner.close()
        if temporary is not None:
            temporary.cleanup()

    def _start(self, scenario: str, *, recovery_mode: bool = False, timeout: float = 5.0):
        self.temporary, self.case_root, self.owner, self.bridge = self._case(
            scenario, recovery_mode=recovery_mode
        )
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                outcome["result"] = self.bridge.handshake(
                    "parent-1",
                    child_run_id="child-1",
                    attempt_id="attempt-1",
                    dsh_session_id="dsh-session-1",
                    dsh_turn_id="dsh-turn-1",
                    timeout=timeout,
                )
            except WorkerBridgeError as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        return thread, outcome

    def _wait_for_process(self) -> None:
        deadline = time.monotonic() + 2.0
        while self.bridge.process is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(self.bridge.process)

    def _wait_for_file(self, path: Path) -> None:
        deadline = time.monotonic() + 2.0
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), f"fixture did not create {path}")

    def _exit_receipt(self, run_id: str = "child-1") -> dict:
        run = self.owner.get_run(run_id)
        matches = [item["value"] for item in run["results"] if item["kind"] == "worker.exit"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_timeout_terminates_process_group_and_records_receipt(self) -> None:
        thread, outcome = self._start("hang", timeout=0.25)
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_timeout")
        receipt = self._exit_receipt()
        self.assertEqual(receipt["termination_reason"], "timeout")
        self.assertTrue(receipt["process_group_clean"])
        self.assertEqual(receipt["orphan_processes"], 0)
        self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")
        self.assertIsNone(self.bridge.process)

    def test_cancel_is_observable_and_safe_stops_both_runs(self) -> None:
        thread, outcome = self._start("hang")
        self._wait_for_process()
        control = self.bridge.cancel("parent-1")
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(control["requested"])
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_cancelled")
        receipt = self._exit_receipt()
        self.assertEqual(receipt["termination_reason"], "cancelled")
        self.assertTrue(receipt["process_group_clean"])
        self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")

    def test_parent_stop_uses_distinct_lifecycle_reason(self) -> None:
        thread, outcome = self._start("hang")
        self._wait_for_process()
        control = self.bridge.stop_parent("parent-1")
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(control["requested"])
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_parent_stopped")
        receipt = self._exit_receipt()
        self.assertEqual(receipt["termination_reason"], "parent_stop")
        self.assertTrue(receipt["process_group_clean"])
        self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")

    def test_descendant_is_killed_with_worker_process_group(self) -> None:
        thread, outcome = self._start("spawn-descendant")
        pid_file = self.case_root / "workspace" / "descendant.pid"
        self._wait_for_file(pid_file)
        descendant_pid = int(pid_file.read_text(encoding="utf-8"))
        self.bridge.stop_parent("parent-1")
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_parent_stopped")
        receipt = self._exit_receipt()
        self.assertTrue(receipt["process_group_clean"])
        self.assertTrue(receipt["orphan_processes"] == 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(descendant_pid, 0)

    def test_child_crash_records_exit_without_semantic_success(self) -> None:
        thread, outcome = self._start("crash")
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_exit_nonzero")
        receipt = self._exit_receipt()
        self.assertEqual(receipt["exit_code"], 23)
        self.assertEqual(receipt["termination_reason"], "child_crash")
        self.assertTrue(receipt["process_group_clean"])
        self.assertNotIn("semantic", {item["kind"] for item in self.owner.get_run("child-1")["results"]})

    def test_recovery_creates_new_attempt_and_preserves_failed_attempt(self) -> None:
        thread, outcome = self._start("crash-once", recovery_mode=True)
        thread.join(timeout=4.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(getattr(outcome["error"], "code", None), "worker_exit_nonzero")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "recovering")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")

        result = self.bridge.recover_handshake(
            "parent-1",
            recovery_of_child_run_id="child-1",
            child_run_id="child-2",
            attempt_id="attempt-2",
            dsh_session_id="dsh-session-2",
            dsh_turn_id="dsh-turn-2",
            timeout=2.0,
        )
        self.assertEqual(result.status, "handshake_complete")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "running")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")
        child = self.owner.get_run("child-2")
        self.assertEqual(child["status"], "completed")
        self.assertEqual(child["metadata"]["recovery_of_child_run_id"], "child-1")
        self.assertEqual(child["metadata"]["attempt_id"], "attempt-2")
        self.assertEqual(self._exit_receipt("child-2")["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
