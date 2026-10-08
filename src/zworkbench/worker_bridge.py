"""Owner-backed process boundary for the H2 DSH-to-Worker handshake.

The bridge owns only the transport and correlation seam.  It does not run an
Agent loop, call a Provider, execute a capability, or make Worker state a
second durable owner.  A Worker process receives one strict
``zworkbench.worker.v1`` handshake request and must return one matching
handshake response.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .provider_vocabulary import TRANSPORT_LOOPBACK_ONLY

from ._digest import sha256_json as _sha256_json
from .composition import (
    CompositionError,
    CompositionOwner,
    EVIDENCE_SOURCE_OUTER_COMPOSED,
)
from .subprocess_supervisor import LineStreamSupervisor, terminate_process
from .worker_contract import (
    ComponentIdentity,
    IdentityChain,
    ProviderIdentity,
    UNKNOWN,
    WorkerContractError,
    WorkerEnvelope,
)


WORKER_BRIDGE_SCHEMA = "zworkbench-worker-bridge/v1"
MAX_WORKER_LINE_BYTES = 64 * 1024
MAX_WORKER_STDERR_BYTES = 64 * 1024
DEFAULT_PROCESS_STOP_TIMEOUT = 2.0
SAFE_INHERITED_ENVIRONMENT = frozenset({"PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ"})
SECRET_VALUE_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,})")


class WorkerBridgeError(RuntimeError):
    """A Worker handshake failure that requires owner safe-stop."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code
        self.safe_stop = True


class FailStopError(WorkerBridgeError):
    """Termination could not be proven clean; the run must fail-stop.

    A run may only be reported as a clean terminal (``safe_stopped`` /
    ``completed``) when its process-group cleanup was provably clean
    (``process_group_clean is True``).  When the verdict is ``False`` (proven
    dirty) or ``None`` (unverifiable), the termination is unhandleable and the
    operation must fail-stop: force the run to ``failed`` and surface this
    error, never silently degrading to a clean success.
    """

    def __init__(self, message: str, *, code: str):
        super().__init__(message, code=code)
        self.safe_stop = False


@dataclass(frozen=True)
class WorkerHandshakeResult:
    """The identity-bound result of one successful Worker handshake."""

    identity: IdentityChain
    provider_identity: ProviderIdentity
    worker_artifact_identity: ComponentIdentity
    worker_schema_identity: ComponentIdentity
    replay_mode: str
    policy_digest: str
    environment_digest: str
    workspace_digest: str
    status: str
    exit_code: int

    def to_dict(self) -> Dict[str, Any]:
        """Return a non-secret result suitable for CompositionOwner."""

        return {
            "bridge_schema": WORKER_BRIDGE_SCHEMA,
            "status": self.status,
            "identity": self.identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "worker_artifact_identity": self.worker_artifact_identity.to_dict(),
            "worker_schema_identity": self.worker_schema_identity.to_dict(),
            "replay_mode": self.replay_mode,
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "workspace_digest": self.workspace_digest,
            "exit_code": self.exit_code,
        }


@dataclass(frozen=True)
class WorkerCodingResult:
    """The owner-visible result of one bounded read-only coding turn."""

    identity: IdentityChain
    provider_identity: ProviderIdentity
    worker_artifact_identity: ComponentIdentity
    worker_schema_identity: ComponentIdentity
    replay_mode: str
    policy_digest: str
    environment_digest: str
    workspace_digest: str
    semantic_result: Mapping[str, Any]
    artifacts: Mapping[str, Mapping[str, Any]]
    status: str
    exit_code: int

    def to_dict(self) -> Dict[str, Any]:
        """Return a non-secret result suitable for CompositionOwner."""

        return {
            "bridge_schema": WORKER_BRIDGE_SCHEMA,
            "status": self.status,
            "identity": self.identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "worker_artifact_identity": self.worker_artifact_identity.to_dict(),
            "worker_schema_identity": self.worker_schema_identity.to_dict(),
            "replay_mode": self.replay_mode,
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "workspace_digest": self.workspace_digest,
            "semantic_result": dict(self.semantic_result),
            "artifacts": {name: dict(value) for name, value in self.artifacts.items()},
            "exit_code": self.exit_code,
        }


class WorkerBridge:
    """Start one fixed Worker process and bind its handshake to owner state."""

    def __init__(
        self,
        owner: CompositionOwner,
        executable: os.PathLike[str] | str,
        case_root: os.PathLike[str] | str,
        *,
        worker_artifact_identity: ComponentIdentity,
        worker_schema_identity: ComponentIdentity,
        provider_identity: ProviderIdentity,
        policy_digest: str,
        environment_digest: str,
        workspace_digest: str,
        worker_args: Sequence[str] = (),
        recovery_mode: bool = False,
    ) -> None:
        if not isinstance(worker_artifact_identity, ComponentIdentity):
            raise TypeError("worker_artifact_identity must be ComponentIdentity")
        if not isinstance(worker_schema_identity, ComponentIdentity):
            raise TypeError("worker_schema_identity must be ComponentIdentity")
        if not isinstance(provider_identity, ProviderIdentity):
            raise TypeError("provider_identity must be ProviderIdentity")
        self.owner = owner
        self.executable = self._resolve_executable(executable)
        self.case_root = Path(case_root).expanduser().resolve()
        self.worker_args = tuple(self._require_arg(item) for item in worker_args)
        self.worker_artifact_identity = worker_artifact_identity
        self.worker_schema_identity = worker_schema_identity
        self.provider_identity = provider_identity
        self.policy_digest = self._require_text(policy_digest, "policy_digest")
        self.environment_digest = self._require_text(environment_digest, "environment_digest")
        self.workspace_digest = self._require_text(workspace_digest, "workspace_digest")
        if not isinstance(recovery_mode, bool):
            raise TypeError("recovery_mode must be bool")
        self.recovery_mode = recovery_mode
        self._validate_provider()
        self._state_lock = threading.RLock()
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.active_child_run_id: Optional[str] = None
        self._active_parent_run_id: Optional[str] = None
        self._active_attempt_id: Optional[str] = None
        self._active_operation: Optional[str] = None
        self._active_command: Optional[Tuple[str, ...]] = None
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        self._last_exit_receipt: Optional[Dict[str, Any]] = None
        self._exit_receipt_recorded = False
        self._termination_reason: Optional[str] = None
        self._termination_code: Optional[str] = None
        self._termination_signal: Optional[int] = None
        self._termination_forced = False
        self._process_group_clean: Optional[bool] = None
        self._orphan_processes: Optional[int] = None

    def handshake(
        self,
        parent_run_id: str,
        *,
        child_run_id: str,
        attempt_id: str,
        dsh_session_id: str,
        dsh_turn_id: str,
        timeout: float = 15.0,
        recovery_of_child_run_id: Optional[str] = None,
    ) -> WorkerHandshakeResult:
        """Complete one request/response handshake or safe-stop both runs."""

        for value, name in (
            (parent_run_id, "parent_run_id"),
            (child_run_id, "child_run_id"),
            (attempt_id, "attempt_id"),
            (dsh_session_id, "dsh_session_id"),
            (dsh_turn_id, "dsh_turn_id"),
        ):
            self._require_text(value, name)
        if recovery_of_child_run_id is not None:
            self._require_text(recovery_of_child_run_id, "recovery_of_child_run_id")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if not self.case_root.is_dir():
            raise WorkerBridgeError("case root must already be a directory", code="case_root_missing")
        workspace = self.case_root / "workspace"
        if not workspace.is_dir():
            raise WorkerBridgeError("case-local workspace must already be a directory", code="workspace_missing")
        parent = self.owner.get_run(parent_run_id)
        if parent["status"] != "running":
            raise WorkerBridgeError("parent Run must be running before Worker handshake", code="parent_not_running")

        request_identity = IdentityChain(
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            attempt_id=attempt_id,
            dsh_session_id=dsh_session_id,
            dsh_turn_id=dsh_turn_id,
            worker_run_id=child_run_id,
            codex_thread_id=UNKNOWN,
            codex_turn_id=UNKNOWN,
            event_id=f"{child_run_id}:handshake.request",
            artifact_id=f"{child_run_id}:worker-artifact",
        )
        request = WorkerEnvelope(
            message_type="handshake.request",
            identity=request_identity,
            provider_identity=self.provider_identity,
            replay_mode="normal",
            policy_digest=self.policy_digest,
            environment_digest=self.environment_digest,
            workspace_digest=self.workspace_digest,
            worker_artifact_identity=self.worker_artifact_identity,
            worker_schema_identity=self.worker_schema_identity,
            payload={"operation": "handshake", "status": "requested"},
        )
        child_metadata = {
            "bridge_schema": WORKER_BRIDGE_SCHEMA,
            "parent_run_id": parent_run_id,
            "attempt_id": attempt_id,
            "identity": request_identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "worker_artifact_identity": self.worker_artifact_identity.to_dict(),
            "worker_schema_identity": self.worker_schema_identity.to_dict(),
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "workspace_digest": self.workspace_digest,
        }
        if recovery_of_child_run_id is not None:
            child_metadata["recovery_of_child_run_id"] = recovery_of_child_run_id
        self._activate_operation(parent_run_id, child_run_id, attempt_id, "handshake")
        try:
            self.owner.create_run(child_run_id, "worker.handshake", {"operation": "handshake"}, child_metadata)
            self.owner.start_run(child_run_id)
        except Exception:
            self._deactivate_operation()
            try:
                self.owner.safe_stop_run(child_run_id, "worker:child_start_failed")
            except Exception:
                pass
            raise
        try:
            self.owner.record_event(
                child_run_id,
                "worker.handshake.requested",
                {"identity": request_identity.to_dict(), "message_type": request.message_type},
                f"{child_run_id}:handshake-requested",
                evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
            )
            self.owner.record_result(child_run_id, "worker.handshake.request", request.to_dict(), f"{child_run_id}:handshake-request", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            response, exit_code = self._run_process(request, parent_run_id, child_run_id, attempt_id, timeout)
            self._raise_if_stop_requested()
            self._record_exit(child_run_id)
            if exit_code != 0:
                raise WorkerBridgeError("Worker exited with a non-zero code", code="worker_exit_nonzero")
            result = self._validate_response(response, request)
            self.owner.record_result(child_run_id, "worker.handshake", result.to_dict(), f"{child_run_id}:handshake", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            self.owner.complete_run(child_run_id, result.to_dict())
            self.owner.record_event(
                parent_run_id,
                "worker.handshake.completed",
                result.to_dict(),
                f"{child_run_id}:handshake-completed",
                evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
            )
            self.owner.record_result(parent_run_id, "worker.handshake", result.to_dict(), f"{child_run_id}:handshake", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            return result
        except Exception as exc:
            error = exc if isinstance(exc, WorkerBridgeError) else WorkerBridgeError(str(exc), code="worker_bridge_failure")
            self._stop_process(reason=self._termination_reason_for_error(error), code=error.code)
            self._record_exit(child_run_id)
            self._record_failure(parent_run_id, child_run_id, error)
            raise error
        finally:
            self._stop_process()
            self._deactivate_operation()

    def read_only_coding(
        self,
        parent_run_id: str,
        *,
        child_run_id: str,
        attempt_id: str,
        dsh_session_id: str,
        dsh_turn_id: str,
        prompt: str,
        artifact_root: os.PathLike[str] | str,
        timeout: float = 45.0,
        recovery_of_child_run_id: Optional[str] = None,
    ) -> WorkerCodingResult:
        """Run one strict handshake-to-result read-only coding turn.

        The Worker receives a handshake request whose operation is
        ``read_only_coding``.  It must emit exactly one complete
        ``handshake.response`` followed by exactly one complete ``result``.
        The bridge verifies the case-local artifacts and workspace snapshot
        before the child Run can complete.  The parent remains running for
        later H4/H5 orchestration.
        """

        for value, name in (
            (parent_run_id, "parent_run_id"),
            (child_run_id, "child_run_id"),
            (attempt_id, "attempt_id"),
            (dsh_session_id, "dsh_session_id"),
            (dsh_turn_id, "dsh_turn_id"),
            (prompt, "prompt"),
        ):
            self._require_text(value, name)
        if recovery_of_child_run_id is not None:
            self._require_text(recovery_of_child_run_id, "recovery_of_child_run_id")
        if SECRET_VALUE_PATTERN.search(prompt):
            raise WorkerBridgeError("coding prompt contains a credential-like value", code="prompt_credential_forbidden")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        artifact_root_path = self._validate_artifact_root(artifact_root)
        if not self.case_root.is_dir():
            raise WorkerBridgeError("case root must already be a directory", code="case_root_missing")
        workspace = self.case_root / "workspace"
        if not workspace.is_dir():
            raise WorkerBridgeError("case-local workspace must already be a directory", code="workspace_missing")
        parent = self.owner.get_run(parent_run_id)
        if parent["status"] != "running":
            raise WorkerBridgeError("parent Run must be running before Worker coding", code="parent_not_running")

        request_identity = IdentityChain(
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            attempt_id=attempt_id,
            dsh_session_id=dsh_session_id,
            dsh_turn_id=dsh_turn_id,
            worker_run_id=child_run_id,
            codex_thread_id=UNKNOWN,
            codex_turn_id=UNKNOWN,
            event_id=f"{child_run_id}:coding.request",
            artifact_id=f"{child_run_id}:worker-artifact",
        )
        request = WorkerEnvelope(
            message_type="handshake.request",
            identity=request_identity,
            provider_identity=self.provider_identity,
            replay_mode="normal",
            policy_digest=self.policy_digest,
            environment_digest=self.environment_digest,
            workspace_digest=self.workspace_digest,
            worker_artifact_identity=self.worker_artifact_identity,
            worker_schema_identity=self.worker_schema_identity,
            payload={
                "operation": "read_only_coding",
                "prompt": prompt,
                "artifact_root": "case-local/evidence/artifacts",
            },
        )
        child_metadata = {
            "bridge_schema": WORKER_BRIDGE_SCHEMA,
            "operation": "read_only_coding",
            "parent_run_id": parent_run_id,
            "attempt_id": attempt_id,
            "identity": request_identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "worker_artifact_identity": self.worker_artifact_identity.to_dict(),
            "worker_schema_identity": self.worker_schema_identity.to_dict(),
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "workspace_digest": self.workspace_digest,
        }
        if recovery_of_child_run_id is not None:
            child_metadata["recovery_of_child_run_id"] = recovery_of_child_run_id
        self._activate_operation(parent_run_id, child_run_id, attempt_id, "read_only_coding")
        try:
            self.owner.create_run(child_run_id, "worker.read_only_coding", {"operation": "read_only_coding", "prompt": prompt}, child_metadata)
            self.owner.start_run(child_run_id)
        except Exception:
            self._deactivate_operation()
            try:
                self.owner.safe_stop_run(child_run_id, "worker:child_start_failed")
            except Exception:
                pass
            raise
        workspace_before = self._workspace_snapshot(workspace)
        artifact_before = self._workspace_snapshot(artifact_root_path)
        try:
            if artifact_before:
                raise WorkerBridgeError("artifact root must be empty before coding", code="artifact_root_not_empty")
            self.owner.record_event(
                child_run_id,
                "worker.coding.requested",
                {"identity": request_identity.to_dict(), "message_type": request.message_type, "operation": "read_only_coding"},
                f"{child_run_id}:coding-requested",
                evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
            )
            self.owner.record_result(child_run_id, "worker.coding.request", request.to_dict(), f"{child_run_id}:coding-request", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            handshake, coding, exit_code = self._run_coding_process(
                request,
                parent_run_id,
                child_run_id,
                attempt_id,
                artifact_root_path,
                timeout,
            )
            self._raise_if_stop_requested()
            self._record_exit(child_run_id)
            if exit_code != 0:
                raise WorkerBridgeError("Worker exited with a non-zero code", code="worker_exit_nonzero")
            handshake_result = self._validate_response(handshake, request)
            self.owner.record_result(child_run_id, "worker.handshake", handshake_result.to_dict(), f"{child_run_id}:coding-handshake", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            result = self._validate_coding_result(coding, request, handshake_result, artifact_root_path)
            if self._workspace_snapshot(workspace) != workspace_before:
                raise WorkerBridgeError("Worker changed the case-local workspace", code="coding_workspace_changed")
            declared_paths = {descriptor["path"] for descriptor in result.artifacts.values()}
            actual_paths = set(self._workspace_snapshot(artifact_root_path))
            if actual_paths != declared_paths:
                raise WorkerBridgeError("Worker emitted undeclared coding artifacts", code="coding_artifact_set_mismatch")
            self.owner.record_result(child_run_id, "worker.coding", result.to_dict(), f"{child_run_id}:coding", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            self.owner.complete_run(child_run_id, result.to_dict())
            self.owner.record_event(parent_run_id, "worker.coding.completed", result.to_dict(), f"{child_run_id}:coding-completed", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            self.owner.record_result(parent_run_id, "worker.coding", result.to_dict(), f"{child_run_id}:coding", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            return result
        except Exception as exc:
            error = exc if isinstance(exc, WorkerBridgeError) else WorkerBridgeError(str(exc), code="worker_bridge_failure")
            self._stop_process(reason=self._termination_reason_for_error(error), code=error.code)
            self._record_exit(child_run_id)
            self._record_failure(parent_run_id, child_run_id, error)
            raise error
        finally:
            self._stop_process()
            self._deactivate_operation()

    def command(self) -> list[str]:
        """Return the exact shell-free Worker argv."""

        return [str(self.executable), *self.worker_args]

    def cancel(
        self,
        parent_run_id: str,
        *,
        reason: str = "cancelled",
    ) -> Dict[str, Any]:
        """Request cancellation of the active Worker and safe-stop both Runs."""

        return self._request_lifecycle_stop(parent_run_id, reason=reason, code="worker_cancelled")

    def stop_parent(
        self,
        parent_run_id: str,
        *,
        reason: str = "parent_stop",
    ) -> Dict[str, Any]:
        """Stop a parent Run and its active Worker process tree."""

        return self._request_lifecycle_stop(parent_run_id, reason=reason, code="worker_parent_stopped")

    def recover_handshake(
        self,
        parent_run_id: str,
        *,
        recovery_of_child_run_id: str,
        child_run_id: str,
        attempt_id: str,
        dsh_session_id: str,
        dsh_turn_id: str,
        timeout: float = 15.0,
    ) -> WorkerHandshakeResult:
        """Resume a recovering parent using a new owner-correlated attempt."""

        self._prepare_recovery(parent_run_id, recovery_of_child_run_id)
        return self.handshake(
            parent_run_id,
            child_run_id=child_run_id,
            attempt_id=attempt_id,
            dsh_session_id=dsh_session_id,
            dsh_turn_id=dsh_turn_id,
            timeout=timeout,
            recovery_of_child_run_id=recovery_of_child_run_id,
        )

    def recover_read_only_coding(
        self,
        parent_run_id: str,
        *,
        recovery_of_child_run_id: str,
        child_run_id: str,
        attempt_id: str,
        dsh_session_id: str,
        dsh_turn_id: str,
        prompt: str,
        artifact_root: os.PathLike[str] | str,
        timeout: float = 45.0,
    ) -> WorkerCodingResult:
        """Resume a recovering parent with a fresh read-only coding attempt."""

        self._prepare_recovery(parent_run_id, recovery_of_child_run_id)
        return self.read_only_coding(
            parent_run_id,
            child_run_id=child_run_id,
            attempt_id=attempt_id,
            dsh_session_id=dsh_session_id,
            dsh_turn_id=dsh_turn_id,
            prompt=prompt,
            artifact_root=artifact_root,
            timeout=timeout,
            recovery_of_child_run_id=recovery_of_child_run_id,
        )

    def close(self) -> None:
        """Stop an active Worker without deleting case-local evidence."""

        self._stop_process()

    def __enter__(self) -> "WorkerBridge":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def _activate_operation(self, parent_run_id: str, child_run_id: str, attempt_id: str, operation: str) -> None:
        with self._state_lock:
            if self.process is not None or self.active_child_run_id is not None:
                raise WorkerBridgeError("WorkerBridge already has an active operation", code="worker_bridge_busy")
            self.active_child_run_id = child_run_id
            self._active_parent_run_id = parent_run_id
            self._active_attempt_id = attempt_id
            self._active_operation = operation
            self._last_exit_receipt = None
            self._exit_receipt_recorded = False
            self._termination_reason = None
            self._termination_code = None
            self._termination_signal = None
            self._termination_forced = False
            self._process_group_clean = None

    def _deactivate_operation(self) -> None:
        with self._state_lock:
            self.active_child_run_id = None
            self._active_parent_run_id = None
            self._active_attempt_id = None
            self._active_operation = None

    def _prepare_recovery(self, parent_run_id: str, recovery_of_child_run_id: str) -> None:
        self._require_text(parent_run_id, "parent_run_id")
        self._require_text(recovery_of_child_run_id, "recovery_of_child_run_id")
        parent = self.owner.get_run(parent_run_id)
        if parent["status"] != "recovering":
            raise WorkerBridgeError(
                "parent Run is not in recovering state",
                code="recovery_not_available",
            )
        previous_child = self.owner.get_run(recovery_of_child_run_id)
        if (
            previous_child["status"] not in {"failed", "safe_stopped"}
            or previous_child["metadata"].get("parent_run_id") != parent_run_id
        ):
            raise WorkerBridgeError(
                "recovery source child is not a terminal child of the parent Run",
                code="recovery_source_invalid",
            )
        self.owner.start_run(parent_run_id)
        self.owner.record_event(
            parent_run_id,
            "worker.recovery.requested",
            {
                "recovery_of_child_run_id": recovery_of_child_run_id,
                "recovery_parent_run_id": parent_run_id,
            },
            f"{parent_run_id}:worker-recovery:{recovery_of_child_run_id}",
            evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
        )

    def _request_lifecycle_stop(self, parent_run_id: str, *, reason: str, code: str) -> Dict[str, Any]:
        self._require_text(parent_run_id, "parent_run_id")
        self._require_text(reason, "reason")
        with self._state_lock:
            child_run_id = self.active_child_run_id
            active_parent_run_id = self._active_parent_run_id
            process = self.process
            if child_run_id is None or active_parent_run_id != parent_run_id:
                raise WorkerBridgeError("no active Worker belongs to parent Run", code="worker_not_active")
            if process is None:
                raise WorkerBridgeError("active Worker process is unavailable", code="worker_process_missing")
            self._termination_reason = reason
            self._termination_code = code
            pid = process.pid

        payload = {
            "code": code,
            "reason": reason,
            "process_id": pid,
            "process_group_id": pid,
            "operation": self._active_operation,
        }
        self.owner.record_event(
            child_run_id,
            "worker.stop.requested",
            payload,
            f"{child_run_id}:worker-stop:{code}",
            evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
        )
        self.owner.record_result(
            child_run_id,
            "worker.stop",
            payload,
            f"{child_run_id}:worker-stop:{code}",
            evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
        )
        self.owner.record_event(
            parent_run_id,
            "worker.stop.requested",
            payload,
            f"{parent_run_id}:worker-stop:{code}:{child_run_id}",
            evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
        )
        for run_id in (child_run_id, parent_run_id):
            try:
                self.owner.safe_stop_run(run_id, f"worker:{code}")
            except CompositionError:
                # A racing terminal transition is safe only when the owner is
                # already terminal; the bridge loop will still reject success.
                current = self.owner.get_run(run_id)
                if current["status"] not in {"failed", "safe_stopped"}:
                    raise
        self._signal_process(signal.SIGTERM)
        return {"requested": True, **payload}

    def _signal_process(self, requested_signal: int) -> None:
        with self._state_lock:
            process = self.process
            if process is None or process.poll() is not None:
                return
            pid = process.pid
            self._termination_signal = requested_signal
        try:
            os.killpg(pid, requested_signal)
        except (ProcessLookupError, PermissionError):
            try:
                if requested_signal == signal.SIGTERM:
                    process.terminate()
                else:
                    process.kill()
            except (ProcessLookupError, PermissionError):
                pass

    def _raise_if_stop_requested(self) -> None:
        with self._state_lock:
            code = self._termination_code
            reason = self._termination_reason
        if code is not None:
            raise WorkerBridgeError(
                f"Worker stopped by lifecycle control: {reason}",
                code=code,
            )

    def _termination_reason_for_error(self, error: WorkerBridgeError) -> str:
        with self._state_lock:
            if self._termination_reason is not None:
                return self._termination_reason
        if error.code in {"worker_timeout", "worker_exit_timeout"}:
            return "timeout"
        if error.code == "worker_parent_stopped":
            return "parent_stop"
        if error.code == "worker_cancelled":
            return "cancelled"
        if error.code == "worker_exit_nonzero":
            return "child_crash"
        return "bridge_failure"

    def _run_process(
        self,
        request: WorkerEnvelope,
        parent_run_id: str,
        child_run_id: str,
        attempt_id: str,
        timeout: float,
    ) -> Tuple[WorkerEnvelope, int]:
        workspace = self.case_root / "workspace"
        command = tuple(self.command())
        environment = self._build_environment(parent_run_id, child_run_id, attempt_id)
        self._active_command = command
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(workspace),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                close_fds=True,
            )
        except (OSError, ValueError) as exc:
            raise WorkerBridgeError("Worker failed to start", code="worker_start_failed") from exc
        if self.process.stdin is None or self.process.stdout is None or self.process.stderr is None:
            raise WorkerBridgeError("Worker streams are unavailable", code="worker_stream_missing")
        try:
            self.process.stdin.write((request.to_json() + "\n").encode("utf-8"))
            self.process.stdin.flush()
            self.process.stdin.close()
        except OSError as exc:
            raise WorkerBridgeError("Worker handshake request could not be sent", code="worker_request_failed") from exc

        response: Optional[WorkerEnvelope] = None

        def on_line(line: bytes) -> None:
            nonlocal response
            if response is not None:
                raise WorkerBridgeError("Worker emitted more than one handshake response", code="handshake_extra_message")
            response = self._parse_response(line)

        supervisor = LineStreamSupervisor(
            on_line=on_line,
            line_cap_bytes=MAX_WORKER_LINE_BYTES,
            stderr_cap_bytes=MAX_WORKER_STDERR_BYTES,
            on_timeout=lambda: WorkerBridgeError("Worker handshake timed out", code="worker_timeout"),
            on_line_too_large=lambda: WorkerBridgeError("Worker handshake message exceeds size limit", code="handshake_message_too_large"),
            on_stderr_too_large=lambda: WorkerBridgeError("Worker stderr exceeds size limit", code="worker_stderr_too_large"),
            on_incomplete_line=lambda: WorkerBridgeError("Worker emitted incomplete JSONL", code="handshake_incomplete_jsonl"),
            on_empty_line=lambda: WorkerBridgeError("Worker emitted an empty JSONL message", code="handshake_empty_line"),
            on_iteration=self._raise_if_stop_requested,
        )
        deadline = time.monotonic() + timeout
        supervisor.read(self.process, deadline=deadline)
        self._stderr_digest = supervisor.stderr_digest
        self._stderr_bytes = supervisor.stderr_bytes
        if response is None:
            self._raise_if_stop_requested()
            exit_code = self._wait_for_exit(deadline)
            self._last_exit_receipt = self._exit_receipt(exit_code, command)
            if exit_code != 0:
                raise WorkerBridgeError("Worker exited with a non-zero code", code="worker_exit_nonzero")
            raise WorkerBridgeError("Worker emitted no handshake response", code="handshake_response_missing")
        exit_code = self._wait_for_exit(deadline)
        self._last_exit_receipt = self._exit_receipt(exit_code, command)
        return response, exit_code

    def _run_coding_process(
        self,
        request: WorkerEnvelope,
        parent_run_id: str,
        child_run_id: str,
        attempt_id: str,
        artifact_root: Path,
        timeout: float,
    ) -> Tuple[WorkerEnvelope, WorkerEnvelope, int]:
        """Run a Worker and consume exactly handshake.response + result."""

        workspace = self.case_root / "workspace"
        command = tuple(self.command())
        environment = self._build_environment(parent_run_id, child_run_id, attempt_id, artifact_root)
        self._active_command = command
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(workspace),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                close_fds=True,
            )
        except (OSError, ValueError) as exc:
            raise WorkerBridgeError("Worker failed to start", code="worker_start_failed") from exc
        if self.process.stdin is None or self.process.stdout is None or self.process.stderr is None:
            raise WorkerBridgeError("Worker streams are unavailable", code="worker_stream_missing")
        try:
            self.process.stdin.write((request.to_json() + "\n").encode("utf-8"))
            self.process.stdin.flush()
            self.process.stdin.close()
        except OSError as exc:
            raise WorkerBridgeError("Worker coding request could not be sent", code="worker_request_failed") from exc

        responses: list[WorkerEnvelope] = []

        def on_line(line: bytes) -> None:
            if len(responses) >= 2:
                raise WorkerBridgeError("Worker emitted more than two coding messages", code="coding_extra_message")
            responses.append(self._parse_response(line))

        supervisor = LineStreamSupervisor(
            on_line=on_line,
            line_cap_bytes=MAX_WORKER_LINE_BYTES,
            stderr_cap_bytes=MAX_WORKER_STDERR_BYTES,
            on_timeout=lambda: WorkerBridgeError("Worker coding timed out", code="worker_timeout"),
            on_line_too_large=lambda: WorkerBridgeError("Worker coding message exceeds size limit", code="coding_message_too_large"),
            on_stderr_too_large=lambda: WorkerBridgeError("Worker stderr exceeds size limit", code="worker_stderr_too_large"),
            on_incomplete_line=lambda: WorkerBridgeError("Worker emitted incomplete JSONL", code="coding_incomplete_jsonl"),
            on_empty_line=lambda: WorkerBridgeError("Worker emitted an empty JSONL message", code="coding_empty_line"),
            on_iteration=self._raise_if_stop_requested,
        )
        deadline = time.monotonic() + timeout
        supervisor.read(self.process, deadline=deadline)
        self._stderr_digest = supervisor.stderr_digest
        self._stderr_bytes = supervisor.stderr_bytes
        if len(responses) < 2:
            exit_code = self._wait_for_exit(deadline)
            self._last_exit_receipt = self._exit_receipt(exit_code, command)
            self._raise_if_stop_requested()
            if exit_code != 0:
                raise WorkerBridgeError("Worker exited with a non-zero code", code="worker_exit_nonzero")
            raise WorkerBridgeError("Worker coding response sequence is incomplete", code="coding_response_missing")
        if responses[0].message_type != "handshake.response" or responses[1].message_type != "result":
            raise WorkerBridgeError("Worker emitted an invalid coding response sequence", code="coding_extra_message")
        exit_code = self._wait_for_exit(deadline)
        self._last_exit_receipt = self._exit_receipt(exit_code, command)
        return responses[0], responses[1], exit_code

    def _parse_response(self, line: bytes) -> WorkerEnvelope:
        try:
            return WorkerEnvelope.from_json(line.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise WorkerBridgeError("Worker response is not UTF-8 JSON", code="handshake_invalid_json") from exc
        except json.JSONDecodeError as exc:
            raise WorkerBridgeError("Worker response is not valid JSON", code="handshake_invalid_json") from exc
        except WorkerContractError as exc:
            code_map = {
                "unsupported_schema": "handshake_schema_unknown",
                "unknown_wire_message": "handshake_message_unknown",
                "unknown_wire_field": "handshake_field_unknown",
                "envelope_shape_incomplete": "handshake_shape_incomplete",
            }
            raise WorkerBridgeError(
                "Worker response failed strict contract validation",
                code=code_map.get(exc.code, f"handshake_{exc.code}"),
            ) from exc

    def _validate_response(self, response: WorkerEnvelope, request: WorkerEnvelope) -> WorkerHandshakeResult:
        if response.message_type != "handshake.response":
            raise WorkerBridgeError("Worker response is not handshake.response", code="handshake_message_invalid")
        if not response.identity.is_complete():
            raise WorkerBridgeError("Worker handshake identity is incomplete", code="handshake_identity_incomplete")
        static_identity_fields = (
            "parent_run_id",
            "child_run_id",
            "attempt_id",
            "dsh_session_id",
            "dsh_turn_id",
            "worker_run_id",
            "artifact_id",
        )
        for field_name in static_identity_fields:
            if getattr(response.identity, field_name) != getattr(request.identity, field_name):
                raise WorkerBridgeError(
                    f"Worker identity does not match {field_name}",
                    code="handshake_identity_mismatch",
                )
        for field_name, expected in (
            ("provider_identity", request.provider_identity.to_dict()),
            ("worker_artifact_identity", request.worker_artifact_identity.to_dict()),
            ("worker_schema_identity", request.worker_schema_identity.to_dict()),
        ):
            if getattr(response, field_name).to_dict() != expected:
                raise WorkerBridgeError(f"Worker {field_name} does not match request", code="handshake_provenance_mismatch")
        for field_name in ("replay_mode", "policy_digest", "environment_digest", "workspace_digest"):
            if getattr(response, field_name) != getattr(request, field_name):
                raise WorkerBridgeError(f"Worker {field_name} does not match request", code="handshake_provenance_mismatch")
        if response.payload != {"status": "ready"}:
            raise WorkerBridgeError("Worker handshake status is not ready", code="handshake_status_invalid")
        return WorkerHandshakeResult(
            identity=response.identity,
            provider_identity=response.provider_identity,
            worker_artifact_identity=response.worker_artifact_identity,
            worker_schema_identity=response.worker_schema_identity,
            replay_mode=response.replay_mode,
            policy_digest=response.policy_digest,
            environment_digest=response.environment_digest,
            workspace_digest=response.workspace_digest,
            status="handshake_complete",
            exit_code=self._last_exit_receipt["exit_code"] if self._last_exit_receipt else 0,
        )

    def _validate_coding_result(
        self,
        response: WorkerEnvelope,
        request: WorkerEnvelope,
        handshake: WorkerHandshakeResult,
        artifact_root: Path,
    ) -> WorkerCodingResult:
        if response.message_type != "result":
            raise WorkerBridgeError("Worker coding response is not result", code="coding_message_invalid")
        if not response.identity.is_complete():
            raise WorkerBridgeError("Worker coding identity is incomplete", code="coding_identity_incomplete")
        identity_fields = (
            "parent_run_id",
            "child_run_id",
            "attempt_id",
            "dsh_session_id",
            "dsh_turn_id",
            "worker_run_id",
            "codex_thread_id",
            "codex_turn_id",
        )
        for field_name in identity_fields:
            expected = getattr(handshake.identity, field_name)
            if getattr(response.identity, field_name) != expected:
                raise WorkerBridgeError(f"Worker coding identity does not match {field_name}", code="coding_identity_mismatch")
        for field_name, expected in (
            ("provider_identity", request.provider_identity.to_dict()),
            ("worker_artifact_identity", request.worker_artifact_identity.to_dict()),
            ("worker_schema_identity", request.worker_schema_identity.to_dict()),
        ):
            if getattr(response, field_name).to_dict() != expected:
                raise WorkerBridgeError(f"Worker coding {field_name} does not match request", code="coding_provenance_mismatch")
        for field_name in ("replay_mode", "policy_digest", "environment_digest", "workspace_digest"):
            if getattr(response, field_name) != getattr(request, field_name):
                raise WorkerBridgeError(f"Worker coding {field_name} does not match request", code="coding_provenance_mismatch")
        payload = dict(response.payload)
        if set(payload) != {"status", "operation", "semantic_result", "artifacts"}:
            raise WorkerBridgeError("Worker coding result payload shape is unknown", code="coding_payload_unknown")
        if payload["status"] != "completed" or payload["operation"] != "read_only_coding":
            raise WorkerBridgeError("Worker coding result is not completed read_only_coding", code="coding_status_invalid")
        semantic_result = payload["semantic_result"]
        artifacts = payload["artifacts"]
        if not isinstance(semantic_result, Mapping) or not isinstance(artifacts, Mapping):
            raise WorkerBridgeError("Worker coding semantic result or artifacts is not an object", code="coding_payload_invalid")
        if set(artifacts) != {"diff", "tests", "semantic", "runtime_events"}:
            raise WorkerBridgeError("Worker coding artifact set is incomplete", code="coding_artifacts_incomplete")
        checked_artifacts: Dict[str, Mapping[str, Any]] = {}
        for name, descriptor_value in artifacts.items():
            if not isinstance(name, str) or not isinstance(descriptor_value, Mapping):
                raise WorkerBridgeError("Worker coding artifact descriptor is invalid", code="coding_artifact_invalid")
            descriptor = dict(descriptor_value)
            if set(descriptor) != {"path", "digest", "bytes"}:
                raise WorkerBridgeError("Worker coding artifact descriptor has unknown fields", code="coding_artifact_unknown")
            path_value = descriptor["path"]
            digest_value = descriptor["digest"]
            byte_count = descriptor["bytes"]
            if not isinstance(path_value, str) or not path_value or Path(path_value).is_absolute():
                raise WorkerBridgeError("Worker coding artifact path is not relative", code="coding_artifact_path_invalid")
            if not isinstance(digest_value, str) or not _is_sha256(digest_value):
                raise WorkerBridgeError("Worker coding artifact digest is invalid", code="coding_artifact_digest_invalid")
            if not isinstance(byte_count, int) or byte_count < 0:
                raise WorkerBridgeError("Worker coding artifact byte count is invalid", code="coding_artifact_bytes_invalid")
            candidate = (artifact_root / path_value).resolve()
            if artifact_root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
                raise WorkerBridgeError("Worker coding artifact escapes or is missing", code="coding_artifact_path_invalid")
            actual_bytes = candidate.read_bytes()
            actual_digest = "sha256:" + hashlib.sha256(actual_bytes).hexdigest()
            if len(actual_bytes) != byte_count or actual_digest != digest_value:
                raise WorkerBridgeError("Worker coding artifact digest does not match", code="coding_artifact_digest_mismatch")
            checked_artifacts[name] = {"path": path_value, "digest": digest_value, "bytes": byte_count}
        # Fail-stop contract: a "completed" Worker result is impossible when
        # the termination was not provably clean.  This guards the happy path
        # before the caller issues complete_run on the parent Run.
        self.assert_clean_termination()
        return WorkerCodingResult(
            identity=response.identity,
            provider_identity=response.provider_identity,
            worker_artifact_identity=response.worker_artifact_identity,
            worker_schema_identity=response.worker_schema_identity,
            replay_mode=response.replay_mode,
            policy_digest=response.policy_digest,
            environment_digest=response.environment_digest,
            workspace_digest=response.workspace_digest,
            semantic_result=dict(semantic_result),
            artifacts=checked_artifacts,
            status="completed",
            exit_code=self._last_exit_receipt["exit_code"] if self._last_exit_receipt else 0,
        )

    def assert_clean_termination(self) -> None:
        """Fail-stop if the last Worker termination was not provably clean.

        See :class:`FailStopError`.  A run may only be reported as a clean
        terminal (``safe_stopped`` / ``completed``) when ``process_group_clean``
        is ``True``.  Any other verdict (``False`` = proven dirty, ``None`` =
        unverifiable) is unhandleable and must fail-stop rather than be silently
        reported as a clean success.
        """

        with self._state_lock:
            clean = self._process_group_clean
        if clean is not True:
            raise FailStopError(
                "Worker termination not provably clean; refusing clean terminal",
                code="worker_cleanup_unverified",
            )

    def _record_failure(self, parent_run_id: str, child_run_id: str, error: WorkerBridgeError) -> None:
        payload = {"code": error.code, "error_type": type(error).__name__, "message": str(error)}
        try:
            self.owner.record_result(child_run_id, "worker.error", payload, f"{child_run_id}:worker-error:{error.code}", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            child_receipt = self._last_exit_receipt or {}
            if child_receipt.get("process_group_clean") is True:
                self.owner.safe_stop_run(child_run_id, f"worker:{error.code}")
            else:
                # The child's own termination was not provably clean; fail-stop
                # it instead of silently safe-stopping.
                self.owner.fail_run(child_run_id, "worker:child-cleanup-unverified")
        except Exception:
            # The original error remains caller-visible; the owner is
            # inspected separately if a secondary ledger write fails.
            pass
        try:
            self.owner.record_result(parent_run_id, "worker.error", payload, f"{parent_run_id}:worker-error:{error.code}", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
            receipt = self._last_exit_receipt or {}
            cleanup_verified = receipt.get("process_group_clean") is True
            if not cleanup_verified:
                # Fail-stop: the Worker termination could not be proven clean.
                # Do not silently safe-stop a run whose process group was not
                # reaped.  The authoritative action is raising FailStopError;
                # the fail_run attempt below is best-effort.
                try:
                    self.owner.fail_run(parent_run_id, "worker:cleanup-unverified")
                except Exception:
                    pass
                raise FailStopError(
                    "Worker termination not provably clean; fail-stop",
                    code="worker_cleanup_unverified",
                )
            recoverable = error.code in {"worker_timeout", "worker_exit_timeout", "worker_exit_nonzero"}
            if self.recovery_mode and recoverable:
                self.owner.begin_recovery(parent_run_id, f"worker:{error.code}")
            else:
                self.owner.safe_stop_run(parent_run_id, f"worker:{error.code}")
        except FailStopError:
            raise
        except Exception:
            # A failed recovery transition is fail-closed.  Do not turn a
            # partially observed lifecycle into a completed or retryable run.
            try:
                self.owner.safe_stop_run(parent_run_id, f"worker:{error.code}")
            except Exception:
                pass

    def _wait_for_exit(self, deadline: float) -> int:
        if self.process is None:
            raise WorkerBridgeError("Worker process is unavailable", code="worker_process_missing")
        remaining = max(0.01, deadline - time.monotonic())
        try:
            exit_code = self.process.wait(timeout=remaining)
            self._ensure_process_group_clean(self.process.pid)
            return exit_code
        except subprocess.TimeoutExpired as exc:
            raise WorkerBridgeError("Worker did not exit before timeout", code="worker_exit_timeout") from exc

    def _record_exit(self, child_run_id: str) -> None:
        if self._last_exit_receipt is None or self._exit_receipt_recorded:
            return
        self.owner.record_result(child_run_id, "worker.exit", self._last_exit_receipt, f"{child_run_id}:worker-exit", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
        self._exit_receipt_recorded = True
        # Symmetric Provider-side ledger: the worker IS the Provider engagement
        # for this child run, so the Provider-side accounting is recorded exactly
        # once (paired with the local worker.exit ledger above) at the same
        # termination boundary.  A harness (e.g. local_run) recording the parent
        # run's Provider ledger is a separate run and is not deduplicated here.
        try:
            self.owner.record_provider_exit_ledger_once(child_run_id, self.provider_identity.to_dict())
        except Exception:
            # The local receipt above is the authoritative local accounting; a
            # Provider-ledger write failure must never mask it.
            pass

    def _build_environment(
        self,
        parent_run_id: str,
        child_run_id: str,
        attempt_id: str,
        artifact_root: Optional[Path] = None,
    ) -> Dict[str, str]:
        environment = {key: value for key, value in os.environ.items() if key in SAFE_INHERITED_ENVIRONMENT}
        environment.update(
            {
                "ZWORKBENCH_PARENT_RUN_ID": parent_run_id,
                "ZWORKBENCH_CHILD_RUN_ID": child_run_id,
                "ZWORKBENCH_ATTEMPT_ID": attempt_id,
                "ZWORKBENCH_WORKER_SCHEMA": self.worker_schema_identity.version,
                "ZWORKBENCH_H2": "1",
            }
        )
        if artifact_root is not None:
            environment["ZWORKBENCH_ARTIFACT_ROOT"] = str(artifact_root)
        return environment

    def _validate_artifact_root(self, artifact_root: os.PathLike[str] | str) -> Path:
        candidate = Path(artifact_root).expanduser().resolve()
        if not candidate.is_dir():
            raise WorkerBridgeError("artifact root must already be a directory", code="artifact_root_missing")
        if self.case_root not in candidate.parents:
            raise WorkerBridgeError("artifact root must remain inside case root", code="artifact_root_outside_case")
        workspace = (self.case_root / "workspace").resolve()
        if candidate == workspace or workspace in candidate.parents or candidate in workspace.parents:
            raise WorkerBridgeError("artifact root must be separate from workspace", code="artifact_root_workspace_overlap")
        return candidate

    @staticmethod
    def _workspace_snapshot(workspace: Path) -> Dict[str, str]:
        snapshot: Dict[str, str] = {}
        for path in sorted(workspace.rglob("*")):
            if path.is_file() and not path.is_symlink():
                snapshot[str(path.relative_to(workspace))] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        return snapshot

    def _exit_receipt(self, exit_code: int, command: Sequence[str]) -> Dict[str, Any]:
        with self._state_lock:
            termination_reason = self._termination_reason
            termination_signal = self._termination_signal
            termination_forced = self._termination_forced
            process_group_clean = self._process_group_clean
            process_id = self.process.pid if self.process is not None else None
        if termination_reason is None:
            termination_reason = "normal_exit" if exit_code == 0 else "child_crash"
        if termination_reason in {"cancelled", "operator_cancelled"}:
            outcome = "cancelled"
        elif termination_reason == "parent_stop":
            outcome = "parent_stopped"
        elif termination_reason == "timeout":
            outcome = "timed_out"
        elif termination_reason == "child_crash":
            outcome = "crashed"
        elif termination_reason == "normal_exit":
            outcome = "completed"
        else:
            outcome = "failed"
        return {
            "status": "exited",
            "outcome": outcome,
            "exit_code": exit_code,
            "signal": -exit_code if exit_code < 0 else None,
            "termination_reason": termination_reason,
            "termination_signal": termination_signal,
            "termination_forced": termination_forced,
            "process_id": process_id,
            "process_group_id": process_id,
            "process_group_clean": process_group_clean is True,
            "orphan_processes": UNKNOWN if self._orphan_processes is None else self._orphan_processes,
            "stderr_sha256": "sha256:" + self._stderr_digest.hexdigest(),
            "stderr_bytes": self._stderr_bytes,
            "argv_digest": _sha256_json(list(command)),
            "shell": False,
            "start_new_session": True,
        }

    def _stop_process(self, *, reason: Optional[str] = None, code: Optional[str] = None) -> None:
        with self._state_lock:
            process = self.process
            if process is None:
                return
            if reason is not None and self._termination_reason is None:
                self._termination_reason = reason
            if code is not None and self._termination_code is None:
                self._termination_code = code
            pid = process.pid
        try:
            if process.poll() is None:
                returncode, forced_kill = terminate_process(
                    process,
                    term_timeout=DEFAULT_PROCESS_STOP_TIMEOUT,
                    kill_timeout=DEFAULT_PROCESS_STOP_TIMEOUT,
                )
                with self._state_lock:
                    if self._termination_signal is None:
                        self._termination_signal = signal.SIGTERM
                    if forced_kill:
                        self._termination_signal = signal.SIGKILL
                        self._termination_forced = True
            else:
                returncode = process.returncode
            # Snapshot orphans while the leader is still alive so the
            # parent->child chain is intact; setsid-escaped children acquire a
            # different session id and survive killpg on the parent group.
            orphans = detect_orphan_processes(pid)
            # _ensure_process_group_clean is the authoritative source of truth
            # for process_group_clean; it re-checks the group and may SIGKILL
            # stragglers, then sweeps setsid-escaped orphans, never reporting
            # an un-reaped leader (or orphan) as clean.
            self._ensure_process_group_clean(pid, orphans)
            if returncode is not None and self._active_command is not None:
                self._last_exit_receipt = self._exit_receipt(returncode, self._active_command)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        finally:
            with self._state_lock:
                self.process = None
                self._active_command = None

    def _ensure_process_group_clean(
        self, process_group_id: int, orphans: Optional[List[int]] = None
    ) -> bool:
        clean = self._wait_for_process_group_exit(process_group_id, 0.25)
        if not clean:
            with self._state_lock:
                self._termination_signal = signal.SIGKILL
                self._termination_forced = True
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                # Group already reaped; nothing to clean.
                pass
            except PermissionError:
                # Cannot signal the group: cleanup is unverifiable.  Leave the
                # verdict as not-clean so the terminal boundary fail-stops
                # instead of silently declaring a clean termination.
                with self._state_lock:
                    self._process_group_clean = None
                    self._orphan_processes = None
                return False
            except OSError as exc:
                # Any other OS error during escalation is unhandleable ->
                # fail-stop, not a silent swallow.
                raise FailStopError(
                    f"Process group {process_group_id} cleanup escalation failed: {exc}",
                    code="process_group_cleanup_failed",
                ) from exc
            clean = self._wait_for_process_group_exit(process_group_id, DEFAULT_PROCESS_STOP_TIMEOUT)
        # Orphan sweep: setsid-escaped descendants survive killpg and must be
        # reaped explicitly.  ``None`` means enumeration was unsupported ->
        # fail-closed to UNKNOWN rather than a false zero.
        if orphans is None:
            orphan_count: Optional[int] = None
        else:
            for orphan_pid in orphans:
                try:
                    os.kill(orphan_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    raise FailStopError(
                        f"Orphan cleanup failed for pid {orphan_pid}: {exc}",
                        code="orphan_cleanup_failed",
                    ) from exc
            orphan_count = len(orphans)
            if orphan_count > 0:
                clean = False
        with self._state_lock:
            self._process_group_clean = clean
            self._orphan_processes = orphan_count
        return clean

    @staticmethod
    def _wait_for_process_group_exit(process_group_id: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                os.killpg(process_group_id, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _validate_provider(self) -> None:
        endpoint = urlsplit(self.provider_identity.endpoint)
        if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("H2 Provider endpoint must be loopback")
        if self.provider_identity.transport != TRANSPORT_LOOPBACK_ONLY:
            raise ValueError("H2 Provider transport must be loopback-only")

    @staticmethod
    def _resolve_executable(executable: os.PathLike[str] | str) -> Path:
        path = Path(executable).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Worker executable not found: {executable}")
        return path

    @staticmethod
    def _require_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError(f"{name} must be a non-empty NUL-free string")
        return value

    @classmethod
    def _require_arg(cls, value: str) -> str:
        return cls._require_text(value, "worker_arg")


def _is_sha256(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(character in "0123456789abcdef" for character in value[7:])


def _iter_all_processes() -> Optional[List[Tuple[int, int, int, int]]]:
    """Snapshot ``(pid, ppid, pgid, sid)`` for every process on the host.

    Returns ``None`` when process enumeration is unavailable (no ``ps`` binary
    or an unsupported column set).  Callers must treat ``None`` as "orphan
    detection unsupported" and fall back to the fail-closed ``UNKNOWN`` caliber
    rather than assuming zero orphans.
    """

    try:
        completed = subprocess.run(
            ["ps", "-o", "pid=", "-o", "ppid=", "-o", "pgid=", "-o", "sess=", "-ax"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    rows: List[Tuple[int, int, int, int]] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        try:
            rows.append((int(fields[0]), int(fields[1]), int(fields[2]), int(fields[3])))
        except ValueError:
            continue
    return rows


def _collect_descendants(root_pid: int, tree: List[Tuple[int, int, int, int]]) -> List[int]:
    children: Dict[int, List[int]] = {}
    for pid, ppid, _pgid, _sid in tree:
        children.setdefault(ppid, []).append(pid)
    seen: set[int] = set()
    stack = [root_pid]
    while stack:
        current = stack.pop()
        for child in children.get(current, ()):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return [pid for pid in seen if pid != root_pid]


def _find_orphans_in_tree(
    root_pid: int, tree: List[Tuple[int, int, int, int]]
) -> List[int]:
    """Pure orphan filter over a ``(pid, ppid, pgid, sid)`` snapshot.

    Returns descendant pids of ``root_pid`` whose session id differs from the
    root's session id -- i.e. processes that escaped the parent group via
    ``os.setsid()`` and survive ``os.killpg``.  The root itself is never
    reported.  If the root is absent from the snapshot (already exited) the
    result is empty; callers that need to distinguish "unsupported" from "no
    orphans" must check the source snapshot separately.
    """

    sid_by_pid = {pid: sid for pid, _ppid, _pgid, sid in tree}
    root_sid = sid_by_pid.get(root_pid)
    if root_sid is None:
        return []
    return [pid for pid in _collect_descendants(root_pid, tree) if sid_by_pid.get(pid) != root_sid]


def detect_orphan_processes(root_pid: int) -> Optional[List[int]]:
    """Return descendant pids of ``root_pid`` that escaped its session via setsid.

    A child that calls ``os.setsid()`` becomes its own session leader (a new
    session id) and therefore escapes ``os.killpg`` aimed at the parent process
    group.  Those processes are orphans: still alive after the parent group is
    torn down, but no longer reachable by a group signal.

    Must be called while ``root_pid`` is still alive so the parent->child chain
    is intact.  Returns ``None`` when process enumeration is unsupported or the
    root has already exited (caller records ``UNKNOWN`` instead of a false
    zero).
    """

    tree = _iter_all_processes()
    if tree is None:
        return None
    if not any(pid == root_pid for pid, _ppid, _pgid, _sid in tree):
        return None
    return _find_orphans_in_tree(root_pid, tree)


__all__ = [
    "WORKER_BRIDGE_SCHEMA",
    "WorkerBridge",
    "WorkerBridgeError",
    "WorkerCodingResult",
    "WorkerHandshakeResult",
    "detect_orphan_processes",
]
