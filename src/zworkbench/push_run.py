"""Control-plane orchestrator that drives the S4 push seam.

The :class:`PushRunOrchestrator` connects the durable
:class:`~zworkbench.composition.CompositionOwner` to the stateless
:class:`~zworkbench.push_seam.PushSeam`.  It is the "orchestrator 接 push seam"
seam for roadmap 1-10-5: a known local commit is pushed to a named remote behind
the S4 gate.

The orchestrator opens the owner, ensures an *independent* push run exists
(task type ``push_seam``, ``metadata.parent_run_id`` linking back to the apply
run), performs the push through the seam, and closes the run.  Push is never
performed by :mod:`write_seam` or :mod:`write_run`; this module is the only
control-plane entry that performs it.  No second durable owner is constructed
(R3 architecture negative constraint #2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .composition import CompositionError, CompositionOwner
from .push_seam import PushReceipt, PushSeam


class PushRunOrchestrator:
    """Drive the S4 push seam through one owner-backed push run.

    The orchestrator is the only control-plane entry that performs a push
    effect.  It reuses the single :class:`CompositionOwner` passed to the seam
    and never opens a second owner database.
    """

    def __init__(
        self,
        database: Path | str,
        *,
        case_root: Path | str | None = None,
        push_enabled: bool = False,
    ) -> None:
        self.database = Path(database).expanduser().resolve()
        self.case_root = Path(case_root).expanduser().resolve() if case_root is not None else None
        # Lock 1 + the CLI gate: the orchestrator only enables push when the
        # caller (the CLI --push-gate) explicitly opts in.
        self.push_enabled = push_enabled

    def push(
        self,
        run_id: str,
        repo: Path | str,
        remote: str,
        ref: str,
        expect_commit: str,
        source_run_id: str,
        apply_operation_id: str,
        *,
        approval_token: str,
        operation_id: str,
        action: str = "push_commit",
        resource: str,
        idempotency_key: str,
        force_with_lease: bool = False,
        reason: str = "S4 push seam git push",
    ) -> PushReceipt:
        """Push ``expect_commit`` to ``remote``/``ref`` through an owner-backed run.

        The push run is created if absent (idempotent across retries) and closed
        as completed on success.  On an idempotent replay (same idempotency key)
        the seam returns the already-completed receipt and the run is already
        closed — closing it twice is an InvalidTransition, so only close a
        non-completed run.
        """

        with CompositionOwner(self.database) as owner:
            self._ensure_run(owner, run_id, parent_run_id=source_run_id)
            seam = PushSeam(owner, push_enabled=self.push_enabled, case_root=self.case_root)
            receipt = seam.push(
                run_id,
                repo,
                remote,
                ref,
                expect_commit,
                source_run_id,
                apply_operation_id,
                approval_token=approval_token,
                operation_id=operation_id,
                action=action,
                resource=resource,
                idempotency_key=idempotency_key,
                force_with_lease=force_with_lease,
                reason=reason,
            )
            if owner.get_run(run_id)["status"] != "completed":
                owner.complete_run(
                    run_id,
                    {
                        "push_remote": receipt.remote,
                        "push_ref": receipt.ref,
                        "push_expect_commit": receipt.expect_commit,
                        "physical_push_performed": receipt.physical_push_performed,
                        "noop": receipt.noop,
                        "pushed": receipt.pushed,
                    },
                )
            return receipt

    @staticmethod
    def _ensure_run(owner: CompositionOwner, run_id: str, parent_run_id: Optional[str] = None) -> None:
        """Create the push run if absent; reuse an existing one (idempotent)."""

        try:
            owner.create_run(
                run_id,
                "push_seam",
                {"driver": "PushRunOrchestrator", "parent_run_id": parent_run_id},
            )
        except CompositionError:
            # The run already exists (a prior push attempt).  Reuse it; the
            # seam's idempotency guarantee keeps the physical push count at one.
            pass


__all__ = ["PushRunOrchestrator"]
