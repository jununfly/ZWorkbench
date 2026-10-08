"""Write seam — the only runtime seam for local write effects (S2).

S2 productizes the reversible write boundary: a Codex-generated unified diff
is applied to an *isolated* git worktree and committed locally (no push).  The
seam reuses the single :class:`CompositionOwner` — approval, effect claim and
the commit receipt all live there.  No second durable owner is introduced (R3
architecture negative constraint #2: "写 seam 的 receipt / approval 数据模型不得
引入第二个 durable owner").

Generating the diff and applying it are separated (see
``docs/architecture/ta-reversible-write-boundary.md``): the caller is
responsible for producing the unified diff (e.g. from a Codex turn run in a
writable sub-environment); this seam applies it to an isolated worktree.  The
main workspace is never touched — the worktree lives under
``worktree_root/<run_id>``.

Write blast radius is graded (R3 「写操作爆炸半径分级」):
``apply`` (revertible) -> ``commit`` (resettable) -> ``push`` (hard to undo).
S2 implements the first two; push is the S4 separate gate and is never performed
here (``pushed`` is always ``False`` in the receipt).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from .composition import CompositionOwner, EVIDENCE_SOURCE_NATIVE


WRITE_SEAM_SCHEMA = "zworkbench-write-seam/v1"
#: S2 write effects require an explicit, approved token bound to the same
#: operation/action/resource/idempotency key.
EFFECT_CLASS_WRITE = "approval-required"


class WriteSeamError(RuntimeError):
    """Base error for the write seam."""


class WorktreeCreationError(WriteSeamError):
    """The isolated worktree could not be created."""


class DiffApplyError(WriteSeamError):
    """The diff could not be applied (invalid patch, conflict, or no change)."""


@dataclass(frozen=True)
class WriteReceipt:
    """The bounded, owner-backed outcome of one write effect."""

    effect_id: str
    status: str
    worktree_path: str
    commit_hash: Optional[str]
    diff_digest: str
    external_receipt: Mapping[str, Any]


class WriteSeam:
    """Apply a unified diff to an isolated worktree and commit it locally.

    The seam is stateless across runs except for the owner it is given.  It
    never opens a second owner database; every durable fact goes through the
    supplied :class:`CompositionOwner`.
    """

    SCHEMA = WRITE_SEAM_SCHEMA

    def __init__(
        self,
        owner: CompositionOwner,
        worktree_root: os.PathLike[str] | str,
        *,
        case_root: os.PathLike[str] | str | None = None,
    ) -> None:
        self.owner = owner
        self.worktree_root = Path(worktree_root).expanduser().resolve()
        self.case_root = Path(case_root).expanduser().resolve() if case_root is not None else None

    # ------------------------------------------------------------------
    # Isolated worktree (S2-①)
    # ------------------------------------------------------------------

    def create_worktree(
        self,
        run_id: str,
        repo: os.PathLike[str] | str,
        base_ref: str = "HEAD",
    ) -> Path:
        """Create an isolated git worktree for one run.

        The worktree lives under ``worktree_root/<run_id>`` so the main
        workspace is never touched.  A worktree that already exists for the run
        is reused (idempotent across retries).  The path is recorded in the owner
        as a durable result so later stages and the human can locate it.
        """

        repo_path = Path(repo).expanduser().resolve()
        if self.case_root is not None and not self._inside_case_root(repo_path):
            raise WorktreeCreationError(f"repo {repo_path} is outside case_root {self.case_root}")
        if not _is_git_repo(repo_path):
            raise WorktreeCreationError(f"not a git repository: {repo_path}")
        worktree_path = self.worktree_root / run_id
        if self.case_root is not None and not self._inside_case_root(worktree_path):
            raise WorktreeCreationError(f"worktree {worktree_path} is outside case_root {self.case_root}")
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            # Reuse an existing worktree for the run (idempotent across retries).
            self.owner.record_result(
                run_id,
                "write_seam.worktree.reused",
                {"worktree_path": str(worktree_path)},
                f"{run_id}:worktree",
                evidence_source=EVIDENCE_SOURCE_NATIVE,
            )
        else:
            try:
                _git(repo_path, ["worktree", "add", "--force", str(worktree_path), base_ref])
            except subprocess.CalledProcessError as exc:
                raise WorktreeCreationError(f"git worktree add failed: {exc}") from exc
            self.owner.record_result(
                run_id,
                "write_seam.worktree.created",
                {"worktree_path": str(worktree_path), "base_ref": base_ref},
                f"{run_id}:worktree",
                evidence_source=EVIDENCE_SOURCE_NATIVE,
            )
        # Record the repo fingerprint (the base-ref HEAD) so apply_diff can detect
        # repo/worktree substitution or tampering before any write effect commits.
        repo_fingerprint = _git(repo_path, ["rev-parse", base_ref]).strip()
        self.owner.record_result(
            run_id,
            "write_seam.repo.fingerprint",
            {"repo_fingerprint": repo_fingerprint, "base_ref": base_ref, "repo": str(repo_path)},
            f"{run_id}:repo_fingerprint",
            evidence_source=EVIDENCE_SOURCE_NATIVE,
        )
        return worktree_path

    # ------------------------------------------------------------------
    # Apply + commit (S2-② / S2-③ / S2-④ / S2-⑤)
    # ------------------------------------------------------------------

    def apply_diff(
        self,
        run_id: str,
        worktree_path: os.PathLike[str] | str,
        patch_text: str,
        *,
        approval_token: str,
        operation_id: str,
        action: str = "apply_diff",
        resource: str,
        idempotency_key: str,
        reason: str = "S2 write seam local commit",
    ) -> WriteReceipt:
        """Claim, apply and commit one write effect, returning an owner-backed receipt.

        The effect is ``approval-required``: it must carry an approved token
        bound to the same operation/action/resource/idempotency key.  Idempotency
        is enforced by the owner — a replay with the same idempotency key returns
        the already-completed receipt without a second physical commit, so the
        worktree digest changes at most once (S2-⑤ 执行级幂等验收).
        """

        worktree_path = Path(worktree_path).expanduser().resolve()
        claim = self.owner.claim_effect(
            run_id,
            operation_id,
            action,
            resource,
            idempotency_key,
            EFFECT_CLASS_WRITE,
            approval_token=approval_token,
        )
        if not claim.executable:
            # Non-executable claim: already completed (idempotent replay), in
            # flight, recovery required, or denied.  Return the durable receipt if
            # one exists; otherwise surface the denial.
            existing = self._completed_receipt(run_id, operation_id)
            if existing is not None:
                return existing
            raise WriteSeamError(f"effect not executable: {claim.reason}")

        # 1-4-2 invariants: the effect's declared resource must equal the physical
        # worktree being written (no resource/physical-target confusion), and the
        # repo fingerprint recorded at create_worktree must still match (no repo
        # or worktree substitution/tampering).  These run only when a write is
        # actually about to happen, so an idempotent replay returns above untouched.
        if Path(resource).expanduser().resolve() != worktree_path:
            raise DiffApplyError(
                f"effect resource {resource!r} does not match the worktree being written {worktree_path}"
            )
        self._ensure_repo_fingerprint(run_id, worktree_path)

        effect_id = claim.effect_id
        assert effect_id is not None
        before_commit = _git(worktree_path, ["rev-parse", "HEAD"]).strip()
        diff_digest = _sha256(patch_text)
        try:
            # Dry-run first so a bad patch leaves the worktree clean.
            _git(worktree_path, ["apply", "--check", "-"], input_text=patch_text)
            _git(worktree_path, ["apply", "-"], input_text=patch_text)
        except subprocess.CalledProcessError as exc:
            self.owner.mark_effect_uncertain(effect_id, {"error": str(exc), "stage": "apply"})
            raise DiffApplyError(f"diff apply rejected (worktree left clean): {exc}") from exc

        try:
            after_commit = _commit(worktree_path, reason)
        except subprocess.CalledProcessError as exc:
            # The patch applied but staged nothing committable (no-op / already
            # applied content): mark uncertain and fail closed rather than record
            # a phantom commit.
            self.owner.mark_effect_uncertain(effect_id, {"error": str(exc), "stage": "commit"})
            raise DiffApplyError("diff applied but produced no committable change") from exc

        external_receipt = {
            "schema": WRITE_SEAM_SCHEMA,
            "operation": action,
            "operation_id": operation_id,
            "action": action,
            "resource": resource,
            "idempotency_key": idempotency_key,
            "worktree_path": str(worktree_path),
            "commit_hash": after_commit,
            "diff_digest": diff_digest,
            "commit_before": before_commit,
            "commit_after": after_commit,
            "pushed": False,
        }
        self.owner.complete_effect(
            effect_id,
            {"commit_hash": after_commit, "commit_before": before_commit, "commit_after": after_commit},
            external_receipt,
        )
        return WriteReceipt(
            effect_id=effect_id,
            status="completed",
            worktree_path=str(worktree_path),
            commit_hash=after_commit,
            diff_digest=diff_digest,
            external_receipt=external_receipt,
        )

    def _inside_case_root(self, path: Path) -> bool:
        """True when ``path`` is the case root or lives inside it."""

        if self.case_root is None:
            return True
        return path == self.case_root or self.case_root in path.parents

    def _ensure_repo_fingerprint(self, run_id: str, worktree_path: Path) -> None:
        """Fail-closed: the worktree HEAD must still equal the recorded fingerprint.

        A mismatch means the repo or worktree was substituted or tampered with
        between ``create_worktree`` and ``apply_diff``; refuse to commit.
        """

        expected = self._stored_repo_fingerprint(run_id)
        if expected is None:
            # Runs created before fingerprinting existed have nothing to verify.
            # The product path always stores a fingerprint, so this branch only
            # guards legacy fixtures; no write happens here, merely a skipped check.
            return
        current = _git(worktree_path, ["rev-parse", "HEAD"]).strip()
        if current != expected:
            raise DiffApplyError(
                f"repo fingerprint mismatch at {worktree_path}: expected {expected}, got {current}"
            )

    def _stored_repo_fingerprint(self, run_id: str) -> Optional[str]:
        """Return the repo fingerprint recorded at ``create_worktree``, if any."""

        run = self.owner.get_run(run_id)
        for result in run.get("results", []):
            if result.get("kind") == "write_seam.repo.fingerprint":
                return result.get("value", {}).get("repo_fingerprint")
        return None

    def _completed_receipt(self, run_id: str, operation_id: str) -> Optional[WriteReceipt]:
        """Return the durable receipt for an already-completed effect, if any."""

        run = self.owner.get_run(run_id)
        for effect in run.get("effects", []):
            if effect.get("operation_id") == operation_id and effect.get("status") == "completed":
                receipt = effect.get("external_receipt") or {}
                return WriteReceipt(
                    effect_id=effect["effect_id"],
                    status="already_completed",
                    worktree_path=receipt.get("worktree_path", ""),
                    commit_hash=receipt.get("commit_hash"),
                    diff_digest=receipt.get("diff_digest", ""),
                    external_receipt=receipt,
                )
        return None


def _git(repo: Path, args: list[str], *, input_text: Optional[str] = None) -> str:
    """Run one git command in ``repo`` and return stdout (utf-8, replace errors)."""

    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _commit(repo: Path, message: str) -> str:
    """Stage everything and create a local commit; return the new HEAD sha."""

    _git(repo, ["add", "-A"])
    _git(repo, ["commit", "-m", message])
    return _git(repo, ["rev-parse", "HEAD"]).strip()


def _is_git_repo(path: Path) -> bool:
    """True when ``path`` is the root of a git repository (bare or not)."""

    if (path / ".git").exists():
        return True
    try:
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "WRITE_SEAM_SCHEMA",
    "EFFECT_CLASS_WRITE",
    "WriteSeamError",
    "WorktreeCreationError",
    "DiffApplyError",
    "WriteReceipt",
    "WriteSeam",
]
