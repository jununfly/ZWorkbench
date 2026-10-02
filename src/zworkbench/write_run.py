"""Control-plane orchestrator that drives the S2 write seam.

The :class:`WriteRunOrchestrator` is the owner-backed driver that connects the
durable :class:`CompositionOwner` to the stateless :class:`WriteSeam`.  It is
the "orchestrator 接 write seam" seam for roadmap 1-7-6: a Codex-generated
unified diff is applied to an isolated worktree and committed locally.  Push is
never performed here — it is the separate S4 gate and stays off by default.

The orchestrator opens the owner, ensures the run exists, creates the isolated
worktree, and applies+commits the diff through the seam.  No second durable
owner is constructed (R3 architecture negative constraint #2: "写 seam 的
receipt / approval 数据模型不得引入第二个 durable owner").
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .composition import CompositionError, CompositionOwner
from .write_seam import WriteReceipt, WriteSeam


class WriteRunOrchestrator:
    """Drive the S2 write seam through one owner-backed run.

    The orchestrator is the only control-plane entry that applies a write
    effect.  It reuses the single :class:`CompositionOwner` passed to the seam
    and never opens a second owner database.
    """

    def __init__(self, database: os.PathLike[str] | str, *, worktree_root: os.PathLike[str] | str) -> None:
        self.database = Path(database).expanduser().resolve()
        self.worktree_root = Path(worktree_root).expanduser().resolve()

    def apply(
        self,
        run_id: str,
        repo: os.PathLike[str] | str,
        patch_text: str,
        *,
        approval_token: str,
        operation_id: str,
        action: str = "apply_diff",
        resource: str,
        idempotency_key: str,
        base_ref: str = "HEAD",
        reason: str = "S2 write seam local commit",
    ) -> WriteReceipt:
        """Create an isolated worktree and apply+commit the diff, owner-backed.

        The run is created if absent (idempotent across retries).  Push is never
        performed: the returned receipt always reports ``pushed=False`` and no
        remote is configured (S2 write blast radius stops at the local commit;
        ``push`` is the S4 separate gate and is never touched here).
        """

        with CompositionOwner(self.database) as owner:
            self._ensure_run(owner, run_id)
            seam = WriteSeam(owner, self.worktree_root)
            worktree_path = seam.create_worktree(run_id, repo, base_ref)
            receipt = seam.apply_diff(
                run_id,
                worktree_path,
                patch_text,
                approval_token=approval_token,
                operation_id=operation_id,
                action=action,
                resource=resource,
                idempotency_key=idempotency_key,
                reason=reason,
            )
            # The write effect completed locally; close the run as completed so
            # the durable owner reflects a finished write (no push, ever).
            owner.complete_run(
                run_id,
                {
                    "write_receipt_commit": receipt.commit_hash,
                    "worktree_path": str(worktree_path),
                },
            )
            return receipt

    @staticmethod
    def _ensure_run(owner: CompositionOwner, run_id: str) -> None:
        """Create the run if absent; reuse an existing one (idempotent)."""

        try:
            owner.create_run(run_id, "write_seam", {"driver": "WriteRunOrchestrator"})
        except CompositionError:
            # The run already exists (a prior apply attempt, or a read-only run
            # that produced the diff).  Reuse it; the seam's idempotency
            # guarantee keeps the physical commit count at one.
            pass


__all__ = ["WriteRunOrchestrator"]
