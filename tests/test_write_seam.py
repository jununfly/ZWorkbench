"""Tests for the S2 write seam (roadmap 1-7-1 .. 1-7-5).

The seam applies a Codex-generated unified diff to an isolated git worktree and
commits it locally (no push), recording an owner-backed receipt.  These tests
guard:

* S2-① isolation: the main workspace is never touched; the worktree path is
  recorded in the owner.
* S2-② diff apply: a valid patch is applied; an invalid patch is rejected and
  the worktree is left clean.
* S2-③ local commit: the change is committed locally with no push.
* S2-④ receipt: operation/action/resource/idempotency key are bound in the
  external_receipt, and no second durable owner is constructed.
* S2-⑤ approval + idempotency: the effect is approval-required; a replay with
  the same idempotency key produces at most one physical commit (one digest
  change).
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import zworkbench.write_seam as write_seam_module
from zworkbench.composition import CompositionOwner
from zworkbench.write_seam import (
    DiffApplyError,
    WorktreeCreationError,
    WriteSeam,
    WriteSeamError,
)

VALID_PATCH = (
    "diff --git a/hello.txt b/hello.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/hello.txt\n"
    "@@ -0,0 +1,1 @@\n"
    "+hello world\n"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
    ).stdout.strip()


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@zworkbench.local")
    _git(repo, "config", "user.name", "ZWorkbench Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "existing.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial seed")
    return repo


def _commit_count(repo: Path) -> int:
    return int(_git(repo, "rev-list", "--count", "HEAD"))


def _approved_token(
    owner: CompositionOwner,
    run_id: str,
    operation_id: str,
    action: str,
    resource: str,
    idempotency_key: str,
    reason: str = "S2 test",
) -> str:
    approval = owner.request_approval(run_id, operation_id, action, resource, idempotency_key, reason)
    granted = owner.approve(approval["approval_id"])
    return granted["token"]


class WriteSeamWorktreeTests(unittest.TestCase):
    """S2-①: isolated worktree, main workspace untouched, path recorded."""

    def test_create_worktree_isolates_main_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            try:
                run_id = "run-wt-1"
                owner.create_run(run_id, "write_seam", {"x": 1})
                seam = WriteSeam(owner, root / "worktrees")
                worktree = seam.create_worktree(run_id, repo)

                self.assertTrue(worktree.exists(), "worktree must be created")
                # Main workspace keeps only its seed file; the write seam never
                # touches it directly.
                self.assertTrue((repo / "existing.txt").exists())
                self.assertFalse((repo / "hello.txt").exists(), "main workspace must stay untouched")

                run = owner.get_run(run_id)
                created = [r for r in run["results"] if r["kind"] == "write_seam.worktree.created"]
                self.assertEqual(len(created), 1, "worktree path must be recorded in the owner")
                self.assertEqual(created[0]["value"]["worktree_path"], str(worktree))
            finally:
                owner.close()

    def test_create_worktree_idempotent_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            try:
                run_id = "run-wt-2"
                owner.create_run(run_id, "write_seam", {"x": 1})
                seam = WriteSeam(owner, root / "worktrees")
                first = seam.create_worktree(run_id, repo)
                second = seam.create_worktree(run_id, repo)
                self.assertEqual(first, second, "repeated create_worktree must reuse the same path")

                run = owner.get_run(run_id)
                reused = [r for r in run["results"] if r["kind"] == "write_seam.worktree.reused"]
                self.assertEqual(len(reused), 1, "second create must record a reuse event")
            finally:
                owner.close()


class WriteSeamApplyCommitTests(unittest.TestCase):
    """S2-② / S2-③: diff apply + local commit, no push, invalid patch rejected."""

    def _setup(self, root: Path, run_id: str):
        repo = _make_repo(root)
        owner = CompositionOwner(root / "state" / "owner.sqlite3")
        owner.create_run(run_id, "write_seam", {"x": 1})
        seam = WriteSeam(owner, root / "worktrees")
        worktree = seam.create_worktree(run_id, repo)
        return owner, seam, repo, worktree

    def test_apply_valid_diff_commits_locally_no_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, seam, repo, worktree = self._setup(root, "run-apply-1")
            try:
                token = _approved_token(owner, "run-apply-1", "op1", "apply_diff", str(worktree), "k1")
                receipt = seam.apply_diff(
                    "run-apply-1",
                    worktree,
                    VALID_PATCH,
                    approval_token=token,
                    operation_id="op1",
                    action="apply_diff",
                    resource=str(worktree),
                    idempotency_key="k1",
                )
                self.assertEqual(receipt.status, "completed")
                self.assertEqual((worktree / "hello.txt").read_text(), "hello world\n")
                self.assertIsNotNone(receipt.commit_hash)
                # S2 is local-only: no remote is configured and the receipt
                # declares pushed=False.
                self.assertFalse(receipt.external_receipt["pushed"])
                self.assertEqual(_git(worktree, "remote"), "", "write seam must never configure a push remote")
                self.assertEqual(_commit_count(worktree), 2, "exactly one local write commit on top of the seed")

                run = owner.get_run("run-apply-1")
                effects = [e for e in run["effects"] if e["operation_id"] == "op1"]
                self.assertEqual(len(effects), 1)
                self.assertEqual(effects[0]["status"], "completed")
                self.assertEqual(effects[0]["external_receipt"]["commit_hash"], receipt.commit_hash)
            finally:
                owner.close()

    def test_apply_invalid_diff_rejected_worktree_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, seam, repo, worktree = self._setup(root, "run-apply-2")
            try:
                token = _approved_token(owner, "run-apply-2", "op2", "apply_diff", str(worktree), "k2")
                with self.assertRaises(DiffApplyError):
                    seam.apply_diff(
                        "run-apply-2",
                        worktree,
                        "this is not a unified diff",
                        approval_token=token,
                        operation_id="op2",
                        action="apply_diff",
                        resource=str(worktree),
                        idempotency_key="k2",
                    )
                # The bad patch must not leave a partial file behind.
                self.assertFalse((worktree / "hello.txt").exists(), "worktree must be left clean after a rejected patch")
                self.assertEqual(_commit_count(worktree), 1, "no commit may be created for a rejected patch")

                run = owner.get_run("run-apply-2")
                effects = [e for e in run["effects"] if e["operation_id"] == "op2"]
                self.assertEqual(effects[0]["status"], "uncertain", "a rejected apply must be marked uncertain")
            finally:
                owner.close()


class WriteSeamReceiptTests(unittest.TestCase):
    """S2-④: receipt binds the approval scope; no second durable owner."""

    def test_write_seam_must_not_construct_second_owner(self) -> None:
        source = Path(write_seam_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn(
            "CompositionOwner(",
            source,
            "write_seam must reuse the single CompositionOwner, never construct a second durable owner",
        )
        self.assertIn("CompositionOwner", source, "write_seam should reference the owner it is given")

    def test_receipt_binds_operation_action_resource_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-receipt", "write_seam", {"x": 1})
            seam = WriteSeam(owner, root / "worktrees")
            worktree = seam.create_worktree("run-receipt", repo)
            try:
                token = _approved_token(owner, "run-receipt", "opR", "apply_diff", str(worktree), "kR")
                receipt = seam.apply_diff(
                    "run-receipt",
                    worktree,
                    VALID_PATCH,
                    approval_token=token,
                    operation_id="opR",
                    action="apply_diff",
                    resource=str(worktree),
                    idempotency_key="kR",
                )
                receipt_data = receipt.external_receipt
                self.assertEqual(receipt_data["operation_id"], "opR")
                self.assertEqual(receipt_data["action"], "apply_diff")
                self.assertEqual(receipt_data["resource"], str(worktree))
                self.assertEqual(receipt_data["idempotency_key"], "kR")
                self.assertEqual(receipt_data["commit_hash"], receipt.commit_hash)
                self.assertEqual(receipt_data["diff_digest"], receipt.diff_digest)
                self.assertFalse(receipt_data["pushed"])
            finally:
                owner.close()


class WriteSeamApprovalIdempotencyTests(unittest.TestCase):
    """S2-⑤: approval-required gate + execution-level idempotency."""

    def test_apply_requires_approved_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-gate", "write_seam", {"x": 1})
            seam = WriteSeam(owner, root / "worktrees")
            worktree = seam.create_worktree("run-gate", repo)
            try:
                # No request_approval was made for opG: the effect must be denied.
                with self.assertRaises(WriteSeamError):
                    seam.apply_diff(
                        "run-gate",
                        worktree,
                        VALID_PATCH,
                        approval_token="unused",
                        operation_id="opG",
                        action="apply_diff",
                        resource=str(worktree),
                        idempotency_key="kG",
                    )
            finally:
                owner.close()

    def test_wrong_token_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-wrong", "write_seam", {"x": 1})
            seam = WriteSeam(owner, root / "worktrees")
            worktree = seam.create_worktree("run-wrong", repo)
            try:
                token = _approved_token(owner, "run-wrong", "opW", "apply_diff", str(worktree), "kW")
                with self.assertRaises(WriteSeamError):
                    seam.apply_diff(
                        "run-wrong",
                        worktree,
                        VALID_PATCH,
                        approval_token="not-the-approved-token",
                        operation_id="opW",
                        action="apply_diff",
                        resource=str(worktree),
                        idempotency_key="kW",
                    )
            finally:
                owner.close()

    def test_scope_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-scope", "write_seam", {"x": 1})
            seam = WriteSeam(owner, root / "worktrees")
            worktree = seam.create_worktree("run-scope", repo)
            try:
                token = _approved_token(owner, "run-scope", "opS", "apply_diff", "wt-A", "kS")
                # Approval bound to resource "wt-A" but the apply claims "wt-B".
                with self.assertRaises(WriteSeamError):
                    seam.apply_diff(
                        "run-scope",
                        worktree,
                        VALID_PATCH,
                        approval_token=token,
                        operation_id="opS",
                        action="apply_diff",
                        resource="wt-B",
                        idempotency_key="kS",
                    )
            finally:
                owner.close()

    def test_idempotent_replay_single_digest_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-idem", "write_seam", {"x": 1})
            seam = WriteSeam(owner, root / "worktrees")
            worktree = seam.create_worktree("run-idem", repo)
            try:
                token = _approved_token(owner, "run-idem", "opI", "apply_diff", str(worktree), "kI")
                first = seam.apply_diff(
                    "run-idem",
                    worktree,
                    VALID_PATCH,
                    approval_token=token,
                    operation_id="opI",
                    action="apply_diff",
                    resource=str(worktree),
                    idempotency_key="kI",
                )
                # Replay with the same idempotency key: must return the existing
                # receipt without creating a second physical commit.
                second = seam.apply_diff(
                    "run-idem",
                    worktree,
                    VALID_PATCH,
                    approval_token=token,
                    operation_id="opI",
                    action="apply_diff",
                    resource=str(worktree),
                    idempotency_key="kI",
                )
                self.assertEqual(second.status, "already_completed")
                self.assertEqual(first.commit_hash, second.commit_hash, "replay must not produce a new commit")
                self.assertEqual(_commit_count(worktree), 2, "only one digest change across the replay")
                self.assertEqual(_git(worktree, "rev-parse", "HEAD"), first.commit_hash)
            finally:
                owner.close()


class WriteSeamCaseLocalTests(unittest.TestCase):
    """1-4-2: case-local boundary + resource==worktree assertion + repo fingerprint.

    The seam must not trust its caller: the repo and the isolated worktree must
    both resolve inside the case root, the effect's declared resource must equal
    the physical worktree being written, and the worktree must still carry the
    repo fingerprint recorded at create_worktree time (no substitution/tampering).
    """

    def _real_repo_outside(self, root: Path, case: Path) -> Path:
        """A valid git repo that lives *outside* ``case`` (for negative tests)."""

        case.mkdir(parents=True, exist_ok=True)
        repo = root / "outside_repo"
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@zworkbench.local")
        _git(repo, "config", "user.name", "ZWorkbench Test")
        _git(repo, "config", "commit.gpgsign", "false")
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "initial seed")
        return repo

    def test_create_worktree_rejects_repo_outside_case_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_root = root / "case"
            repo = self._real_repo_outside(root, case_root)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            try:
                owner.create_run("run-cl-1", "write_seam", {"x": 1})
                seam = WriteSeam(owner, root / "worktrees", case_root=case_root)
                with self.assertRaises(WorktreeCreationError):
                    seam.create_worktree("run-cl-1", repo)
            finally:
                owner.close()

    def test_create_worktree_rejects_worktree_outside_case_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Repo lives inside case_root, but the worktree root is outside it.
            case_root = root / "case"
            case_root.mkdir(parents=True, exist_ok=True)
            repo = case_root / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _git(repo, "init", "-q")
            _git(repo, "config", "user.email", "test@zworkbench.local")
            _git(repo, "config", "user.name", "ZWorkbench Test")
            _git(repo, "config", "commit.gpgsign", "false")
            (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "initial seed")

            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            try:
                owner.create_run("run-cl-2", "write_seam", {"x": 1})
                seam = WriteSeam(owner, root / "outside_worktrees", case_root=case_root)
                with self.assertRaises(WorktreeCreationError):
                    seam.create_worktree("run-cl-2", repo)
            finally:
                owner.close()

    def test_apply_diff_rejects_resource_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo  # case-root == repo root (the real dogfood convention)
            worktree_root = repo / ".zw-worktrees"
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-cl-3", "write_seam", {"x": 1})
            seam = WriteSeam(owner, worktree_root, case_root=case_root)
            worktree = seam.create_worktree("run-cl-3", repo)
            try:
                resource_cl = str(worktree.parent / "other-target")
                token = _approved_token(owner, "run-cl-3", "opCL3", "apply_diff", resource_cl, "kCL3")
                with self.assertRaises(DiffApplyError):
                    seam.apply_diff(
                        "run-cl-3",
                        worktree,
                        VALID_PATCH,
                        approval_token=token,
                        operation_id="opCL3",
                        action="apply_diff",
                        resource=resource_cl,
                        idempotency_key="kCL3",
                    )
            finally:
                owner.close()

    def test_apply_diff_rejects_repo_fingerprint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-cl-4", "write_seam", {"x": 1})
            seam = WriteSeam(owner, worktree_root, case_root=case_root)
            worktree = seam.create_worktree("run-cl-4", repo)
            # Tamper with the worktree between create_worktree and apply_diff.
            _git(worktree, "commit", "--allow-empty", "-m", "tamper")
            try:
                token = _approved_token(owner, "run-cl-4", "opCL4", "apply_diff", str(worktree), "kCL4")
                with self.assertRaises(DiffApplyError):
                    seam.apply_diff(
                        "run-cl-4",
                        worktree,
                        VALID_PATCH,
                        approval_token=token,
                        operation_id="opCL4",
                        action="apply_diff",
                        resource=str(worktree),
                        idempotency_key="kCL4",
                    )
            finally:
                owner.close()

    def test_happy_path_records_fingerprint_and_applies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-cl-5", "write_seam", {"x": 1})
            seam = WriteSeam(owner, worktree_root, case_root=case_root)
            worktree = seam.create_worktree("run-cl-5", repo)
            try:
                run = owner.get_run("run-cl-5")
                fp = [r for r in run["results"] if r["kind"] == "write_seam.repo.fingerprint"]
                self.assertEqual(len(fp), 1, "repo fingerprint must be recorded at create_worktree")
                self.assertTrue(fp[0]["value"]["repo_fingerprint"])

                token = _approved_token(owner, "run-cl-5", "opCL5", "apply_diff", str(worktree), "kCL5")
                receipt = seam.apply_diff(
                    "run-cl-5",
                    worktree,
                    VALID_PATCH,
                    approval_token=token,
                    operation_id="opCL5",
                    action="apply_diff",
                    resource=str(worktree),
                    idempotency_key="kCL5",
                )
                self.assertEqual(receipt.status, "completed")
                self.assertEqual((worktree / "hello.txt").read_text(), "hello world\n")
            finally:
                owner.close()


if __name__ == "__main__":
    unittest.main()
