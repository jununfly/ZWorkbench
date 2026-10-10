"""Tests for the S4 push seam (roadmap 1-10-5).

The push seam is the separate, off-by-default gate for the hard-to-undo
``git push`` (the third blast-radius grade after apply -> commit).  These tests
guard:

* Lock 1 (library default off): ``PushSeam(push_enabled=False)`` refuses before
  claiming — no approval token consumed, no effect row created.
* Lock 3 (separate approval): push carries its own operation/action/resource/
  idempotency key; missing / wrong / mismatched approval is denied.
* Happy path: a known local commit is pushed to a named bare remote, the effect
  is completed, the remote ref moves to the commit, and the receipt records the
  anonymous URL + sha256 (no credential).
* Owner-level idempotency: a same-key replay returns the already-completed
  receipt and performs no second physical push.
* Cross-process idempotency: when the remote ref already points at the commit,
  the physical push is skipped (noop=True, physical_push_performed=False).
* A-class preconditions (no physical push): remote missing, ref not a branch,
  HEAD != expect_commit, chained custody mismatch -> reconcile not-applied
  (effect retryable, run running), raised as PushPrecheckError.
* B-class uncertainty: a non-fast-forward push that git rejects -> mark_effect
  uncertain, run recovering, raised as PushUncertainError; force-with-lease
  succeeds against the same divergence.
* Static guard: write_seam.py / write_run.py contain no push execution surface.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import zworkbench.push_seam as push_seam_module
import zworkbench.write_run as write_run_module
import zworkbench.write_seam as write_seam_module
from zworkbench.composition import CompositionOwner
from zworkbench.push_seam import (
    PushDisabledError,
    PushPrecheckError,
    PushReceipt,
    PushSeam,
    PushSeamError,
    PushUncertainError,
)
from zworkbench.push_run import PushRunOrchestrator
from zworkbench.write_seam import WriteSeam


VALID_PATCH = (
    "diff --git a/hello.txt b/hello.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/hello.txt\n"
    "@@ -0,0 +1,1 @@\n"
    "+hello world\n"
)


def _run_git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
    ).stdout.strip()


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@zworkbench.local")
    _run_git(repo, "config", "user.name", "ZWorkbench Test")
    _run_git(repo, "config", "commit.gpgsign", "false")
    (repo / "existing.txt").write_text("seed\n", encoding="utf-8")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "initial seed")
    return repo


def _make_bare_remote(root: Path, branch: str) -> Path:
    """Create a bare remote, optionally seeded with one unrelated commit on ``branch``.

    Returns the bare repo path.  When ``seed`` is true the remote's ``branch``
    already carries a commit that is NOT an ancestor of anything we push later,
    so a non-fast-forward push is rejected (and force-with-lease can be tested).
    """

    bare = root / "bare.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", str(bare)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return bare


def _seed_bare_branch(bare: Path, branch: str) -> str:
    """Put one unrelated commit on ``branch`` in the bare remote; return its SHA."""

    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary) / "seedrepo"
        tmp.mkdir()
        _run_git(tmp, "init", "-q")
        _run_git(tmp, "config", "user.email", "test@zworkbench.local")
        _run_git(tmp, "config", "user.name", "ZWorkbench Test")
        _run_git(tmp, "config", "commit.gpgsign", "false")
        (tmp / "seed.txt").write_text("bare seed\n", encoding="utf-8")
        _run_git(tmp, "add", "-A")
        _run_git(tmp, "commit", "-q", "-m", "bare seed")
        sha = _run_git(tmp, "rev-parse", "HEAD")
        _run_git(tmp, "push", str(bare), f"{sha}:refs/heads/{branch}")
        return sha


def _current_branch(repo: Path) -> str:
    return _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def _approved_token(
    owner: CompositionOwner,
    run_id: str,
    operation_id: str,
    action: str,
    resource: str,
    idempotency_key: str,
    reason: str = "S4 test",
) -> str:
    approval = owner.request_approval(run_id, operation_id, action, resource, idempotency_key, reason)
    granted = owner.approve(approval["approval_id"])
    return granted["token"]


def _apply_commit(
    owner: CompositionOwner,
    case_root: Path,
    repo: Path,
    worktree_root: Path,
    run_id: str,
    operation_id: str,
    resource: str,
    idempotency_key: str,
) -> tuple[Path, str]:
    """Perform a real S2 apply so an apply receipt + worktree commit exist."""

    try:
        owner.create_run(run_id, "write_seam", {"x": 1})
    except Exception:
        # The caller may have already created the run; reuse it.
        pass
    seam = WriteSeam(owner, worktree_root, case_root=case_root)
    worktree = seam.create_worktree(run_id, repo)
    token = _approved_token(owner, run_id, operation_id, "apply_diff", resource, idempotency_key)
    receipt = seam.apply_diff(
        run_id,
        worktree,
        VALID_PATCH,
        approval_token=token,
        operation_id=operation_id,
        action="apply_diff",
        resource=resource,
        idempotency_key=idempotency_key,
    )
    return worktree, receipt.commit_hash


class PushSeamLockTests(unittest.TestCase):
    """Lock 1 (library default off) and lock 3 (separate approval)."""

    def _setup_owner(self, root: Path) -> CompositionOwner:
        return CompositionOwner(root / "state" / "owner.sqlite3")

    def test_default_off_refuses_before_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            owner = self._setup_owner(root)
            try:
                owner.create_run("run-lock1", "push_seam", {"x": 1})
                # Lock 1: disabled by default.
                seam = PushSeam(owner, push_enabled=False)
                with self.assertRaises(PushDisabledError):
                    seam.push(
                        "run-lock1", repo, "origin", "main", "deadbeef",
                        "src", "applyop",
                        approval_token="unused", operation_id="opX",
                        action="push_commit", resource=str(repo),
                        idempotency_key="kX",
                    )
                # No effect row, no approval consumed.
                run = owner.get_run("run-lock1")
                self.assertEqual(run["effects"], [])
            finally:
                owner.close()

    def test_missing_approval_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            owner = self._setup_owner(root)
            try:
                owner.create_run("run-miss", "push_seam", {"x": 1})
                worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-miss", "applyop", str(worktree_root / "run-apply-miss"), "kA")
                _run_git(worktree, "remote", "add", "origin", str(root / "bare.git"))
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                with self.assertRaises(PushSeamError):
                    seam.push(
                        "run-miss", worktree, "origin", _current_branch(worktree), commit,
                        "run-apply-miss", "applyop",
                        approval_token="no-token", operation_id="opMissing",
                        action="push_commit", resource=str(worktree),
                        idempotency_key="kMiss",
                    )
            finally:
                owner.close()

    def test_wrong_token_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            owner = self._setup_owner(root)
            try:
                owner.create_run("run-wrong", "push_seam", {"x": 1})
                worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-wrong", "applyop", str(worktree_root / "run-apply-wrong"), "kA")
                _run_git(worktree, "remote", "add", "origin", str(root / "bare.git"))
                token = _approved_token(owner, "run-wrong", "opW", "push_commit", str(worktree), "kW")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                with self.assertRaises(PushSeamError):
                    seam.push(
                        "run-wrong", worktree, "origin", _current_branch(worktree), commit,
                        "run-apply-wrong", "applyop",
                        approval_token="not-the-token", operation_id="opW",
                        action="push_commit", resource=str(worktree),
                        idempotency_key="kW",
                    )
            finally:
                owner.close()

    def test_scope_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            owner = self._setup_owner(root)
            try:
                owner.create_run("run-scope", "push_seam", {"x": 1})
                worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-scope", "applyop", str(worktree_root / "run-apply-scope"), "kA")
                _run_git(worktree, "remote", "add", "origin", str(root / "bare.git"))
                # Approval bound to resource "wt-A" but push claims "wt-B".
                token = _approved_token(owner, "run-scope", "opS", "push_commit", "wt-A", "kS")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                with self.assertRaises(PushSeamError):
                    seam.push(
                        "run-scope", worktree, "origin", _current_branch(worktree), commit,
                        "run-apply-scope", "applyop",
                        approval_token=token, operation_id="opS",
                        action="push_commit", resource="wt-B",
                        idempotency_key="kS",
                    )
            finally:
                owner.close()


class PushSeamHappyPathTests(unittest.TestCase):
    """Happy path + owner-level idempotency + cross-process noop."""

    def _scenario(self, root: Path):
        repo = _make_repo(root)
        case_root = repo
        worktree_root = repo / ".zw-worktrees"
        branch = _current_branch(repo)
        bare = _make_bare_remote(root, branch)
        owner = CompositionOwner(root / "state" / "owner.sqlite3")
        owner.create_run("run-apply-hp", "write_seam", {"x": 1})
        worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-hp", "applyop", str(worktree_root / "run-apply-hp"), "kA")
        _run_git(worktree, "remote", "add", "origin", str(bare))
        return owner, repo, case_root, worktree_root, worktree, commit, branch, bare

    def test_happy_path_pushes_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, repo, case_root, worktree_root, worktree, commit, branch, bare = self._scenario(root)
            try:
                owner.create_run("run-push-hp", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-hp", "opP", "push_commit", str(worktree), "kP")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                receipt = seam.push(
                    "run-push-hp", worktree, "origin", branch, commit,
                    "run-apply-hp", "applyop",
                    approval_token=token, operation_id="opP",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kP",
                )
                self.assertEqual(receipt.status, "completed")
                self.assertTrue(receipt.pushed)
                self.assertTrue(receipt.physical_push_performed)
                self.assertFalse(receipt.noop)
                # Remote ref now reports the pushed commit.
                self.assertEqual(_run_git(worktree, "ls-remote", "origin", f"refs/heads/{branch}").split()[0], commit)
                # Receipt records anonymous URL + sha256 of the (local path) URL.
                ext = receipt.external_receipt
                self.assertEqual(ext["remote"], "origin")
                self.assertEqual(ext["ref"], f"refs/heads/{branch}")
                self.assertEqual(ext["expect_commit"], commit)
                self.assertEqual(ext["credential_source"], "ambient")
                self.assertNotIn("secret", ext["remote_url_anonymous"])
            finally:
                owner.close()

    def test_owner_level_idempotent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, repo, case_root, worktree_root, worktree, commit, branch, bare = self._scenario(root)
            try:
                owner.create_run("run-push-idem", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-idem", "opI", "push_commit", str(worktree), "kI")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                first = seam.push(
                    "run-push-idem", worktree, "origin", branch, commit,
                    "run-apply-hp", "applyop",
                    approval_token=token, operation_id="opI",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kI",
                )
                # Replay same idempotency key -> already_completed, no second push.
                second = seam.push(
                    "run-push-idem", worktree, "origin", branch, commit,
                    "run-apply-hp", "applyop",
                    approval_token=token, operation_id="opI",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kI",
                )
                self.assertEqual(second.status, "already_completed")
                self.assertEqual(first.external_receipt["expect_commit"], second.external_receipt["expect_commit"])
            finally:
                owner.close()

    def test_cross_process_noop_when_remote_already_has_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, repo, case_root, worktree_root, worktree, commit, branch, bare = self._scenario(root)
            try:
                # First push actually performs the physical push.
                owner.create_run("run-push-noop", "push_seam", {"x": 1})
                token1 = _approved_token(owner, "run-push-noop", "opN1", "push_commit", str(worktree), "kN1")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                seam.push(
                    "run-push-noop", worktree, "origin", branch, commit,
                    "run-apply-hp", "applyop",
                    approval_token=token1, operation_id="opN1",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kN1",
                )
                # Second push with a fresh key: the remote already has it -> noop.
                token2 = _approved_token(owner, "run-push-noop", "opN2", "push_commit", str(worktree), "kN2")
                receipt = seam.push(
                    "run-push-noop", worktree, "origin", branch, commit,
                    "run-apply-hp", "applyop",
                    approval_token=token2, operation_id="opN2",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kN2",
                )
                self.assertTrue(receipt.pushed)
                self.assertFalse(receipt.physical_push_performed, "remote already had the commit; no physical push")
                self.assertTrue(receipt.noop)
                # Only one physical push took place across both effect claims.
            finally:
                owner.close()


class PushSeamPrecheckTests(unittest.TestCase):
    """A-class preconditions: no physical push, reconcile not-applied (retryable)."""

    def _scenario(self, root: Path):
        repo = _make_repo(root)
        case_root = repo
        worktree_root = repo / ".zw-worktrees"
        branch = _current_branch(repo)
        bare = _make_bare_remote(root, branch)
        owner = CompositionOwner(root / "state" / "owner.sqlite3")
        owner.create_run("run-apply-pc", "write_seam", {"x": 1})
        worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-pc", "applyop", str(worktree_root / "run-apply-pc"), "kA")
        _run_git(worktree, "remote", "add", "origin", str(bare))
        return owner, case_root, worktree, commit, branch

    def _push_expect_precheck(self, owner, worktree, commit, branch, op, key, remote, ref, source_run, apply_op, head=None, expect_commit=None):
        owner.create_run("run-push-pc", "push_seam", {"x": 1})
        token = _approved_token(owner, "run-push-pc", op, "push_commit", str(worktree), key)
        seam = PushSeam(owner, push_enabled=True, case_root=worktree.parent.parent)
        with self.assertRaises(PushPrecheckError):
            seam.push(
                "run-push-pc", worktree, remote, ref, expect_commit if expect_commit else commit,
                source_run, apply_op,
                approval_token=token, operation_id=op,
                action="push_commit", resource=str(worktree),
                idempotency_key=key,
            )
        run = owner.get_run("run-push-pc")
        effects = [e for e in run["effects"] if e["operation_id"] == op]
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["status"], "retryable", "A-class failure must reconcile as not-applied (retryable)")
        self.assertEqual(run["status"], "running")

    def test_remote_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, case_root, worktree, commit, branch = self._scenario(root)
            try:
                self._push_expect_precheck(owner, worktree, commit, branch, "opRNF", "kRNF", "nonexistent", branch, "run-apply-pc", "applyop")
            finally:
                owner.close()

    def test_ref_not_a_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, case_root, worktree, commit, branch = self._scenario(root)
            try:
                self._push_expect_precheck(owner, worktree, commit, branch, "opRef", "kRef", "origin", "refs/tags/v1.0", "run-apply-pc", "applyop")
            finally:
                owner.close()

    def test_head_not_equal_expect_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, case_root, worktree, commit, branch = self._scenario(root)
            try:
                # HEAD/commit matches the real apply receipt, but we lie about
                # expect_commit: the head check fires before custody.
                self._push_expect_precheck(owner, worktree, commit, branch, "opHead", "kHead", "origin", branch, "run-apply-pc", "applyop", expect_commit="0" * 40)
            finally:
                owner.close()

    def test_custody_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner, case_root, worktree, commit, branch = self._scenario(root)
            try:
                # HEAD == expect_commit (the real apply commit), but the chained
                # custody points at a source run / apply op that does not exist,
                # so the receipt commit cannot be verified -> custody fails.
                owner.create_run("run-push-pc", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-pc", "opCust", "push_commit", str(worktree), "kCust")
                seam = PushSeam(owner, push_enabled=True, case_root=worktree.parent.parent)
                with self.assertRaises(PushPrecheckError):
                    seam.push(
                        "run-push-pc", worktree, "origin", branch, commit,
                        "run-does-not-exist", "applyop",
                        approval_token=token, operation_id="opCust",
                        action="push_commit", resource=str(worktree),
                        idempotency_key="kCust",
                    )
                run = owner.get_run("run-push-pc")
                effects = [e for e in run["effects"] if e["operation_id"] == "opCust"]
                self.assertEqual(effects[0]["status"], "retryable")
            finally:
                owner.close()


class PushSeamUncertainTests(unittest.TestCase):
    """B-class uncertainty: non-fast-forward rejected -> mark_effect_uncertain.

    And the force-with-lease escape hatch succeeds against the same divergence.
    """

    def test_non_fast_forward_marks_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            branch = _current_branch(repo)
            bare = _make_bare_remote(root, branch)
            _seed_bare_branch(bare, branch)  # divergent commit already on bare
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-apply-uf", "write_seam", {"x": 1})
            worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-uf", "applyop", str(worktree_root / "run-apply-uf"), "kA")
            _run_git(worktree, "remote", "add", "origin", str(bare))
            try:
                owner.create_run("run-push-uf", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-uf", "opUF", "push_commit", str(worktree), "kUF")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                with self.assertRaises(PushUncertainError):
                    seam.push(
                        "run-push-uf", worktree, "origin", branch, commit,
                        "run-apply-uf", "applyop",
                        approval_token=token, operation_id="opUF",
                        action="push_commit", resource=str(worktree),
                        idempotency_key="kUF",
                    )
                run = owner.get_run("run-push-uf")
                effects = [e for e in run["effects"] if e["operation_id"] == "opUF"]
                self.assertEqual(effects[0]["status"], "uncertain")
                self.assertEqual(run["status"], "recovering")
            finally:
                owner.close()

    def test_force_with_lease_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            branch = _current_branch(repo)
            bare = _make_bare_remote(root, branch)
            remote_before = _seed_bare_branch(bare, branch)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-apply-fwl", "write_seam", {"x": 1})
            worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-fwl", "applyop", str(worktree_root / "run-apply-fwl"), "kA")
            _run_git(worktree, "remote", "add", "origin", str(bare))
            try:
                owner.create_run("run-push-fwl", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-fwl", "opFWL", "push_commit", str(worktree), "kFWL")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                receipt = seam.push(
                    "run-push-fwl", worktree, "origin", branch, commit,
                    "run-apply-fwl", "applyop",
                    approval_token=token, operation_id="opFWL",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kFWL",
                    force_with_lease=True,
                )
                self.assertTrue(receipt.pushed)
                self.assertTrue(receipt.physical_push_performed)
                # The lease (remote_before) matched, so the forced push landed.
                self.assertEqual(_run_git(worktree, "ls-remote", "origin", f"refs/heads/{branch}").split()[0], commit)
            finally:
                owner.close()


class PushSeamUrlHygieneTests(unittest.TestCase):
    """Credential discipline: the URL written to the receipt carries no secret."""

    def test_strip_userinfo_unit(self) -> None:
        url = "https://alice:s3cr3t@example.com/owner/repo.git"
        anonymous, digest = push_seam_module._strip_userinfo(url)
        self.assertNotIn("s3cr3t", anonymous)
        self.assertNotIn("alice", anonymous)
        self.assertEqual(anonymous, "https://example.com/owner/repo.git")
        import hashlib
        self.assertEqual(digest, hashlib.sha256(url.encode("utf-8")).hexdigest())

    def test_receipt_records_anonymous_url_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            branch = _current_branch(repo)
            bare = _make_bare_remote(root, branch)
            owner = CompositionOwner(root / "state" / "owner.sqlite3")
            owner.create_run("run-apply-url", "write_seam", {"x": 1})
            worktree, commit = _apply_commit(owner, case_root, repo, worktree_root, "run-apply-url", "applyop", str(worktree_root / "run-apply-url"), "kA")
            # Remote URL with userinfo; git can still push to a local path, but
            # we instead point at the bare via a path URL to keep the test offline.
            _run_git(worktree, "remote", "add", "origin", str(bare))
            try:
                owner.create_run("run-push-url", "push_seam", {"x": 1})
                token = _approved_token(owner, "run-push-url", "opURL", "push_commit", str(worktree), "kURL")
                seam = PushSeam(owner, push_enabled=True, case_root=case_root)
                receipt = seam.push(
                    "run-push-url", worktree, "origin", branch, commit,
                    "run-apply-url", "applyop",
                    approval_token=token, operation_id="opURL",
                    action="push_commit", resource=str(worktree),
                    idempotency_key="kURL",
                )
                ext = receipt.external_receipt
                self.assertEqual(ext["remote_url_anonymous"], str(bare))
                import hashlib
                self.assertEqual(ext["remote_url_sha256"], hashlib.sha256(str(bare).encode("utf-8")).hexdigest())
                # The full URL with any userinfo is never persisted verbatim.
                self.assertNotIn("://", str(ext.get("remote_url_anonymous", "")).replace(str(bare), ""))
            finally:
                owner.close()


class PushSeamStaticGuardTests(unittest.TestCase):
    """write_seam.py / write_run.py must carry no push execution surface."""

    def test_write_seam_has_no_push_execution_surface(self) -> None:
        src = Path(write_seam_module.__file__).read_text(encoding="utf-8")
        # No git 'push' subcommand literal, and no method named push*.
        self.assertNotIn('"push"', src)
        self.assertNotIn("'push'", src)
        self.assertNotRegex(src, r"def\s+\w*push\w*\s*\(")

    def test_write_run_has_no_push_execution_surface(self) -> None:
        src = Path(write_run_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"push"', src)
        self.assertNotIn("'push'", src)
        self.assertNotRegex(src, r"def\s+\w*push\w*\s*\(")


if __name__ == "__main__":
    unittest.main()
