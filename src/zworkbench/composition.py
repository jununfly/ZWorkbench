"""A small, durable composition owner for ZWorkbench.

The owner is deliberately harness-neutral.  It owns the durable identity and
policy ledger around an execution, while a Harness adapter (Codex for the
current adoption route) remains responsible for model/tool execution.

The public interface is intentionally small:

* run lifecycle: ``create_run``, ``start_run``, ``complete_run`` and
  ``safe_stop_run``;
* approval/effect seam: ``request_approval``, ``approve`` and
  ``claim_effect``;
* uncertainty handling: ``mark_effect_uncertain`` and ``reconcile_effect``;
* evidence and portability: ``events``, ``snapshot``, ``export_state``,
  ``backup`` and ``restore``.

No method in this module executes a shell command, calls a Provider, or sends
an external side effect.  A caller must claim an effect before executing it
and must then report completion or uncertainty through this owner.
"""

from __future__ import annotations

import contextlib
import datetime as _datetime
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Iterator, List, Mapping, Optional, Sequence

from .resident_service_registry import ResidentServiceRegistry


SCHEMA = "zworkbench-composition-owner/v1"
SCHEMA_VERSION = 3

# Secret-shaped values that must never be persisted in owner evidence.
_SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,})")
ALLOWED_EFFECT_CLASSES = frozenset({"read-only", "idempotent", "approval-required"})
REPLAY_MODES = frozenset({"recorded_view", "simulated_replay", "live_replay"})

# Evidence source classification (docs/methods/README.md). Every owner-persisted
# observation must declare where the observed behaviour came from so the owner
# can tell native runtime behaviour apart from plugin-composed or outer-composed
# behaviour. This is the Q4 owner-backed source classification (ta-evidence-replay.md).
EVIDENCE_SOURCE_NATIVE = "native"
EVIDENCE_SOURCE_PLUGIN_COMPOSED = "plugin-composed"
EVIDENCE_SOURCE_OUTER_COMPOSED = "outer-composed"
EVIDENCE_SOURCES = frozenset(
    {EVIDENCE_SOURCE_NATIVE, EVIDENCE_SOURCE_PLUGIN_COMPOSED, EVIDENCE_SOURCE_OUTER_COMPOSED}
)
RUN_STATES = frozenset(
    {"created", "running", "waiting_approval", "recovering", "completed", "failed", "safe_stopped"}
)
EFFECT_STATES = frozenset({"claimed", "completed", "uncertain", "retryable", "unknown"})

_HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")


class CompositionError(Exception):
    """Base error for the composition owner."""


class NotFoundError(CompositionError):
    """A referenced owner object does not exist."""


class InvalidTransition(CompositionError):
    """A requested lifecycle transition is not safe or supported."""


class PolicyDenied(CompositionError):
    """Reserved for callers that opt into exception-based policy handling."""


class ApprovalError(CompositionError):
    """An approval cannot be created, decided, or consumed."""


class RetryBudgetExhausted(CompositionError):
    """A Provider's declared retry budget has no remaining allowance."""


class ProviderAccessDenied(CompositionError):
    """A real Provider was requested without the controlled access gate enabled.

    The baseline path (loopback / fake) must never silently reach a real
    Provider.  When a run config selects an explicit real Provider profile but
    ``real_provider_gate`` is not enabled, the Host Capability Facade refuses to
    produce an adapter; the preflight layer denies admission with the same
    semantics so the orchestrator returns a clean ``denied`` result.
    """


class IntegrityError(CompositionError):
    """A backup or restored database failed integrity validation."""


@dataclass(frozen=True)
class EffectClaim:
    """The owner's decision about whether an effect may be executed."""

    effect_id: Optional[str]
    status: str
    attempt: int
    physical_effect_count: int
    reason: str

    @property
    def executable(self) -> bool:
        """Whether the caller may perform exactly one physical attempt."""

        return self.status == "claimed"


class CompositionOwner:
    """The single durable owner for ZWorkbench composition state.

    The SQLite file is the source of truth.  The class is safe to reopen from
    another process, and every state-changing public operation is committed in
    one ``BEGIN IMMEDIATE`` transaction.  The owner is intentionally local and
    single-process in the first slice; SQLite's locking gives deterministic
    fail-closed behaviour if another process races with it.
    """

    def __init__(self, database: os.PathLike[str] | str):
        self.database = Path(database).expanduser().resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.database),
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_schema()
        # In-process capacity guardrail for resident services (sub-07 Backlog #3).
        # Runtime state only — never persisted; a freshly opened owner gets an
        # empty registry, matching the per-session boundary.
        self.resident_registry = ResidentServiceRegistry()

    def close(self) -> None:
        """Close the owner connection."""

        if self._connection is not None:
            self._connection.close()
            self._connection = None  # type: ignore[assignment]

    def __enter__(self) -> "CompositionOwner":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        run_id: str,
        task_type: str,
        input_value: Any,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a durable run identity without starting execution."""

        self._require_text(run_id, "run_id")
        self._require_text(task_type, "task_type")
        # Run input/metadata is the harness's own run definition, not external
        # adapter evidence. The owner is the trusted raw store and projection
        # safety is enforced by the view layer (redaction), so create_run must
        # NOT reject secret-shaped values here. Value-level credential hygiene
        # stays at the true external-evidence seams: record_result/record_event,
        # record_replay_metadata, external_receipt and the provider ledgers.
        metadata_value = dict(metadata or {})
        input_json = self._canonical_json(input_value)
        metadata_json = self._canonical_json(metadata_value)
        timestamp = self._now()
        with self._transaction() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO runs(run_id, task_type, input_json, metadata_json,
                                     status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'created', ?, ?)
                    """,
                    (run_id, task_type, input_json, metadata_json, timestamp, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                raise CompositionError(f"run already exists: {run_id}") from exc
            self._append_event(connection, run_id, "run.created", {"task_type": task_type})
        return self.get_run(run_id)

    def start_run(self, run_id: str) -> Dict[str, Any]:
        """Move a newly created or recovering run into execution."""

        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            self._set_run_status(connection, row, "running", "run.started")
        return self.get_run(run_id)

    def complete_run(self, run_id: str, semantic_result: Any) -> Dict[str, Any]:
        """Complete a run only when no effect remains unresolved.

        Fail-closed guards (1-5-1): a run may not be completed while it still
        has (a) a pending approval recorded against it, or (b) an unresolved
        key-identity reference in the durable identity graph. Both conditions
        mean the run's lifecycle is not yet reconciled, so completion is
        refused and the run stays ``running`` -- mirroring the existing
        unresolved-effect rejection path. No schema change; both checks reuse
        existing tables/functions.
        """

        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            if row["status"] != "running":
                raise InvalidTransition(f"run {run_id} is not running: {row['status']}")
            pending_approvals = connection.execute(
                """
                SELECT COUNT(*) AS count FROM approvals
                WHERE run_id = ? AND status = 'pending'
                """,
                (run_id,),
            ).fetchone()["count"]
            if pending_approvals:
                raise InvalidTransition(f"run {run_id} has {pending_approvals} pending approval(s)")
            identity_violations = self.detect_identity_violations(run_id)
            if identity_violations:
                raise InvalidTransition(
                    f"run {run_id} has {len(identity_violations)} unresolved identity "
                    f"violation(s); refuse completion until reconciled"
                )
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count FROM effects
                WHERE run_id = ? AND status IN ('claimed', 'uncertain', 'retryable', 'unknown')
                """,
                (run_id,),
            ).fetchone()["count"]
            if unresolved:
                raise InvalidTransition(f"run {run_id} has {unresolved} unresolved effect(s)")
            self._record_result_tx(connection, run_id, "semantic", semantic_result, "run", EVIDENCE_SOURCE_NATIVE)
            self._set_run_status(connection, row, "completed", "run.completed")
        return self.get_run(run_id)

    def fail_run(self, run_id: str, error: Any) -> Dict[str, Any]:
        """Record a terminal failure when no uncertain effect is outstanding."""

        blocked_by_effect = False
        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count FROM effects
                WHERE run_id = ? AND status IN ('claimed', 'uncertain', 'unknown')
                """,
                (run_id,),
            ).fetchone()["count"]
            if unresolved:
                self._set_run_status(connection, row, "safe_stopped", "run.safe_stopped", {"reason": "uncertain_effect"})
                blocked_by_effect = True
            else:
                self._record_result_tx(connection, run_id, "error", error, "run", EVIDENCE_SOURCE_NATIVE)
                self._set_run_status(connection, row, "failed", "run.failed")
        if blocked_by_effect:
            raise InvalidTransition(f"run {run_id} safe-stopped because an effect is unresolved")
        return self.get_run(run_id)

    def safe_stop_run(self, run_id: str, reason: str) -> Dict[str, Any]:
        """Make a run terminal without attempting to repair unknown state."""

        self._require_text(reason, "reason")
        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            if row["status"] != "safe_stopped":
                self._set_run_status(connection, row, "safe_stopped", "run.safe_stopped", {"reason": reason})
        return self.get_run(run_id)

    def begin_recovery(self, run_id: str, reason: str) -> Dict[str, Any]:
        """Move a running Run into explicit owner-controlled recovery."""

        self._require_text(reason, "reason")
        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count FROM effects
                WHERE run_id = ? AND status IN ('claimed', 'uncertain', 'unknown')
                """,
                (run_id,),
            ).fetchone()["count"]
            if unresolved:
                raise InvalidTransition(f"run {run_id} cannot recover with unresolved effect(s)")
            if row["status"] == "recovering":
                return self.get_run(run_id)
            self._set_run_status(connection, row, "recovering", "run.recovering", {"reason": reason})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """Read one run and its durable result/effect summary."""

        connection = self._require_connection()
        row = self._run_row(connection, run_id)
        result = self._decode_row(row, {"input_json": "input", "metadata_json": "metadata"})
        result["effects"] = [self._decode_row(item, {"external_receipt_json": "external_receipt"}) for item in connection.execute(
            "SELECT * FROM effects WHERE run_id = ? ORDER BY created_at, effect_id", (run_id,)
        ).fetchall()]
        result["results"] = [self._decode_row(item, {"value_json": "value"}) for item in connection.execute(
            "SELECT * FROM results WHERE run_id = ? ORDER BY created_at, result_id", (run_id,)
        ).fetchall()]
        return result

    # ------------------------------------------------------------------
    # Approval and effect seam
    # ------------------------------------------------------------------

    def request_approval(
        self,
        run_id: str,
        operation_id: str,
        action: str,
        resource: str,
        idempotency_key: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Create a pending approval request; no token is persisted in plaintext."""

        for value, label in (
            (operation_id, "operation_id"),
            (action, "action"),
            (resource, "resource"),
            (idempotency_key, "idempotency_key"),
            (reason, "reason"),
        ):
            self._require_text(value, label)
        timestamp = self._now()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            existing = connection.execute(
                "SELECT * FROM approvals WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if existing:
                if existing["run_id"] != run_id:
                    raise ApprovalError("approval operation belongs to another run")
                if not self._approval_scope_matches(existing, action, resource, idempotency_key):
                    raise ApprovalError("approval operation scope conflict")
                return self._decode_row(existing, {})
            approval_id = self._new_id()
            try:
                connection.execute(
                    """
                    INSERT INTO approvals(
                        approval_id, run_id, operation_id, action, resource,
                        idempotency_key, reason, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (approval_id, run_id, operation_id, action, resource, idempotency_key, reason, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                raise ApprovalError("approval conflicts with an existing operation or idempotency key") from exc
            self._append_event(
                connection,
                run_id,
                "approval.requested",
                {
                    "approval_id": approval_id,
                    "operation_id": operation_id,
                    "action": action,
                    "resource": resource,
                    "idempotency_key": idempotency_key,
                },
            )
            return self._decode_row(connection.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone(), {})

    def approve(self, approval_id: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        """Approve one exact operation and return a one-use bearer token."""

        if ttl_seconds <= 0:
            raise ApprovalError("ttl_seconds must be positive")
        token = secrets.token_urlsafe(32)
        token_hash = self._sha256(token.encode("utf-8"))
        timestamp = self._now()
        expires_at = (
            _datetime.datetime.now(_datetime.timezone.utc) + _datetime.timedelta(seconds=ttl_seconds)
        ).isoformat(timespec="milliseconds")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"approval not found: {approval_id}")
            if row["status"] != "pending":
                raise ApprovalError(f"approval is not pending: {row['status']}")
            connection.execute(
                """
                UPDATE approvals
                SET status = 'approved', token_hash = ?, expires_at = ?, decided_at = ?
                WHERE approval_id = ?
                """,
                (token_hash, expires_at, timestamp, approval_id),
            )
            self._append_event(
                connection,
                row["run_id"],
                "approval.approved",
                {"approval_id": approval_id, "operation_id": row["operation_id"], "expires_at": expires_at},
            )
        return {
            "approval_id": approval_id,
            "operation_id": row["operation_id"],
            "token": token,
            "expires_at": expires_at,
        }

    def deny_approval(self, approval_id: str, reason: str) -> Dict[str, Any]:
        """Deny a pending request; a denied request can never be approved later."""

        self._require_text(reason, "reason")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"approval not found: {approval_id}")
            if row["status"] != "pending":
                raise ApprovalError(f"approval is not pending: {row['status']}")
            timestamp = self._now()
            connection.execute(
                "UPDATE approvals SET status = 'denied', decided_at = ?, decision_reason = ? WHERE approval_id = ?",
                (timestamp, reason, approval_id),
            )
            self._append_event(
                connection,
                row["run_id"],
                "approval.denied",
                {"approval_id": approval_id, "operation_id": row["operation_id"], "reason": reason},
            )
            return self._decode_row(connection.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone(), {})

    def claim_effect(
        self,
        run_id: str,
        operation_id: str,
        action: str,
        resource: str,
        idempotency_key: str,
        effect_class: str,
        approval_token: Optional[str] = None,
        max_attempts: int = 2,
        required_exposure: Optional[Iterable[str]] = None,
    ) -> EffectClaim:
        """Claim one effect or return a durable fail-closed decision.

        ``read-only`` and ``idempotent`` are the only classes that can be
        claimed without an approval token.  ``approval-required`` needs an
        exact, unexpired, one-use token tied to the same operation, action,
        resource and idempotency key.  Unknown classes, mismatches, replays and
        uncertain effects never become executable.
        """

        self._validate_effect_inputs(operation_id, action, resource, idempotency_key, effect_class, max_attempts)
        now = self._now()
        with self._transaction() as connection:
            run = self._run_row(connection, run_id)
            if run["status"] in {"completed", "failed", "safe_stopped"}:
                return EffectClaim(None, "denied", 0, 0, f"run_terminal:{run['status']}")

            existing = connection.execute(
                """
                SELECT * FROM effects
                WHERE operation_id = ? OR idempotency_key = ?
                ORDER BY created_at LIMIT 1
                """,
                (operation_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["run_id"] != run_id:
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "effect_belongs_to_other_run"})
                    self._append_event(
                        connection,
                        run_id,
                        "effect.claim.denied",
                        {"operation_id": operation_id, "reason": "effect_belongs_to_other_run", "existing_effect_id": existing["effect_id"]},
                    )
                    return EffectClaim(existing["effect_id"], "denied", existing["attempt"], existing["physical_effect_count"], "effect_belongs_to_other_run")
                if not self._effect_scope_matches(existing, operation_id, action, resource, idempotency_key, effect_class):
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "effect_scope_mismatch"})
                    self._append_event(
                        connection,
                        run_id,
                        "effect.claim.denied",
                        {"operation_id": operation_id, "reason": "effect_scope_mismatch", "existing_effect_id": existing["effect_id"]},
                    )
                    return EffectClaim(existing["effect_id"], "denied", existing["attempt"], existing["physical_effect_count"], "effect_scope_mismatch")
                status = existing["status"]
                if status == "completed":
                    return EffectClaim(existing["effect_id"], "already_completed", existing["attempt"], existing["physical_effect_count"], "idempotent_replay")
                if status == "claimed":
                    return EffectClaim(existing["effect_id"], "in_flight", existing["attempt"], existing["physical_effect_count"], "attempt_already_claimed")
                if status in {"uncertain", "unknown"}:
                    return EffectClaim(existing["effect_id"], "recovery_required", existing["attempt"], existing["physical_effect_count"], f"effect_{status}")
                if status == "retryable":
                    if existing["attempt"] >= existing["max_attempts"]:
                        self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "retry_budget_exhausted"})
                        return EffectClaim(existing["effect_id"], "safe_stopped", existing["attempt"], existing["physical_effect_count"], "retry_budget_exhausted")
                    next_attempt = existing["attempt"] + 1
                    connection.execute(
                        "UPDATE effects SET status = 'claimed', attempt = ?, updated_at = ? WHERE effect_id = ?",
                        (next_attempt, now, existing["effect_id"]),
                    )
                    connection.execute(
                        """
                        INSERT INTO effect_attempts(effect_id, attempt, status, started_at)
                        VALUES (?, ?, 'claimed', ?)
                        """,
                        (existing["effect_id"], next_attempt, now),
                    )
                    self._set_run_status(connection, run, "running", "run.resumed")
                    self._append_event(connection, run_id, "effect.claimed", {"effect_id": existing["effect_id"], "attempt": next_attempt, "retry": True})
                    return EffectClaim(existing["effect_id"], "claimed", next_attempt, existing["physical_effect_count"], "bounded_retry")

            # Q4 preflight-class deny: enforce the run's declared exposure
            # boundary, but only when one was recorded at preflight.  Absence
            # of a declaration preserves legacy behaviour (the declaration is
            # opt-in).  Fail-closed: any breach safe-stops the run.
            declared = self._declared_exposure_row(connection, run_id)
            if declared is not None:
                declared_classes = set(json.loads(declared["declared_side_effects_json"]))
                if effect_class not in declared_classes:
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "side_effect_not_declared"})
                    self._append_event(
                        connection,
                        run_id,
                        "effect.claim.denied",
                        {"operation_id": operation_id, "effect_class": effect_class, "reason": "side_effect_not_declared"},
                    )
                    return EffectClaim(None, "denied", 0, 0, "side_effect_not_declared")
                exposure = json.loads(declared["exposure_json"])
                workspace_root = exposure.get("workspace_root")
                if workspace_root:
                    resolved_resource = Path(resource).expanduser().resolve()
                    resolved_root = Path(workspace_root).expanduser().resolve()
                    if not (resolved_resource == resolved_root or resolved_resource.is_relative_to(resolved_root)):
                        self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "workspace_out_of_bounds"})
                        self._append_event(
                            connection,
                            run_id,
                            "effect.claim.denied",
                            {"operation_id": operation_id, "resource": resource, "workspace_root": workspace_root, "reason": "workspace_out_of_bounds"},
                        )
                        return EffectClaim(None, "denied", 0, 0, "workspace_out_of_bounds")
                required = set(required_exposure or ())
                for capability in ("network", "credentials", "subprocess"):
                    if capability in required and not exposure.get(capability):
                        self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "exposure_not_declared"})
                        self._append_event(
                            connection,
                            run_id,
                            "effect.claim.denied",
                            {"operation_id": operation_id, "capability": capability, "reason": "exposure_not_declared"},
                        )
                        return EffectClaim(None, "denied", 0, 0, "exposure_not_declared")

            if effect_class not in ALLOWED_EFFECT_CLASSES:
                self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "unknown_effect_class"})
                self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "unknown_effect_class"})
                return EffectClaim(None, "denied", 0, 0, "unknown_effect_class")

            approval = None
            if effect_class == "approval-required":
                approval = connection.execute("SELECT * FROM approvals WHERE operation_id = ?", (operation_id,)).fetchone()
                if approval is None or approval["status"] != "approved":
                    self._set_run_status(connection, run, "waiting_approval", "run.waiting_approval")
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_missing_or_not_approved"})
                    return EffectClaim(None, "denied", 0, 0, "approval_missing_or_not_approved")
                if not self._approval_scope_matches(approval, action, resource, idempotency_key):
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "approval_scope_mismatch"})
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_scope_mismatch"})
                    return EffectClaim(None, "denied", 0, 0, "approval_scope_mismatch")
                if not approval_token:
                    self._set_run_status(connection, run, "waiting_approval", "run.waiting_approval")
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_token_missing"})
                    return EffectClaim(None, "denied", 0, 0, "approval_token_missing")
                if approval["consumed_at"] is not None:
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "approval_token_replay"})
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_token_replay"})
                    return EffectClaim(None, "denied", 0, 0, "approval_token_replay")
                if not secrets.compare_digest(approval["token_hash"], self._sha256(approval_token.encode("utf-8"))):
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "approval_token_mismatch"})
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_token_mismatch"})
                    return EffectClaim(None, "denied", 0, 0, "approval_token_mismatch")
                if approval["expires_at"] is None or approval["expires_at"] <= now:
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "approval_expired"})
                    self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "approval_expired"})
                    return EffectClaim(None, "denied", 0, 0, "approval_expired")
                connection.execute("UPDATE approvals SET consumed_at = ?, status = 'consumed' WHERE approval_id = ?", (now, approval["approval_id"]))

            effect_id = self._new_id()
            try:
                connection.execute(
                    """
                    INSERT INTO effects(
                        effect_id, run_id, operation_id, idempotency_key,
                        effect_class, action, resource, status, attempt,
                        max_attempts, physical_effect_count, approval_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'claimed', 1, ?, 0, ?, ?, ?)
                    """,
                    (effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, max_attempts, approval["approval_id"] if approval else None, now, now),
                )
                connection.execute(
                    "INSERT INTO effect_attempts(effect_id, attempt, status, started_at) VALUES (?, 1, 'claimed', ?)",
                    (effect_id, now),
                )
            except sqlite3.IntegrityError as exc:
                # A concurrent owner won the idempotency race.  Returning a
                # non-executable result is safer than attempting the effect.
                self._append_event(connection, run_id, "effect.claim.denied", {"operation_id": operation_id, "reason": "idempotency_race"})
                return EffectClaim(None, "in_flight", 0, 0, "idempotency_race")
            self._set_run_status(connection, run, "running", "run.started")
            self._append_event(connection, run_id, "effect.claimed", {"effect_id": effect_id, "operation_id": operation_id, "attempt": 1, "effect_class": effect_class})
            return EffectClaim(effect_id, "claimed", 1, 0, "new_effect")

    def declare_exposure(
        self,
        run_id: str,
        *,
        declared_side_effects: Iterable[str],
        exposure: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Record the exposure a run is permitted to perform (Q4 preflight class).

        Idempotent upsert: re-declaring replaces the prior boundary.  The
        declaration is opt-in at preflight — ``claim_effect`` only enforces it
        when one exists for the run, so absence preserves legacy behaviour.

        ``exposure`` shape: ``{"workspace_root": <path>, "network": bool,
        "credentials": bool, "subprocess": bool}``.  ``workspace_root`` bounds
        every effect resource to that directory; the boolean flags gate the
        network/credentials/subprocess capabilities named in ``required_exposure``.
        """

        self._require_text(run_id, "run_id")
        declared_side_effects_value = sorted(set(declared_side_effects))
        exposure_value = dict(exposure or {})
        timestamp = self._now()
        with self._transaction() as connection:
            self._run_row(connection, run_id)  # validates the run exists
            connection.execute(
                """
                INSERT INTO declared_exposure(
                    run_id, declared_side_effects_json, exposure_json, declared_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    declared_side_effects_json = excluded.declared_side_effects_json,
                    exposure_json = excluded.exposure_json,
                    declared_at = excluded.declared_at
                """,
                (
                    run_id,
                    self._canonical_json(declared_side_effects_value),
                    self._canonical_json(exposure_value),
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "exposure.declared",
                {"declared_side_effects": declared_side_effects_value, "exposure": exposure_value},
            )
        return self.get_declared_exposure(run_id)

    def get_declared_exposure(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the declared exposure for a run, or ``None`` if undeclared."""

        with self._transaction() as connection:
            row = self._declared_exposure_row(connection, run_id)
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "declared_side_effects": json.loads(row["declared_side_effects_json"]),
            "exposure": json.loads(row["exposure_json"]),
            "declared_at": row["declared_at"],
        }

    def _declared_exposure_row(self, connection: sqlite3.Connection, run_id: str) -> Optional[sqlite3.Row]:
        """Read a run's declared exposure row on an existing connection."""

        return connection.execute(
            "SELECT * FROM declared_exposure WHERE run_id = ?", (run_id,)
        ).fetchone()

    def complete_effect(
        self,
        effect_id: str,
        result: Any,
        external_receipt: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Commit one physical effect and its result exactly once."""

        self._reject_raw_credentials(external_receipt or {}, "external_receipt")
        timestamp = self._now()
        with self._transaction() as connection:
            effect = self._effect_row(connection, effect_id)
            if effect["status"] == "completed":
                return self._decode_row(effect, {"external_receipt_json": "external_receipt"})
            if effect["status"] != "claimed":
                raise InvalidTransition(f"effect {effect_id} cannot complete from {effect['status']}")
            connection.execute(
                """
                UPDATE effects
                SET status = 'completed', physical_effect_count = 1,
                    external_receipt_json = ?, updated_at = ?
                WHERE effect_id = ?
                """,
                (self._canonical_json(dict(external_receipt or {})), timestamp, effect_id),
            )
            connection.execute(
                """
                UPDATE effect_attempts
                SET status = 'succeeded', finished_at = ?, result_json = ?
                WHERE effect_id = ? AND attempt = ?
                """,
                (timestamp, self._canonical_json(result), effect_id, effect["attempt"]),
            )
            self._record_result_tx(connection, effect["run_id"], "effect", result, effect_id, EVIDENCE_SOURCE_OUTER_COMPOSED)
            self._append_event(connection, effect["run_id"], "effect.completed", {"effect_id": effect_id, "attempt": effect["attempt"], "physical_effect_count": 1})
            return self._decode_row(connection.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone(), {"external_receipt_json": "external_receipt"})

    def mark_effect_uncertain(self, effect_id: str, error: Any) -> Dict[str, Any]:
        """Record that the external outcome is unknown; never retry implicitly."""

        timestamp = self._now()
        with self._transaction() as connection:
            effect = self._effect_row(connection, effect_id)
            if effect["status"] == "uncertain":
                return self._decode_row(effect, {})
            if effect["status"] != "claimed":
                raise InvalidTransition(f"effect {effect_id} cannot become uncertain from {effect['status']}")
            error_json = self._canonical_json(error)
            connection.execute(
                "UPDATE effects SET status = 'uncertain', last_error_json = ?, updated_at = ? WHERE effect_id = ?",
                (error_json, timestamp, effect_id),
            )
            connection.execute(
                "UPDATE effect_attempts SET status = 'uncertain', finished_at = ?, error_json = ? WHERE effect_id = ? AND attempt = ?",
                (timestamp, error_json, effect_id, effect["attempt"]),
            )
            run = self._run_row(connection, effect["run_id"])
            self._set_run_status(connection, run, "recovering", "run.recovering", {"effect_id": effect_id})
            self._append_event(connection, effect["run_id"], "effect.uncertain", {"effect_id": effect_id, "attempt": effect["attempt"]})
            return self._decode_row(connection.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone(), {})

    def reconcile_effect(self, effect_id: str, observed_outcome: str, evidence: Any = None) -> Dict[str, Any]:
        """Resolve uncertainty as applied, not-applied, or unknown.

        ``unknown`` is terminal and safe-stops the run.  ``not-applied`` is the
        only outcome that permits the owner's bounded retry.  ``applied``
        records one physical effect even when the original caller crashed.
        """

        if observed_outcome not in {"applied", "not-applied", "unknown"}:
            raise ValueError("observed_outcome must be applied, not-applied, or unknown")
        if observed_outcome == "applied":
            self._reject_raw_credentials(evidence or {}, "external_receipt")
        timestamp = self._now()
        with self._transaction() as connection:
            effect = self._effect_row(connection, effect_id)
            if effect["status"] == "completed":
                return self._decode_row(effect, {"external_receipt_json": "external_receipt"})
            if effect["status"] not in {"uncertain", "retryable"}:
                raise InvalidTransition(f"effect {effect_id} cannot reconcile from {effect['status']}")
            evidence_json = self._canonical_json(evidence if evidence is not None else {})
            if observed_outcome == "applied":
                new_status = "completed"
                physical_count = 1
                attempt_status = "reconciled_applied"
            elif observed_outcome == "not-applied":
                new_status = "retryable"
                physical_count = effect["physical_effect_count"]
                attempt_status = "reconciled_not_applied"
            else:
                new_status = "unknown"
                physical_count = effect["physical_effect_count"]
                attempt_status = "reconciled_unknown"
            connection.execute(
                """
                UPDATE effects
                SET status = ?, physical_effect_count = ?, last_error_json = ?,
                    external_receipt_json = CASE WHEN ? = 'applied' THEN ? ELSE external_receipt_json END,
                    updated_at = ?
                WHERE effect_id = ?
                """,
                (new_status, physical_count, evidence_json, observed_outcome, evidence_json, timestamp, effect_id),
            )
            connection.execute(
                "UPDATE effect_attempts SET status = ?, finished_at = ?, error_json = ? WHERE effect_id = ? AND attempt = ?",
                (attempt_status, timestamp, evidence_json, effect_id, effect["attempt"]),
            )
            run = self._run_row(connection, effect["run_id"])
            if observed_outcome == "unknown":
                if run["status"] != "safe_stopped":
                    self._set_run_status(connection, run, "safe_stopped", "run.safe_stopped", {"reason": "effect_outcome_unknown", "effect_id": effect_id})
            elif run["status"] != "safe_stopped":
                self._set_run_status(connection, run, "running", "run.reconciled", {"effect_id": effect_id, "outcome": observed_outcome})
            self._append_event(connection, effect["run_id"], "effect.reconciled", {"effect_id": effect_id, "outcome": observed_outcome, "physical_effect_count": physical_count})
            if observed_outcome == "applied":
                self._record_result_tx(connection, effect["run_id"], "effect", {"reconciled": True, "evidence": evidence}, effect_id, EVIDENCE_SOURCE_OUTER_COMPOSED)
            return self._decode_row(connection.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone(), {"external_receipt_json": "external_receipt"})

    # ------------------------------------------------------------------
    # F13 (1-2-5) — identity-boundary judgment and reconcile routing
    # ------------------------------------------------------------------

    def detect_identity_violations(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scan the durable identity graph for unresolved references.

        A "key identity" in this owner is any cross-reference the AGENTS.md
        long-lived constraint requires to stay queryable: the run_id link from
        every child table, the effect_attempts -> effects link, the
        effects.approval_id link, and the parent/child run links carried in
        ``runs.metadata``.  Any reference that points at a row that does not
        exist is an unresolved identity -- the boundary has been crossed.

        The scan is read-only and fail-closed: it never invents a target, it
        only reports what cannot be resolved.  Pass ``run_id`` to scope the scan
        to one run's inbound and outbound links (as the view model does); pass
        ``None`` for a whole-owner integrity audit.
        """

        connection = self._require_connection()
        valid_runs = {row["run_id"] for row in connection.execute("SELECT run_id FROM runs")}
        effect_run = {
            row["effect_id"]: row["run_id"]
            for row in connection.execute("SELECT effect_id, run_id FROM effects")
        }
        findings: List[Dict[str, Any]] = []

        child_tables = ("effects", "approvals", "results", "replays", "events", "provider_exit_ledger")
        for table in child_tables:
            for row in connection.execute(f"SELECT run_id FROM {table}"):
                child_run = row["run_id"]
                if child_run in valid_runs:
                    continue
                if run_id is not None and child_run != run_id:
                    continue
                findings.append({
                    "kind": f"orphan_{table}_run",
                    "run_id": child_run,
                    "ref_table": table,
                    "ref_id": child_run,
                    "detail": f"{table}.run_id references missing run {child_run!r}",
                })

        for row in connection.execute("SELECT effect_id FROM effect_attempts"):
            effect_id = row["effect_id"]
            owner_run = effect_run.get(effect_id)
            if owner_run is None:
                if run_id is None:
                    findings.append({
                        "kind": "orphan_effect_attempt_effect",
                        "run_id": "unknown",
                        "ref_table": "effect_attempts",
                        "ref_id": effect_id,
                        "detail": f"effect_attempts.effect_id references missing effect {effect_id!r}",
                    })
                continue
            if run_id is not None and owner_run != run_id:
                continue

        for row in connection.execute("SELECT effect_id, approval_id, run_id FROM effects WHERE approval_id IS NOT NULL"):
            approval_id = row["approval_id"]
            exists = connection.execute("SELECT 1 FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if exists:
                continue
            if run_id is not None and row["run_id"] != run_id:
                continue
            findings.append({
                "kind": "orphan_effect_approval",
                "run_id": row["run_id"],
                "ref_table": "effects",
                "ref_id": approval_id,
                "detail": f"effects.approval_id references missing approval {approval_id!r}",
            })

        for row in connection.execute("SELECT run_id, metadata_json FROM runs"):
            current_run = row["run_id"]
            if run_id is not None and current_run != run_id:
                continue
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (ValueError, TypeError):
                metadata = {}
            if not isinstance(metadata, dict):
                continue
            for link in ("parent_run_id", "child_run_id"):
                target = metadata.get(link)
                if target and target not in valid_runs:
                    findings.append({
                        "kind": f"broken_{link}",
                        "run_id": current_run,
                        "ref_table": "runs.metadata",
                        "ref_id": target,
                        "detail": f"{current_run}.metadata.{link} references missing run {target!r}",
                    })

        return findings

    def safe_stop_on_identity_violation(self, run_id: str) -> Dict[str, Any]:
        """Fail-closed boundary enforcement for the F13 (1-2-5) judgment.

        If the run's durable identity graph has an unresolved reference,
        safe-stop it with reason ``identity_unresolved`` and record the
        findings.  When the graph is clean the run is left untouched and
        ``safe_stopped`` is False -- detection alone is never a reason to
        interrupt a healthy run.
        """

        findings = self.detect_identity_violations(run_id)
        if not findings:
            return {"violations": [], "safe_stopped": False, "status": self.get_run(run_id)["status"]}
        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            if row["status"] != "safe_stopped":
                self._set_run_status(connection, row, "safe_stopped", "run.safe_stopped", {"reason": "identity_unresolved"})
            self._append_event(connection, run_id, "run.identity.violation", {"reason": "identity_unresolved", "violations": findings})
        return {"violations": findings, "safe_stopped": True, "status": "safe_stopped"}

    def reconcile_identity(self, run_id: str, evidence: Any = None) -> Dict[str, Any]:
        """Record an identity-reconciliation decision and re-check the graph.

        Mirrors ``reconcile_effect``'s fail-closed spirit: a safe-stopped run is
        terminal and is never resurrected.  If violations remain the run stays
        safe_stopped (``outcome=unknown``); if the graph is now clean the run is
        recorded as reconciled (``outcome=resolved``) but still terminal.  Either
        way the decision is durable and observable through the event ledger.

        ``evidence`` is accepted for caller symmetry but is not persisted in this
        slice: the owner rejects raw credential fields, and free-text evidence
        would need redaction before entering the ledger.
        """

        findings = self.detect_identity_violations(run_id)
        payload = {"outcome": "unknown" if findings else "resolved", "violation_count": len(findings)}
        if findings:
            payload["violations"] = findings
            with self._transaction() as connection:
                row = self._run_row(connection, run_id)
                if row["status"] != "safe_stopped":
                    self._set_run_status(connection, row, "safe_stopped", "run.safe_stopped", {"reason": "identity_unresolved"})
                self._append_event(connection, run_id, "run.identity.reconciled", payload)
            return {"outcome": "unknown", "violations": findings, "status": "safe_stopped"}
        with self._transaction() as connection:
            self._append_event(connection, run_id, "run.identity.reconciled", payload)
        return {"outcome": "resolved", "violations": [], "status": self.get_run(run_id)["status"]}

    # ------------------------------------------------------------------
    # Evidence, export and portable backup
    # ------------------------------------------------------------------

    def record_result(self, run_id: str, kind: str, value: Any, source_id: Optional[str] = None, *, evidence_source: str) -> Dict[str, Any]:
        """Append a durable semantic or adapter result.

        ``evidence_source`` is required so every owner-persisted observation is
        classified as native / plugin-composed / outer-composed. A missing or
        invalid classification is rejected (fail-closed) instead of defaulted.
        """

        self._require_text(kind, "kind")
        self._reject_raw_credentials(value, "value")
        self._validate_evidence_source(evidence_source)
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            return self._record_result_tx(connection, run_id, kind, value, source_id, evidence_source)

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        event_id: Optional[str] = None,
        *,
        evidence_source: str,
    ) -> Dict[str, Any]:
        """Append one structured adapter event without exposing SQLite.

        Adapter messages are evidence, not a second source of truth.  The
        owner therefore assigns the canonical event row and keeps the public
        seam deliberately smaller than the underlying table.  ``evidence_source``
        is required so each event is classified as native / plugin-composed /
        outer-composed.  A caller may provide a stable event id when retrying an
        already-recorded message; a conflicting reuse is rejected instead of
        being silently merged.
        """

        self._require_text(event_type, "event_type")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be an object")
        payload_value = dict(payload)
        self._reject_raw_credentials(payload_value, "payload")
        self._validate_evidence_source(evidence_source)
        if event_id is not None:
            self._require_text(event_id, "event_id")
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            if event_id is not None:
                existing = connection.execute(
                    "SELECT * FROM events WHERE event_id = ?", (event_id,)
                ).fetchone()
                if existing is not None:
                    same = (
                        existing["run_id"] == run_id
                        and existing["type"] == event_type
                        and existing["payload_json"] == self._canonical_json(payload_value)
                        and existing["evidence_source"] == evidence_source
                    )
                    if not same:
                        raise CompositionError("event_id is already bound to different event data")
                    return self._decode_row(existing, {"payload_json": "payload"})
            assigned_id = self._append_event(connection, run_id, event_type, payload_value, event_id, evidence_source)
            return self._decode_row(
                connection.execute("SELECT * FROM events WHERE event_id = ?", (assigned_id,)).fetchone(),
                {"payload_json": "payload"},
            )

    def record_replay_metadata(
        self,
        run_id: str,
        replay_id: str,
        mode: str,
        source_event_digest: str,
        environment_digest: str,
        provider_identity: Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record replay identity without executing a replay.

        The owner records all three explicit modes so a later adapter cannot
        silently turn a recorded view into live execution.  In particular,
        ``live_replay`` is metadata only here; any live execution still needs
        the effect/approval seam and remains outside this module.
        """

        for value, label in (
            (replay_id, "replay_id"),
            (source_event_digest, "source_event_digest"),
            (environment_digest, "environment_digest"),
        ):
            self._require_text(value, label)
        if mode not in REPLAY_MODES:
            raise ValueError(f"unsupported replay mode: {mode}")
        timestamp = self._now()
        if not isinstance(provider_identity, Mapping):
            raise ValueError("provider_identity must be an object")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise ValueError("metadata must be an object")
        provider_value = dict(provider_identity)
        metadata_value = dict(metadata or {})
        self._reject_raw_credentials(provider_value, "provider_identity")
        self._reject_raw_credentials(metadata_value, "metadata")
        provider_json = self._canonical_json(provider_value)
        metadata_json = self._canonical_json(metadata_value)
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            existing = connection.execute("SELECT * FROM replays WHERE replay_id = ?", (replay_id,)).fetchone()
            if existing:
                same = (
                    existing["run_id"] == run_id
                    and existing["mode"] == mode
                    and existing["source_event_digest"] == source_event_digest
                    and existing["environment_digest"] == environment_digest
                    and existing["provider_identity_json"] == provider_json
                    and existing["metadata_json"] == metadata_json
                )
                if not same:
                    raise CompositionError("replay_id is already bound to different identity")
                return self._decode_row(existing, {"provider_identity_json": "provider_identity", "metadata_json": "metadata"})
            connection.execute(
                """
                INSERT INTO replays(
                    replay_id, run_id, mode, source_event_digest,
                    environment_digest, provider_identity_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (replay_id, run_id, mode, source_event_digest, environment_digest, provider_json, metadata_json, timestamp),
            )
            self._append_event(
                connection,
                run_id,
                "replay.metadata.recorded",
                {"replay_id": replay_id, "mode": mode, "source_event_digest": source_event_digest, "environment_digest": environment_digest},
            )
            return self._decode_row(connection.execute("SELECT * FROM replays WHERE replay_id = ?", (replay_id,)).fetchone(), {"provider_identity_json": "provider_identity", "metadata_json": "metadata"})

    # ------------------------------------------------------------------
    # Provider-side exit ledger (1-6-6) — owner-owned, unknown/delegated caliber
    # ------------------------------------------------------------------

    def record_provider_exit_ledger(
        self,
        run_id: str,
        provider_identity: Mapping[str, Any],
        *,
        caliber: str = "unknown/delegated",
        local_state_fingerprint: str = "unknown",
    ) -> Dict[str, Any]:
        """Record the owner-owned provider-side exit accounting for a run.

        The default (loopback/fake) product path has no real remote provider,
        so the caliber is ``unknown/delegated`` by construction: this ledger
        never claims a remote zero-residue proof.  It records only that the run
        used the named provider, with every resource status ``unknown`` and the
        remote residue explicitly ``unknown/delegated``.  This satisfies the
        AGENTS.md constraint that the exit ledger belongs to the single durable
        owner, and keeps the default-path accounting distinct from the opt-in
        Ark inventory wizard (which remains the separate owner-authorized
        evidence flow for real providers).
        """

        self._require_text(run_id, "run_id")
        provider_identity_value = dict(provider_identity or {})
        self._reject_raw_credentials(provider_identity_value, "provider_identity")
        if local_state_fingerprint != "unknown":
            self._require_text(local_state_fingerprint, "local_state_fingerprint")
            if not _HEX64.fullmatch(local_state_fingerprint):
                raise ValueError("local_state_fingerprint must be 64-char SHA-256 hex or 'unknown'")
        provider = str(provider_identity_value.get("provider") or "unknown")
        endpoint = str(provider_identity_value.get("endpoint") or "unknown")
        statuses = {
            "task_or_run": "unknown",
            "webhook_or_integration": "unknown",
            "backup_or_snapshot": "unknown",
            "coding_data": "unknown",
            "api_key": "unknown",
            "billing": "unknown",
            "subscription": "unknown",
            "account": "unknown",
            "local_case": "unknown",
            "exit_action": "unknown",
        }
        surface_observations = {
            "task_or_run": "unknown",
            "backup_or_snapshot": "unknown",
            "retention_policy": "unknown",
        }
        unknown_fields = sorted(statuses.keys())
        timestamp = self._now()
        ledger_id = self._new_id()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            connection.execute(
                """
                INSERT INTO provider_exit_ledger(
                    ledger_id, run_id, provider, endpoint, account_scope,
                    exit_mode, exit_status, provider_remote_zero_residue,
                    surface_observations_json, statuses_json, unknown_fields_json,
                    local_state_fingerprint, evidence_class, recorded_at
                ) VALUES (?, ?, ?, ?, 'unknown', 'inventory-only', 'unknown/safe-stop',
                          'unknown/delegated', ?, ?, ?, ?, 'local-inventory', ?)
                """,
                (
                    ledger_id,
                    run_id,
                    provider,
                    endpoint,
                    self._canonical_json(surface_observations),
                    self._canonical_json(statuses),
                    self._canonical_json(unknown_fields),
                    local_state_fingerprint,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "provider.exit.ledger.recorded",
                {
                    "ledger_id": ledger_id,
                    "provider": provider,
                    "caliber": caliber,
                    "provider_remote_zero_residue": "unknown/delegated",
                },
            )
        return self.get_provider_exit_ledger(ledger_id)

    def record_provider_exit_ledger_once(
        self,
        run_id: str,
        provider_identity: Mapping[str, Any],
        *,
        caliber: str = "unknown/delegated",
        local_state_fingerprint: str = "unknown",
    ) -> Dict[str, Any]:
        """Record the Provider-side exit ledger at most once per run.

        This is the symmetric counterpart to the adapter-local exit ledger
        (e.g. ``worker.exit`` / ``dsh.exit``).  Every termination path that
        knows the real ``provider_identity`` records it at the same boundary
        where it records its local resource teardown, so the two ledgers are
        *paired* rather than written at unrelated layers.

        Idempotent: if a ledger entry already exists for ``run_id`` (recorded
        by the harness or another adapter sharing the run), the existing entry
        is returned and nothing new is appended.  This keeps the default
        append-only ``record_provider_exit_ledger`` semantics intact (the
        multi-entry journal contract is unchanged) while guaranteeing a single
        Provider-side accounting per run across the harness and adapter layers.
        """

        existing = self.provider_exit_ledger_for_run(run_id)
        if existing:
            return existing[0]
        return self.record_provider_exit_ledger(
            run_id,
            provider_identity,
            caliber=caliber,
            local_state_fingerprint=local_state_fingerprint,
        )

    def attach_provider_exit_receipt(
        self,
        run_id: str,
        receipt: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Attach an owner-supplied, redacted Provider exit receipt to a run.

        This is the C7 reconciliation seam: the opt-in Ark inventory wizard
        (``scripts/record_provider_exit_receipt.py``) produces a v2 receipt that
        an account owner recorded in the Provider console.  Attaching it
        *supplements* the default ``local-inventory`` entry with
        ``owner-backed`` evidence (receipt fingerprint + attestation), WITHOUT
        ever letting local or owner evidence upgrade to a Provider clearance.

        Fail-closed guarantees:
        - the receipt must be the v2 schema; unknown/mismatched schemas are rejected.
        - ``provider_remote_zero_residue`` MUST remain ``unknown/delegated``: a
          tampered receipt claiming remote zero residue is rejected, so a local
          exit never becomes a Provider-exit proof.
        - any secret-shaped string leaf is rejected; the owner store never ingests
          raw credentials.
        The method is append-only: a run may carry a ``local-inventory`` entry and
        one or more ``owner-backed`` entries, making the durable distinction
        "本地退出 ≠ Provider 退出" queryable.
        """

        self._require_text(run_id, "run_id")
        if not isinstance(receipt, Mapping):
            raise ValueError("receipt must be a mapping (Provider exit receipt v2)")
        schema = receipt.get("schema")
        if schema != "zworkbench-provider-exit-receipt/v2":
            raise ValueError(f"receipt schema must be zworkbench-provider-exit-receipt/v2: {schema!r}")
        remote_residue = receipt.get("provider_remote_zero_residue")
        if remote_residue != "unknown/delegated":
            raise ValueError(
                "provider_remote_zero_residue must stay 'unknown/delegated'; "
                "local/owner evidence cannot claim Provider clearance"
            )
        self._reject_secret_shaped_values(receipt, "receipt")
        provider = str(receipt.get("provider") or "unknown")
        endpoint = str(receipt.get("endpoint") or "unknown")
        account_scope = str(receipt.get("account_scope") or "unknown")
        exit_mode = str(receipt.get("exit_mode") or "authorized-manual-exit")
        exit_status = str(receipt.get("exit_status") or "unknown/safe-stop")
        local_state_fingerprint = str(receipt.get("local_state_fingerprint") or "unknown")
        surface_observations = dict(receipt.get("surface_observations") or {})
        statuses = dict(receipt.get("statuses") or {})
        unknown_fields = list(receipt.get("unknown_fields") or [])
        timestamp = self._now()
        ledger_id = self._new_id()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            connection.execute(
                """
                INSERT INTO provider_exit_ledger(
                    ledger_id, run_id, provider, endpoint, account_scope,
                    exit_mode, exit_status, provider_remote_zero_residue,
                    surface_observations_json, statuses_json, unknown_fields_json,
                    local_state_fingerprint, evidence_class, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown/delegated', ?, ?, ?, ?, 'owner-backed', ?)
                """,
                (
                    ledger_id,
                    run_id,
                    provider,
                    endpoint,
                    account_scope,
                    exit_mode,
                    exit_status,
                    self._canonical_json(surface_observations),
                    self._canonical_json(statuses),
                    self._canonical_json(unknown_fields),
                    local_state_fingerprint,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "provider.exit.ledger.recorded",
                {
                    "ledger_id": ledger_id,
                    "provider": provider,
                    "evidence_class": "owner-backed",
                    "evidence_fingerprint": str(receipt.get("evidence_fingerprint") or "unknown"),
                    "provider_remote_zero_residue": "unknown/delegated",
                },
            )
        return self.get_provider_exit_ledger(ledger_id)

    def get_provider_exit_ledger(self, ledger_id: str) -> Dict[str, Any]:
        """Read one provider-exit ledger entry by id."""

        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM provider_exit_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider exit ledger entry not found: {ledger_id}")
        return self._decode_row(
            row,
            {
                "surface_observations_json": "surface_observations",
                "statuses_json": "statuses",
                "unknown_fields_json": "unknown_fields",
            },
        )

    def provider_exit_ledger_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Return all provider-exit ledger entries for a run, in recorded order."""

        connection = self._require_connection()
        self._run_row(connection, run_id)
        rows = connection.execute(
            "SELECT * FROM provider_exit_ledger WHERE run_id = ? ORDER BY recorded_at, ledger_id",
            (run_id,),
        ).fetchall()
        return [
            self._decode_row(
                row,
                {
                    "surface_observations_json": "surface_observations",
                    "statuses_json": "statuses",
                    "unknown_fields_json": "unknown_fields",
                },
            )
            for row in rows
        ]

    def record_provider_fallback(
        self,
        run_id: str,
        *,
        from_provider: Optional[str],
        to_provider: Optional[str],
        reason: str,
        degradation_mode: str,
        attempt: int,
        failure_code: Optional[str] = None,
        http_status: Optional[int] = None,
        local_state_fingerprint: str = "unknown",
    ) -> Dict[str, Any]:
        """Record an owner-owned Provider fallback / degradation decision.

        This is the first-class, auditable home for fallback accounting that the
        Provider adaptation layer previously kept only inside fixture-level
        events and generic results (node 1-1-1).  Every fallback or safe-stop
        decision must carry an explicit ``reason``; a missing / empty reason is
        rejected (reason-required fail-closed) because a silent degradation must
        never enter the single durable owner.
        """

        self._require_text(run_id, "run_id")
        if from_provider is not None:
            self._require_text(from_provider, "from_provider")
        if to_provider is not None:
            self._require_text(to_provider, "to_provider")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string (fallback without reason is rejected)")
        if degradation_mode not in ("fallback", "safe_stop"):
            raise ValueError("degradation_mode must be 'fallback' or 'safe_stop'")
        if not isinstance(attempt, int) or attempt < 0:
            raise ValueError("attempt must be a non-negative integer")
        if failure_code is not None:
            self._require_text(failure_code, "failure_code")
        if http_status is not None and not isinstance(http_status, int):
            raise ValueError("http_status must be an integer or None")
        if local_state_fingerprint != "unknown":
            self._require_text(local_state_fingerprint, "local_state_fingerprint")
            if not _HEX64.fullmatch(local_state_fingerprint):
                raise ValueError("local_state_fingerprint must be 64-char SHA-256 hex or 'unknown'")
        self._reject_raw_credentials(
            {
                "from_provider": from_provider,
                "to_provider": to_provider,
                "reason": reason,
                "failure_code": failure_code,
            },
            "provider fallback decision",
        )
        timestamp = self._now()
        ledger_id = self._new_id()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            connection.execute(
                """
                INSERT INTO provider_fallback_ledger(
                    ledger_id, run_id, from_provider, to_provider, reason,
                    degradation_mode, attempt, failure_code, http_status,
                    local_state_fingerprint, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    run_id,
                    from_provider,
                    to_provider,
                    reason,
                    degradation_mode,
                    attempt,
                    failure_code,
                    http_status,
                    local_state_fingerprint,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "provider.fallback.ledger.recorded",
                {
                    "ledger_id": ledger_id,
                    "from_provider": from_provider,
                    "to_provider": to_provider,
                    "reason": reason,
                    "degradation_mode": degradation_mode,
                    "attempt": attempt,
                },
            )
        return self.get_provider_fallback_ledger(ledger_id)

    def get_provider_fallback_ledger(self, ledger_id: str) -> Dict[str, Any]:
        """Read one provider-fallback ledger entry by id."""

        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM provider_fallback_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider fallback ledger entry not found: {ledger_id}")
        return self._decode_row(row, {})

    def provider_fallback_ledger_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Return all provider-fallback ledger entries for a run, in recorded order."""

        connection = self._require_connection()
        self._run_row(connection, run_id)
        rows = connection.execute(
            "SELECT * FROM provider_fallback_ledger WHERE run_id = ? ORDER BY recorded_at, attempt, ledger_id",
            (run_id,),
        ).fetchall()
        return [self._decode_row(row, {}) for row in rows]

    def record_provider_attempt(
        self,
        run_id: str,
        *,
        provider_id: str,
        request_id: str,
        attempt_number: int,
        status: str,
        failure_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record one owner-owned Provider retry attempt (terminal outcome only).

        This is the first-class, auditable home for attempt accounting that the
        Provider adaptation layer previously kept only inside fixture-level
        ``provider.attempt`` events and the router's in-memory ``attempts`` list
        (node 1-1-2).  Each dispatched attempt ends in a terminal ``status`` of
        ``"failed"`` or ``"succeeded"``; the live ``"started"`` observation stays
        in the generic event stream and is intentionally not duplicated here so
        the ledger counts attempts exactly once.  A single durable owner lets a
        downstream Provider-level retry budget (node 1-1-3) count and bound
        attempts per provider per run instead of trusting transient fixture state.
        """

        self._require_text(run_id, "run_id")
        self._require_text(provider_id, "provider_id")
        self._require_text(request_id, "request_id")
        if not isinstance(attempt_number, int) or attempt_number < 1:
            raise ValueError("attempt_number must be a positive integer")
        if status not in ("failed", "succeeded"):
            raise ValueError("status must be 'failed' or 'succeeded'")
        if failure_code is not None:
            self._require_text(failure_code, "failure_code")
        self._reject_raw_credentials(
            {"provider_id": provider_id, "request_id": request_id, "failure_code": failure_code},
            "provider attempt",
        )
        timestamp = self._now()
        ledger_id = self._new_id()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            connection.execute(
                """
                INSERT INTO provider_attempt_ledger(
                    ledger_id, run_id, provider_id, request_id, attempt_number,
                    status, failure_code, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    run_id,
                    provider_id,
                    request_id,
                    attempt_number,
                    status,
                    failure_code,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "provider.attempt.ledger.recorded",
                {
                    "ledger_id": ledger_id,
                    "provider_id": provider_id,
                    "request_id": request_id,
                    "attempt_number": attempt_number,
                    "status": status,
                    "failure_code": failure_code,
                },
            )
        return self.get_provider_attempt_ledger(ledger_id)

    def get_provider_attempt_ledger(self, ledger_id: str) -> Dict[str, Any]:
        """Read one provider-attempt ledger entry by id."""

        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM provider_attempt_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider attempt ledger entry not found: {ledger_id}")
        return self._decode_row(row, {})

    def provider_attempt_ledger_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Return all provider-attempt ledger entries for a run, in attempt order."""

        connection = self._require_connection()
        self._run_row(connection, run_id)
        rows = connection.execute(
            "SELECT * FROM provider_attempt_ledger WHERE run_id = ? ORDER BY attempt_number, ledger_id",
            (run_id,),
        ).fetchall()
        return [self._decode_row(row, {}) for row in rows]

    # -- Provider-level retry budget (node 1-1-3) --------------------------
    #
    # The attempt ledger (node 1-1-2) counts every dispatched terminal attempt.
    # The retry budget layer closes the UNKNOWN gap the adaptation doc flagged:
    # a Provider-level retry *ceiling* owned by the single durable owner, plus a
    # consumption ledger that records each cross-Provider retry with its
    # attempt / failure_class / target / reason.  A declared budget is enforced
    # fail-closed; an undeclared Provider still has its retry recorded (bound=
    # 'undeclared') so the absence of a ceiling is an auditable signal rather
    # than silent state.

    def declare_provider_retry_budget(
        self,
        provider_id: str,
        *,
        max_retries: int,
        declared_by: str,
    ) -> Dict[str, Any]:
        """Declare or replace the owner-owned retry ceiling for a Provider.

        ``max_retries`` is the upper bound on cross-Provider retries attributed
        to ``provider_id`` within a single run.  ``declared_by`` captures the
        provenance of the ceiling (the entity that owns/establishes it).
        """

        self._require_text(provider_id, "provider_id")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self._require_text(declared_by, "declared_by")
        self._reject_raw_credentials(
            {"provider_id": provider_id, "declared_by": declared_by},
            "provider retry budget declaration",
        )
        timestamp = self._now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO provider_retry_budget(provider_id, max_retries, declared_by, declared_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    max_retries = excluded.max_retries,
                    declared_by = excluded.declared_by,
                    declared_at = excluded.declared_at
                """,
                (provider_id, max_retries, declared_by, timestamp),
            )
        return self.get_provider_retry_budget(provider_id)

    def get_provider_retry_budget(self, provider_id: str) -> Dict[str, Any]:
        """Read one declared Provider retry budget by provider id."""

        connection = self._require_connection()
        self._require_text(provider_id, "provider_id")
        row = connection.execute(
            "SELECT * FROM provider_retry_budget WHERE provider_id = ?", (provider_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider retry budget not declared: {provider_id}")
        return self._decode_row(row, {})

    def provider_retry_budgets(self) -> List[Dict[str, Any]]:
        """Return all declared Provider retry budgets."""

        connection = self._require_connection()
        rows = connection.execute("SELECT * FROM provider_retry_budget ORDER BY provider_id").fetchall()
        return [self._decode_row(row, {}) for row in rows]

    def record_provider_retry_budget_consumption(
        self,
        run_id: str,
        *,
        provider_id: str,
        request_id: str,
        attempt_number: int,
        failure_class: str,
        target: Optional[str],
        reason: str,
    ) -> Dict[str, Any]:
        """Record one cross-Provider retry consumption and enforce the ceiling.

        The attempt/failure_class/target/reason are captured for every
        cross-Provider retry regardless of whether a budget is declared.  When a
        budget is declared for ``provider_id`` the consumption is bounded: if the
        count for ``(run_id, provider_id)`` would exceed ``max_retries`` the call
        raises ``RetryBudgetExhausted`` (fail-closed) and writes nothing.  When no
        budget is declared the consumption is still recorded with ``bound=
        'undeclared'`` so the missing ceiling is auditable rather than silent.
        """

        self._require_text(run_id, "run_id")
        self._require_text(provider_id, "provider_id")
        self._require_text(request_id, "request_id")
        if not isinstance(attempt_number, int) or attempt_number < 1:
            raise ValueError("attempt_number must be a positive integer")
        self._require_text(failure_class, "failure_class")
        if target is not None:
            self._require_text(target, "target")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string (retry without reason is rejected)")
        self._reject_raw_credentials(
            {
                "provider_id": provider_id,
                "request_id": request_id,
                "failure_class": failure_class,
                "target": target,
                "reason": reason,
            },
            "provider retry budget consumption",
        )
        timestamp = self._now()
        ledger_id = self._new_id()
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            budget = connection.execute(
                "SELECT * FROM provider_retry_budget WHERE provider_id = ?", (provider_id,)
            ).fetchone()
            if budget is None:
                bound = "undeclared"
            else:
                prior = connection.execute(
                    "SELECT COUNT(*) AS n FROM provider_retry_budget_ledger WHERE run_id = ? AND provider_id = ?",
                    (run_id, provider_id),
                ).fetchone()["n"]
                if prior + 1 > budget["max_retries"]:
                    raise RetryBudgetExhausted(
                        f"provider {provider_id} retry budget exhausted for run {run_id} "
                        f"(max_retries={budget['max_retries']}, attempted={prior + 1})"
                    )
                bound = "enforced"
            connection.execute(
                """
                INSERT INTO provider_retry_budget_ledger(
                    ledger_id, run_id, provider_id, request_id, attempt_number,
                    failure_class, target, reason, bound, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    run_id,
                    provider_id,
                    request_id,
                    attempt_number,
                    failure_class,
                    target,
                    reason,
                    bound,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "provider.retry_budget.consumption.recorded",
                {
                    "ledger_id": ledger_id,
                    "provider_id": provider_id,
                    "request_id": request_id,
                    "attempt_number": attempt_number,
                    "failure_class": failure_class,
                    "target": target,
                    "reason": reason,
                    "bound": bound,
                },
            )
        return self.get_provider_retry_budget_ledger(ledger_id)

    def get_provider_retry_budget_ledger(self, ledger_id: str) -> Dict[str, Any]:
        """Read one retry-budget consumption entry by id."""

        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM provider_retry_budget_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider retry budget ledger entry not found: {ledger_id}")
        return self._decode_row(row, {})

    def provider_retry_budget_ledger_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Return all retry-budget consumption entries for a run, in attempt order."""

        connection = self._require_connection()
        self._run_row(connection, run_id)
        rows = connection.execute(
            "SELECT * FROM provider_retry_budget_ledger WHERE run_id = ? ORDER BY attempt_number, ledger_id",
            (run_id,),
        ).fetchall()
        return [self._decode_row(row, {}) for row in rows]

    # -- Provider access gate (node 1-1-4) ---------------------------------
    #
    # The single controlled boundary that decides whether a run reaches a real
    # Provider or stays on the loopback / fake baseline.  The facade refuses to
    # produce an adapter (and preflight denies admission) whenever a real
    # Provider profile is selected without ``real_provider_gate`` enabled; the
    # orchestrator records the decision here so every run's classification is
    # auditable (which runs engaged real routing / billing vs stayed baseline).
    def record_provider_access_gate(
        self,
        run_id: str,
        classification: str,
        gate_enabled: bool,
        reason: str,
        provider_id: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> str:
        """Record one Provider-access gate decision for a run.

        ``classification`` is ``"real"`` (an explicit real Provider profile was
        selected and gated) or ``"baseline"`` (loopback / fake, no real
        profile).  ``reason`` must be non-empty: a missing or blank reason is a
        fail-closed programming error, never a silent default.
        """

        self._require_text(run_id, "run_id")
        if classification not in ("real", "baseline"):
            raise ValueError("classification must be 'real' or 'baseline'")
        if not reason or not reason.strip():
            raise ValueError("provider access gate reason must be non-empty")
        connection = self._require_connection()
        self._run_row(connection, run_id)
        ledger_id = secrets.token_hex(16)
        timestamp = self._now()
        connection.execute(
            """
            INSERT INTO provider_access_gate_ledger(
                ledger_id, run_id, classification, gate_enabled, reason,
                provider_id, profile_name, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_id,
                run_id,
                classification,
                1 if gate_enabled else 0,
                reason,
                provider_id,
                profile_name,
                timestamp,
            ),
        )
        connection.commit()
        return ledger_id

    def get_provider_access_gate(self, ledger_id: str) -> Dict[str, Any]:
        """Read one Provider-access gate ledger entry by id."""

        connection = self._require_connection()
        row = connection.execute(
            "SELECT * FROM provider_access_gate_ledger WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"provider access gate ledger entry not found: {ledger_id}")
        return self._decode_row(row, {})

    def provider_access_gate_ledger_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Return all Provider-access gate entries for a run, in recorded order."""

        connection = self._require_connection()
        self._run_row(connection, run_id)
        rows = connection.execute(
            "SELECT * FROM provider_access_gate_ledger WHERE run_id = ? ORDER BY recorded_at, ledger_id",
            (run_id,),
        ).fetchall()
        return [self._decode_row(row, {}) for row in rows]

    def events(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return recorded events; this is a recorded view, not live replay."""

        connection = self._require_connection()
        if run_id is None:
            rows = connection.execute("SELECT * FROM events ORDER BY seq").fetchall()
        else:
            rows = connection.execute("SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        return [self._decode_row(row, {"payload_json": "payload"}) for row in rows]

    def snapshot(self) -> Dict[str, Any]:
        """Return all owner state in a deterministic, JSON-compatible shape."""

        connection = self._require_connection()
        return self._snapshot_from_connection(connection)

    @classmethod
    def _snapshot_from_connection(cls, connection: sqlite3.Connection) -> Dict[str, Any]:
        """Read the canonical state shape from an arbitrary validated DB."""

        connection.row_factory = sqlite3.Row
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "runs": [cls._decode_row(row, {"input_json": "input", "metadata_json": "metadata"}) for row in connection.execute("SELECT * FROM runs ORDER BY created_at, run_id")],
            "approvals": [cls._decode_row(row, {}) for row in connection.execute("SELECT * FROM approvals ORDER BY created_at, approval_id")],
            "effects": [cls._decode_row(row, {"external_receipt_json": "external_receipt", "last_error_json": "last_error"}) for row in connection.execute("SELECT * FROM effects ORDER BY created_at, effect_id")],
            "effect_attempts": [cls._decode_row(row, {"result_json": "result", "error_json": "error"}) for row in connection.execute("SELECT * FROM effect_attempts ORDER BY attempt_id")],
            "results": [cls._decode_row(row, {"value_json": "value"}) for row in connection.execute("SELECT * FROM results ORDER BY created_at, result_id")],
            "replays": [cls._decode_row(row, {"provider_identity_json": "provider_identity", "metadata_json": "metadata"}) for row in connection.execute("SELECT * FROM replays ORDER BY created_at, replay_id")],
            "events": [cls._decode_row(row, {"payload_json": "payload"}) for row in connection.execute("SELECT * FROM events ORDER BY seq")],
            "provider_exit_ledger": [
                cls._decode_row(
                    row,
                    {
                        "surface_observations_json": "surface_observations",
                        "statuses_json": "statuses",
                        "unknown_fields_json": "unknown_fields",
                    },
                )
                for row in connection.execute("SELECT * FROM provider_exit_ledger ORDER BY recorded_at, ledger_id")
            ],
            "provider_fallback_ledger": [
                cls._decode_row(row, {})
                for row in connection.execute("SELECT * FROM provider_fallback_ledger ORDER BY recorded_at, attempt, ledger_id")
            ],
            "provider_attempt_ledger": [
                cls._decode_row(row, {})
                for row in connection.execute("SELECT * FROM provider_attempt_ledger ORDER BY attempt_number, ledger_id")
            ],
            "provider_retry_budget": [
                cls._decode_row(row, {})
                for row in connection.execute("SELECT * FROM provider_retry_budget ORDER BY provider_id")
            ],
            "provider_retry_budget_ledger": [
                cls._decode_row(row, {})
                for row in connection.execute("SELECT * FROM provider_retry_budget_ledger ORDER BY attempt_number, ledger_id")
            ],
            "provider_access_gate_ledger": [
                cls._decode_row(row, {})
                for row in connection.execute("SELECT * FROM provider_access_gate_ledger ORDER BY recorded_at, run_id, ledger_id")
            ],
        }

    def state_digest(self) -> str:
        """Hash the owner state, excluding wall-clock export metadata."""

        return self._sha256(self._canonical_json(self.snapshot()).encode("utf-8"))

    def export_state(self, destination: os.PathLike[str] | str) -> Dict[str, Any]:
        """Write a portable JSON view without exposing approval plaintext tokens."""

        destination_path = Path(destination).expanduser().resolve()
        state = self.snapshot()
        payload = dict(state)
        payload["exported_at"] = self._now()
        payload["state_digest"] = self._sha256(self._canonical_json(state).encode("utf-8"))
        self._atomic_write_json(destination_path, payload)
        return {"path": str(destination_path), "sha256": self._sha256(destination_path.read_bytes()), "state_digest": payload["state_digest"]}

    def backup(self, destination: os.PathLike[str] | str) -> Dict[str, Any]:
        """Create a self-validating SQLite backup plus portable state export."""

        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        if any(destination_path.iterdir()):
            raise FileExistsError(f"backup destination is not empty: {destination_path}")
        self._require_connection().execute("PRAGMA wal_checkpoint(FULL)")
        backup_db = destination_path / "composition.sqlite3"
        target_connection = sqlite3.connect(str(backup_db))
        try:
            self._require_connection().backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
        integrity = self._check_database_integrity(backup_db)
        if not integrity["ok"]:
            raise IntegrityError(integrity["reason"])
        state = self.snapshot()
        state_digest = self._sha256(self._canonical_json(state).encode("utf-8"))
        state_payload = dict(state)
        state_payload["exported_at"] = self._now()
        state_payload["state_digest"] = state_digest
        self._atomic_write_json(destination_path / "state.json", state_payload)
        manifest = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "created_at": self._now(),
            "database_filename": backup_db.name,
            "database_sha256": self._sha256(backup_db.read_bytes()),
            "state_filename": "state.json",
            "state_digest": state_digest,
            "counts": {key: len(value) for key, value in state.items() if isinstance(value, list)},
            "integrity_check": integrity,
        }
        self._atomic_write_json(destination_path / "manifest.json", manifest)
        return manifest

    @classmethod
    def restore(
        cls,
        backup_directory: os.PathLike[str] | str,
        target_database: os.PathLike[str] | str,
        replace: bool = False,
    ) -> Dict[str, Any]:
        """Validate and restore a backup into a new or explicitly replaced DB.

        Existing targets are protected unless ``replace=True`` is explicitly
        supplied.  The replacement is atomic within the target directory.
        """

        backup_path = Path(backup_directory).expanduser().resolve()
        target_path = Path(target_database).expanduser().resolve()
        manifest_path = backup_path / "manifest.json"
        database_path = backup_path / "composition.sqlite3"
        state_path = backup_path / "state.json"
        if not manifest_path.is_file() or not database_path.is_file() or not state_path.is_file():
            raise IntegrityError("backup must contain manifest.json, composition.sqlite3, and state.json")
        manifest = cls._read_json(manifest_path)
        if manifest.get("schema") != SCHEMA or manifest.get("schema_version") != SCHEMA_VERSION:
            raise IntegrityError("unsupported composition backup schema")
        if manifest.get("database_sha256") != cls._sha256(database_path.read_bytes()):
            raise IntegrityError("backup database digest mismatch")
        state = cls._read_json(state_path)
        state_without_metadata = {key: state[key] for key in state if key not in {"exported_at", "state_digest"}}
        calculated_state_digest = cls._sha256(cls._canonical_json_static(state_without_metadata).encode("utf-8"))
        if state.get("state_digest") != calculated_state_digest or manifest.get("state_digest") != calculated_state_digest:
            raise IntegrityError("backup state digest mismatch")
        integrity = cls._check_database_integrity(database_path)
        if not integrity["ok"]:
            raise IntegrityError(integrity["reason"])
        database_connection = sqlite3.connect(str(database_path))
        try:
            database_state = cls._snapshot_from_connection(database_connection)
        finally:
            database_connection.close()
        if database_state != state_without_metadata:
            raise IntegrityError("backup state.json does not match the SQLite snapshot")
        if target_path.exists() and not replace:
            raise FileExistsError(f"restore target exists; pass replace=True explicitly: {target_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target_path.name}.restore-", dir=str(target_path.parent))
        os.close(fd)
        temporary_path = Path(temporary_name)
        try:
            shutil.copyfile(database_path, temporary_path)
            os.replace(temporary_path, target_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return {
            "target_database": str(target_path),
            "database_sha256": cls._sha256(target_path.read_bytes()),
            "state_digest": calculated_state_digest,
            "integrity_check": integrity,
        }

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _configure_connection(self) -> None:
        connection = self._require_connection()
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        # On hosts where the OS sandbox blocks WAL journal fsync into the
        # workspace (e.g. macOS sandbox-center), fall back to an in-memory
        # journal with synchronous=OFF so the durable owner can still be
        # created/written locally. Opt-in via ZW_OWNER_SANDBOX=1 only; it
        # trades crash-durability for drivability. Production keeps WAL/FULL.
        if os.environ.get("ZW_OWNER_SANDBOX") == "1":
            connection.execute("PRAGMA journal_mode = MEMORY")
            connection.execute("PRAGMA synchronous = OFF")
        else:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")

    def _initialize_schema(self) -> None:
        connection = self._require_connection()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS owner_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                input_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                operation_id TEXT NOT NULL UNIQUE,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                token_hash TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decision_reason TEXT,
                consumed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS effects (
                effect_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                operation_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                effect_class TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                physical_effect_count INTEGER NOT NULL,
                approval_id TEXT REFERENCES approvals(approval_id),
                external_receipt_json TEXT,
                last_error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS declared_exposure (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                declared_side_effects_json TEXT NOT NULL,
                exposure_json TEXT NOT NULL,
                declared_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effect_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                effect_id TEXT NOT NULL REFERENCES effects(effect_id),
                attempt INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result_json TEXT,
                error_json TEXT,
                UNIQUE(effect_id, attempt)
            );
            CREATE TABLE IF NOT EXISTS results (
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                kind TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_id TEXT,
                evidence_source TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS replays (
                replay_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                mode TEXT NOT NULL,
                source_event_digest TEXT NOT NULL,
                environment_digest TEXT NOT NULL,
                provider_identity_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                evidence_source TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id, seq);
            CREATE INDEX IF NOT EXISTS results_by_run ON results(run_id, created_at);
            CREATE TABLE IF NOT EXISTS provider_exit_ledger (
                ledger_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                provider TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                account_scope TEXT NOT NULL,
                exit_mode TEXT NOT NULL,
                exit_status TEXT NOT NULL,
                provider_remote_zero_residue TEXT NOT NULL,
                surface_observations_json TEXT NOT NULL,
                statuses_json TEXT NOT NULL,
                unknown_fields_json TEXT NOT NULL,
                local_state_fingerprint TEXT NOT NULL,
                evidence_class TEXT NOT NULL DEFAULT 'local-inventory',
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS provider_exit_ledger_by_run ON provider_exit_ledger(run_id, recorded_at);
            CREATE TABLE IF NOT EXISTS provider_fallback_ledger (
                ledger_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                from_provider TEXT,
                to_provider TEXT,
                reason TEXT NOT NULL,
                degradation_mode TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                failure_code TEXT,
                http_status INTEGER,
                local_state_fingerprint TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS provider_fallback_ledger_by_run ON provider_fallback_ledger(run_id, recorded_at);
            CREATE TABLE IF NOT EXISTS provider_attempt_ledger (
                ledger_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                provider_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                failure_code TEXT,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS provider_attempt_ledger_by_run ON provider_attempt_ledger(run_id, attempt_number, ledger_id);
            CREATE TABLE IF NOT EXISTS provider_retry_budget (
                provider_id TEXT PRIMARY KEY,
                max_retries INTEGER NOT NULL,
                declared_by TEXT NOT NULL,
                declared_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_retry_budget_ledger (
                ledger_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                provider_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                failure_class TEXT NOT NULL,
                target TEXT,
                reason TEXT NOT NULL,
                bound TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS provider_retry_budget_ledger_by_run ON provider_retry_budget_ledger(run_id, attempt_number, ledger_id);
            CREATE TABLE IF NOT EXISTS provider_access_gate_ledger (
                ledger_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                classification TEXT NOT NULL,
                gate_enabled INTEGER NOT NULL,
                reason TEXT NOT NULL,
                provider_id TEXT,
                profile_name TEXT,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS provider_access_gate_ledger_by_run ON provider_access_gate_ledger(run_id, recorded_at, ledger_id);
            INSERT OR IGNORE INTO owner_meta(key, value) VALUES ('schema', 'zworkbench-composition-owner/v1');
            """
        )
        # Migrate existing databases without fabricating values for rows we
        # cannot re-derive. Legacy rows keep NULL (unknown) so the store never
        # lies about an evidence source or class. Read the prior version BEFORE
        # bumping so the migration actually fires.
        prior_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if prior_version < SCHEMA_VERSION:
            for table in ("results", "events"):
                existing_columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "evidence_source" not in existing_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN evidence_source TEXT")
            # C7 (1-3-5): classify each Provider exit ledger entry. Legacy rows
            # default to 'local-inventory' — the default loopback/fake path which
            # never claimed a Provider clearance — so the migration never
            # fabricates an owner-backed attestation.
            existing_exit_columns = {row["name"] for row in connection.execute("PRAGMA table_info(provider_exit_ledger)")}
            if "evidence_class" not in existing_exit_columns:
                connection.execute(
                    "ALTER TABLE provider_exit_ledger ADD COLUMN evidence_class TEXT NOT NULL DEFAULT 'local-inventory'"
                )
        connection.execute("PRAGMA user_version = 3")

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._require_connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise CompositionError("composition owner is closed")
        return self._connection

    @staticmethod
    def _now() -> str:
        return _datetime.datetime.now(_datetime.timezone.utc).isoformat(timespec="milliseconds")

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _canonical_json_static(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise IntegrityError(f"expected JSON object: {path}")
        return value

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @classmethod
    def _atomic_write_json(cls, path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _require_text(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def _validate_evidence_source(value: Any) -> str:
        """Classify an evidence source or fail-closed on a missing/invalid value.

        The owner must distinguish native / plugin-composed / outer-composed
        evidence. A missing or unknown classification is rejected rather than
        silently defaulted, so untagged evidence cannot enter the durable store.
        """

        if not isinstance(value, str) or not value.strip():
            raise ValueError("evidence_source must be a non-empty string")
        if value not in EVIDENCE_SOURCES:
            raise ValueError(
                f"evidence_source must be one of {sorted(EVIDENCE_SOURCES)}: {value!r}"
            )
        return value

    @staticmethod
    def _reject_raw_credentials(value: Any, field_name: str) -> None:
        """Reject obvious credential fields and secret-shaped values before they enter owner evidence.

        Scans both raw credential *field names* (e.g. ``api_key``) and *values*
        matching provider secret patterns (``sk-...`` / ``AKIA...``). Identity
        references (``_ref`` / ``_digest`` / ``_id`` suffixes) are allowed.
        """

        sensitive = {"api_key", "apikey", "authorization", "cookie", "password", "secret", "token", "key"}
        safe_field_names = {"idempotency_key"}
        safe_suffixes = ("_ref", "_reference", "_fingerprint", "_digest", "_id")

        def visit(current: Any, path: str) -> None:
            if isinstance(current, Mapping):
                for key, item in current.items():
                    normalized = str(key).lower().replace("-", "_")
                    if normalized not in safe_field_names and not normalized.endswith(safe_suffixes):
                        parts = set(normalized.split("_"))
                        if normalized in sensitive or parts & sensitive:
                            raise ValueError(f"{field_name} contains raw credential field {path}.{key}")
                    visit(item, f"{path}.{key}")
            elif isinstance(current, (list, tuple)):
                for index, item in enumerate(current):
                    visit(item, f"{path}[{index}]")
            elif isinstance(current, str):
                if _SECRET_VALUE.search(current):
                    raise ValueError(f"{field_name} contains a secret-shaped value at {path}")

        visit(value, field_name)

    @staticmethod
    def _reject_secret_shaped_values(value: Any, field_name: str) -> None:
        """Reject secret-shaped *string* leaves without the credential-field-name
        check.

        The field-name check in :meth:`_reject_raw_credentials` would flag
        legitimate redacted status keys such as ``statuses.api_key`` (whose value
        is a status like ``deleted``, never a secret).  The C7 owner-backed
        receipt carries exactly those redacted status maps, so this helper scans
        only string *values* for provider secret shapes, leaving the receipt's
        structure intact.
        """

        def visit(current: Any, path: str) -> None:
            if isinstance(current, Mapping):
                for key, item in current.items():
                    visit(item, f"{path}.{key}")
            elif isinstance(current, (list, tuple)):
                for index, item in enumerate(current):
                    visit(item, f"{path}[{index}]")
            elif isinstance(current, str):
                if _SECRET_VALUE.search(current):
                    raise ValueError(f"{field_name} contains a secret-shaped value at {path}")

        visit(value, field_name)

    def _run_row(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"run not found: {run_id}")
        return row

    def _effect_row(self, connection: sqlite3.Connection, effect_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"effect not found: {effect_id}")
        return row

    def _set_run_status(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        new_status: str,
        event_type: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> None:
        old_status = row["status"]
        if new_status not in RUN_STATES:
            raise InvalidTransition(f"unknown run status: {new_status}")
        allowed = {
            "created": {"running", "waiting_approval", "failed", "safe_stopped"},
            "running": {"waiting_approval", "recovering", "completed", "failed", "safe_stopped"},
            "waiting_approval": {"running", "failed", "safe_stopped"},
            "recovering": {"running", "failed", "safe_stopped"},
            "completed": set(),
            "failed": set(),
            "safe_stopped": set(),
        }
        if old_status == new_status:
            return
        if new_status not in allowed[old_status]:
            raise InvalidTransition(f"run {row['run_id']} cannot move {old_status} -> {new_status}")
        timestamp = self._now()
        connection.execute("UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?", (new_status, timestamp, row["run_id"]))
        event_payload = {"from": old_status, "to": new_status}
        event_payload.update(dict(payload or {}))
        self._append_event(connection, row["run_id"], event_type, event_payload)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        event_id: Optional[str] = None,
        evidence_source: str = EVIDENCE_SOURCE_NATIVE,
    ) -> str:
        self._reject_raw_credentials(payload, "event payload")
        self._validate_evidence_source(evidence_source)
        event_id = event_id or self._new_id()
        connection.execute(
            "INSERT INTO events(event_id, run_id, type, payload_json, evidence_source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, run_id, event_type, self._canonical_json(dict(payload)), evidence_source, self._now()),
        )
        return event_id

    def _record_result_tx(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        kind: str,
        value: Any,
        source_id: Optional[str],
        evidence_source: str,
    ) -> Dict[str, Any]:
        self._reject_raw_credentials(value, "value")
        self._validate_evidence_source(evidence_source)
        if source_id is not None:
            existing = connection.execute(
                "SELECT * FROM results WHERE run_id = ? AND kind = ? AND source_id = ?",
                (run_id, kind, source_id),
            ).fetchone()
            if existing:
                return self._decode_row(existing, {"value_json": "value"})
        result_id = self._new_id()
        timestamp = self._now()
        connection.execute(
            "INSERT INTO results(result_id, run_id, kind, value_json, source_id, evidence_source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (result_id, run_id, kind, self._canonical_json(value), source_id, evidence_source, timestamp),
        )
        self._append_event(connection, run_id, "result.recorded", {"result_id": result_id, "kind": kind, "source_id": source_id}, evidence_source=evidence_source)
        return self._decode_row(connection.execute("SELECT * FROM results WHERE result_id = ?", (result_id,)).fetchone(), {"value_json": "value"})

    @staticmethod
    def _decode_row(row: sqlite3.Row, json_fields: Mapping[str, str]) -> Dict[str, Any]:
        result = {key: row[key] for key in row.keys()}
        for column, output_name in json_fields.items():
            if result.get(column) is not None:
                result[output_name] = json.loads(result.pop(column))
            else:
                result[output_name] = None
        return result

    @staticmethod
    def _approval_scope_matches(row: sqlite3.Row, action: str, resource: str, idempotency_key: str) -> bool:
        return row["action"] == action and row["resource"] == resource and row["idempotency_key"] == idempotency_key

    @staticmethod
    def _effect_scope_matches(row: sqlite3.Row, operation_id: str, action: str, resource: str, idempotency_key: str, effect_class: str) -> bool:
        return (
            row["operation_id"] == operation_id
            and row["action"] == action
            and row["resource"] == resource
            and row["idempotency_key"] == idempotency_key
            and row["effect_class"] == effect_class
        )

    @staticmethod
    def _validate_effect_inputs(operation_id: str, action: str, resource: str, idempotency_key: str, effect_class: str, max_attempts: int) -> None:
        for value, label in ((operation_id, "operation_id"), (action, "action"), (resource, "resource"), (idempotency_key, "idempotency_key"), (effect_class, "effect_class")):
            CompositionOwner._require_text(value, label)
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    @classmethod
    def _check_database_integrity(cls, path: Path) -> Dict[str, Any]:
        try:
            connection = sqlite3.connect(str(path))
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
                user_version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            return {"ok": False, "reason": f"sqlite error: {exc}"}
        required = {"owner_meta", "runs", "approvals", "effects", "declared_exposure", "effect_attempts", "results", "replays", "events", "provider_exit_ledger", "provider_fallback_ledger", "provider_attempt_ledger", "provider_retry_budget", "provider_retry_budget_ledger", "provider_access_gate_ledger"}
        if result != "ok":
            return {"ok": False, "reason": f"integrity_check={result}"}
        if user_version != SCHEMA_VERSION or not required.issubset(tables):
            return {"ok": False, "reason": "schema tables or user_version mismatch"}
        return {"ok": True, "integrity_check": result, "user_version": user_version}

    # The canonical table set.  Must stay in sync with the `required` set in
    # _check_database_integrity above: every table this owner may create is a
    # first-class, auditable part of the single durable state.  Any other user
    # table in this database would be a *second* canonical state (forbidden).
    _CANONICAL_TABLES: ClassVar[frozenset[str]] = frozenset(
        {
            "owner_meta",
            "runs",
            "approvals",
            "effects",
            "declared_exposure",
            "effect_attempts",
            "results",
            "replays",
            "events",
            "provider_exit_ledger",
            "provider_fallback_ledger",
            "provider_attempt_ledger",
            "provider_retry_budget",
            "provider_retry_budget_ledger",
            "provider_access_gate_ledger",
        }
    )

    def audit_owner_isolated(self) -> Dict[str, Any]:
        """Audit that this CompositionOwner is the unique durable owner.

        Promotes the "no second canonical state" invariant (sub-03, node 1-6-3)
        from discipline to a testable contract.  The set of user tables in this
        database must be exactly ``_CANONICAL_TABLES`` (plus sqlite_sequence).
        Any extra user table would be a second canonical state and fails the audit.
        """
        connection = self._require_connection()
        actual = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        canonical = actual & self._CANONICAL_TABLES
        extra = actual - self._CANONICAL_TABLES - {"sqlite_sequence"}
        return {
            "owner_is_unique": len(extra) == 0,
            "canonical_tables": sorted(canonical),
            "non_canonical_tables": sorted(extra),
            "expected_canonical_count": len(self._CANONICAL_TABLES),
            "actual_canonical_count": len(canonical),
        }
