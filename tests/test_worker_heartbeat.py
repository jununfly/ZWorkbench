from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import unittest

from zworkbench import CompositionOwner, ComponentIdentity, ProviderIdentity, WorkerBridge, WorkerBridgeError
from zworkbench.worker_heartbeat import (
    WORKER_ERROR_CODES,
    WORKER_EVENT_KINDS,
    HeartbeatMonitor,
    heartbeat_lost,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_handshake" / "v1" / "worker_fixture.py"
BRIDGE_SOURCE = REPO_ROOT / "src" / "zworkbench" / "worker_bridge.py"


def digest(label: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


class HeartbeatLostTests(unittest.TestCase):
    def test_lost_when_silent(self):
        self.assertTrue(heartbeat_lost(now=100.0, last_activity_ts=0.0, timeout=90.0))

    def test_not_lost_within_timeout(self):
        self.assertFalse(heartbeat_lost(now=50.0, last_activity_ts=0.0, timeout=90.0))

    def test_boundary_is_exclusive(self):
        self.assertFalse(heartbeat_lost(now=90.0, last_activity_ts=0.0, timeout=90.0))
        self.assertTrue(heartbeat_lost(now=90.0001, last_activity_ts=0.0, timeout=90.0))

    def test_negative_timeout_fails_closed(self):
        with self.assertRaises(ValueError):
            heartbeat_lost(1.0, 0.0, 0.0)


class HeartbeatMonitorTests(unittest.TestCase):
    def test_fires_once_when_activity_stale(self):
        clock = [0.0]
        state = {"last": 0.0}
        lost_at: list[float] = []
        monitor = HeartbeatMonitor(
            interval=0.01,
            timeout=0.5,
            get_last_activity=lambda: state["last"],
            on_lost=lambda t: lost_at.append(t),
            on_tick=lambda t: None,
            clock=lambda: clock[0],
        )
        monitor.start()
        clock[0] = 1.0  # now 1.0, last 0.0 -> lost
        monitor._thread.join(timeout=2.0)
        self.assertTrue(monitor.lost)
        self.assertEqual(len(lost_at), 1)

    def test_no_fire_when_activity_kept_fresh(self):
        clock = [0.0]
        state = {"last": 0.0}
        lost: list[float] = []
        monitor = HeartbeatMonitor(
            interval=0.01,
            timeout=0.5,
            get_last_activity=lambda: state["last"],
            on_lost=lambda t: lost.append(t),
            on_tick=lambda t: None,
            clock=lambda: clock[0],
        )
        monitor.start()
        for _ in range(20):
            clock[0] += 0.01
            state["last"] = clock[0]  # bump activity every tick
            time.sleep(0.005)
        monitor.stop()
        self.assertFalse(monitor.lost)
        self.assertEqual(len(lost), 0)
        self.assertGreater(monitor.tick_count, 0)

    def test_stop_is_idempotent(self):
        monitor = HeartbeatMonitor(
            interval=0.01,
            timeout=10.0,
            get_last_activity=lambda: 0.0,
            on_lost=lambda t: None,
        )
        monitor.start()
        monitor.stop()
        monitor.stop()  # second call must not raise


class WorkerVocabularyConsistencyTests(unittest.TestCase):
    """ADR 0009 spirit: a single vocabulary, enforced by test."""

    def _source(self) -> str:
        return BRIDGE_SOURCE.read_text(encoding="utf-8")

    def test_every_error_code_literal_is_in_vocabulary(self):
        src = self._source()
        used = set(re.findall(r'code="([a-z_]+)"', src))
        missing = used - WORKER_ERROR_CODES
        self.assertEqual(missing, set(), f"error codes not in WORKER_ERROR_CODES: {sorted(missing)}")

    def test_every_recorded_event_kind_is_in_vocabulary(self):
        src = self._source()
        kinds = set(re.findall(r'record_(?:event|result)\(\s*\w+\s*,\s*"([^"]+)"', src, re.DOTALL))
        missing = kinds - WORKER_EVENT_KINDS
        self.assertEqual(missing, set(), f"event kinds not in WORKER_EVENT_KINDS: {sorted(missing)}")

    def test_heartbeat_lost_is_a_known_error_code(self):
        self.assertIn("heartbeat_lost", WORKER_ERROR_CODES)

    def test_heartbeat_lost_event_kind_is_registered(self):
        self.assertIn("worker.heartbeat.lost", WORKER_EVENT_KINDS)


class BridgeHeartbeatIntegrationTests(unittest.TestCase):
    """ADR 0012 test path: a real subprocess that is alive but silent must be
    declared lost, safe-stopped, and reaped via the existing killpg reaper."""

    def _case(self, *, heartbeat_interval=0.05, heartbeat_timeout=0.15):
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
            worker_args=(str(FIXTURE), "--scenario", "success"),
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
            heartbeat_interval=heartbeat_interval,
            heartbeat_timeout=heartbeat_timeout,
        )
        return temporary, case_root, owner, bridge

    def setUp(self):
        self.temporary, self.case_root, self.owner, self.bridge = self._case()

    def tearDown(self):
        try:
            self.bridge.close()
        except Exception:
            pass
        try:
            self.owner.close()
        except Exception:
            pass
        self.temporary.cleanup()

    def test_silent_subprocess_is_declared_lost_and_reaped(self):
        self.owner.create_run("child-hb", "worker.handshake", {"operation": "handshake"})
        self.owner.start_run("child-hb")
        # A process that stays alive but emits nothing on stdout/stderr.
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            self.bridge.process = proc
            self.bridge._last_activity_ts = 0.0  # ancient: must be declared lost
            self.bridge._heartbeat_lost = False
            self.bridge._start_heartbeat("parent-1", "child-hb")

            deadline = time.monotonic() + 2.0
            while not self.bridge._heartbeat_lost and time.monotonic() < deadline:
                time.sleep(0.02)

            self.assertTrue(self.bridge._heartbeat_lost, "monitor must declare heartbeat lost")
            self.assertEqual(self.bridge._termination_code, "heartbeat_lost")
            # The existing reaper (killpg) must have reaped the silent process.
            self.assertIsNotNone(proc.poll(), "silent worker must be killed by reaper")

            # Mirror the run()/read_only_coding() finally + except chain that a
            # real heartbeat loss travels: reap, record exit, then fail-closed
            # safe-stop.  heartbeat_lost is deliberately NOT in the recoverable
            # set, so the verdict is safe_stopped (never uncertain/retryable).
            self.bridge._active_command = tuple(proc.args)
            self.bridge._stop_heartbeat()
            self.bridge._stop_process()
            self.bridge._record_exit("child-hb")
            self.bridge._record_failure(
                "parent-1",
                "child-hb",
                WorkerBridgeError("Worker heartbeat lost", code="heartbeat_lost"),
            )
            self.assertEqual(self.owner.get_run("child-hb")["status"], "safe_stopped")
        finally:
            self.bridge._stop_heartbeat()
            if proc.poll() is None:
                proc.kill()

    def test_normal_handshake_flow_is_unaffected_by_monitor(self):
        # The default 30s/90s monitor must never fire during a fast fixture run;
        # this guards against the heartbeat wiring regressing the happy path.
        result = self.bridge.handshake(
            "parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            timeout=5.0,
        )
        self.assertEqual(result.status, "handshake_complete")
        self.assertFalse(self.bridge._heartbeat_lost)
        self.assertIsNone(self.bridge._heartbeat)
