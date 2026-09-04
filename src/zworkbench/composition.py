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
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence


SCHEMA = "zworkbench-composition-owner/v1"
SCHEMA_VERSION = 1
ALLOWED_EFFECT_CLASSES = frozenset({"read-only", "idempotent", "approval-required"})
REPLAY_MODES = frozenset({"recorded_view", "simulated_replay", "live_replay"})
RUN_STATES = frozenset(
    {"created", "running", "waiting_approval", "recovering", "completed", "failed", "safe_stopped"}
)
EFFECT_STATES = frozenset({"claimed", "completed", "uncertain", "retryable", "unknown"})


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
        self._reject_raw_credentials(input_value, "input")
        metadata_value = dict(metadata or {})
        self._reject_raw_credentials(metadata_value, "metadata")
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
        """Complete a run only when no effect remains unresolved."""

        with self._transaction() as connection:
            row = self._run_row(connection, run_id)
            if row["status"] != "running":
                raise InvalidTransition(f"run {run_id} is not running: {row['status']}")
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count FROM effects
                WHERE run_id = ? AND status IN ('claimed', 'uncertain', 'retryable', 'unknown')
                """,
                (run_id,),
            ).fetchone()["count"]
            if unresolved:
                raise InvalidTransition(f"run {run_id} has {unresolved} unresolved effect(s)")
            self._record_result_tx(connection, run_id, "semantic", semantic_result, "run")
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
                self._record_result_tx(connection, run_id, "error", error, "run")
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

    def complete_effect(
        self,
        effect_id: str,
        result: Any,
        external_receipt: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Commit one physical effect and its result exactly once."""

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
            self._record_result_tx(connection, effect["run_id"], "effect", result, effect_id)
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
                self._record_result_tx(connection, effect["run_id"], "effect", {"reconciled": True, "evidence": evidence}, effect_id)
            return self._decode_row(connection.execute("SELECT * FROM effects WHERE effect_id = ?", (effect_id,)).fetchone(), {"external_receipt_json": "external_receipt"})

    # ------------------------------------------------------------------
    # Evidence, export and portable backup
    # ------------------------------------------------------------------

    def record_result(self, run_id: str, kind: str, value: Any, source_id: Optional[str] = None) -> Dict[str, Any]:
        """Append a durable semantic or adapter result."""

        self._require_text(kind, "kind")
        self._reject_raw_credentials(value, "value")
        with self._transaction() as connection:
            self._run_row(connection, run_id)
            return self._record_result_tx(connection, run_id, kind, value, source_id)

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append one structured adapter event without exposing SQLite.

        Adapter messages are evidence, not a second source of truth.  The
        owner therefore assigns the canonical event row and keeps the public
        seam deliberately smaller than the underlying table.  A caller may
        provide a stable event id when retrying an already-recorded message;
        a conflicting reuse is rejected instead of being silently merged.
        """

        self._require_text(event_type, "event_type")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be an object")
        payload_value = dict(payload)
        self._reject_raw_credentials(payload_value, "payload")
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
                    )
                    if not same:
                        raise CompositionError("event_id is already bound to different event data")
                    return self._decode_row(existing, {"payload_json": "payload"})
            assigned_id = self._append_event(connection, run_id, event_type, payload_value, event_id)
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
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id, seq);
            CREATE INDEX IF NOT EXISTS results_by_run ON results(run_id, created_at);
            INSERT OR IGNORE INTO owner_meta(key, value) VALUES ('schema', 'zworkbench-composition-owner/v1');
            PRAGMA user_version = 1;
            """
        )

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
    def _reject_raw_credentials(value: Any, field_name: str) -> None:
        """Reject obvious credential fields before they enter owner evidence."""

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
    ) -> str:
        self._reject_raw_credentials(payload, "event payload")
        event_id = event_id or self._new_id()
        connection.execute(
            "INSERT INTO events(event_id, run_id, type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, run_id, event_type, self._canonical_json(dict(payload)), self._now()),
        )
        return event_id

    def _record_result_tx(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        kind: str,
        value: Any,
        source_id: Optional[str],
    ) -> Dict[str, Any]:
        self._reject_raw_credentials(value, "value")
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
            "INSERT INTO results(result_id, run_id, kind, value_json, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (result_id, run_id, kind, self._canonical_json(value), source_id, timestamp),
        )
        self._append_event(connection, run_id, "result.recorded", {"result_id": result_id, "kind": kind, "source_id": source_id})
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
        required = {"owner_meta", "runs", "approvals", "effects", "effect_attempts", "results", "replays", "events"}
        if result != "ok":
            return {"ok": False, "reason": f"integrity_check={result}"}
        if user_version != SCHEMA_VERSION or not required.issubset(tables):
            return {"ok": False, "reason": "schema tables or user_version mismatch"}
        return {"ok": True, "integrity_check": result, "user_version": user_version}
