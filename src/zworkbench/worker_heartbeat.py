"""Worker long-connection liveness (heartbeat) supervision — ADR 0012.

Supervisor-side observation only.  No Worker protocol change (no ping/pong):
a background :class:`HeartbeatMonitor` thread advances the pure function
:func:`heartbeat_lost` against a shared ``last_activity_ts`` that the bridge
updates on every stdout byte read and at each process spawn.  On loss the
bridge safe-stops the child run and reuses the existing reaper
(``WorkerBridge._signal_process`` → ``os.killpg``); it does NOT invent a new
kill path.

The single vocabulary of Worker event kinds and error codes lives here
(ADR 0009 spirit) so every code used by ``worker_bridge`` is auditable
against one source of truth.  ``tests/test_worker_heartbeat.py`` fails if any
``WorkerBridgeError``/``FailStopError`` ``code=`` literal or owner event kind
escapes :data:`WORKER_ERROR_CODES` / :data:`WORKER_EVENT_KINDS`.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

# ADR 0012 §②: interval = 30s, timeout = 3×interval = 90s.  A silent worker is
# declared lost only after three full quiet intervals, well past any single
# request deadline (default 45s), so the heartbeat never races the per-request
# `worker_timeout`.
WORKER_HEARTBEAT_INTERVAL_SEC = 30.0
WORKER_HEARTBEAT_TIMEOUT_SEC = 90.0

# Every owner-persisted Worker event kind.  The three `heartbeat.*` kinds are
# registered here as the SSOT; only `worker.heartbeat.lost` is emitted to the
# ledger (a 30s `tick` cadence would otherwise spam the owner journal, and a
# fail-closed-on-first-loss policy leaves no `recovered` state to record).
WORKER_EVENT_KINDS = frozenset(
    {
        "worker.handshake.request",
        "worker.handshake",
        "worker.handshake.completed",
        "worker.coding.request",
        "worker.coding",
        "worker.coding.completed",
        "worker.error",
        "worker.exit",
        "worker.real_mode.gated",
        "worker.handshake.requested",
        "worker.coding.requested",
        "worker.recovery.requested",
        "worker.stop",
        "worker.stop.requested",
        "worker.heartbeat.tick",
        "worker.heartbeat.lost",
        "worker.heartbeat.recovered",
    }
)

# Single vocabulary of WorkerBridge error codes.  Mirrors every `code=` literal
# in `worker_bridge.py` plus the dynamically composed
# `handshake_{schema,message,field,shape}_*` codes and the new `heartbeat_lost`.
# A test enforces that no `code=` literal escapes this set.
WORKER_ERROR_CODES = frozenset(
    {
        "artifact_root_missing",
        "artifact_root_not_empty",
        "artifact_root_outside_case",
        "artifact_root_workspace_overlap",
        "case_root_missing",
        "codex_identity_fabricated",
        "coding_artifact_bytes_invalid",
        "coding_artifact_digest_invalid",
        "coding_artifact_digest_mismatch",
        "coding_artifact_invalid",
        "coding_artifact_path_invalid",
        "coding_artifact_set_mismatch",
        "coding_artifact_unknown",
        "coding_artifacts_incomplete",
        "coding_extra_message",
        "coding_empty_line",
        "coding_identity_incomplete",
        "coding_identity_mismatch",
        "coding_incomplete_jsonl",
        "coding_message_invalid",
        "coding_message_too_large",
        "coding_payload_invalid",
        "coding_payload_unknown",
        "coding_provenance_mismatch",
        "coding_response_missing",
        "coding_status_invalid",
        "coding_workspace_changed",
        "handshake_empty_line",
        "handshake_extra_message",
        "handshake_field_unknown",
        "handshake_identity_incomplete",
        "handshake_identity_mismatch",
        "handshake_incomplete_jsonl",
        "handshake_invalid_json",
        "handshake_message_invalid",
        "handshake_message_too_large",
        "handshake_message_unknown",
        "handshake_provenance_mismatch",
        "handshake_response_missing",
        "handshake_schema_unknown",
        "handshake_shape_incomplete",
        "handshake_status_invalid",
        "orphan_cleanup_failed",
        "parent_not_running",
        "process_group_cleanup_failed",
        "prompt_credential_forbidden",
        "real_mode_replay_conflict",
        "recovery_not_available",
        "recovery_source_invalid",
        "replay_mode_not_normal",
        "worker_bridge_busy",
        "worker_bridge_failure",
        "worker_cancelled",
        "worker_cleanup_unverified",
        "worker_exit_nonzero",
        "worker_exit_timeout",
        "worker_executable_digest_mismatch",
        "worker_not_active",
        "worker_output_credential_forbidden",
        "worker_parent_stopped",
        "worker_process_missing",
        "worker_request_failed",
        "worker_start_failed",
        "worker_stderr_credential_forbidden",
        "worker_stream_missing",
        "worker_stderr_too_large",
        "worker_timeout",
        "workspace_missing",
        "heartbeat_lost",
        "host_sandbox_absent",
    }
)


def heartbeat_lost(now: float, last_activity_ts: float, timeout: float) -> bool:
    """Pure liveness check: ``True`` iff silent longer than ``timeout``.

    ``now`` and ``last_activity_ts`` share a monotonic clock.  A non-positive
    ``timeout`` is a programming error and fails closed (raises).
    """

    if timeout <= 0:
        raise ValueError("heartbeat timeout must be positive")
    return (now - last_activity_ts) > timeout


class HeartbeatMonitor:
    """Background liveness watcher for one Worker subprocess lifetime.

    The bridge owns ``last_activity_ts`` (updated on stdout bytes and at
    spawn).  The monitor polls every ``interval``; on each tick it may invoke
    ``on_tick`` (internal bookkeeping, not the owner ledger) and, if
    :func:`heartbeat_lost` becomes true, invokes ``on_lost`` exactly once and
    stops.  ``stop()`` is idempotent and safe to call from any thread.
    """

    def __init__(
        self,
        *,
        interval: float,
        timeout: float,
        get_last_activity: Callable[[], float],
        on_lost: Callable[[float], None],
        on_tick: Optional[Callable[[float], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        name: str = "worker-heartbeat",
    ) -> None:
        if interval <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._interval = float(interval)
        self._timeout = float(timeout)
        self._get_last_activity = get_last_activity
        self._on_lost = on_lost
        self._on_tick = on_tick
        self._clock = clock
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self.lost = False
        self.tick_count = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self._interval + 1.0)

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            now = self._clock()
            if self._on_tick is not None:
                self._on_tick(now)
                self.tick_count += 1
            if heartbeat_lost(now, self._get_last_activity(), self._timeout):
                self.lost = True
                self._on_lost(now)
                return
