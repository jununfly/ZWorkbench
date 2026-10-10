"""Tests for the ``zworkbench write push`` CLI subcommand (roadmap 1-10-5).

The CLI is the second lock on the S4 push gate: ``write push`` is denied unless
``--push-gate`` is present (lock 2).  These tests guard:

* Lock 2: ``write push`` without ``--push-gate`` is denied (exit 2) before any
  case-local check or push attempt.
* End-to-end: with ``--push-gate``, a known local commit is pushed to a named
  bare remote and the command reports ``completed`` with the receipt.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from zworkbench.cli import _parser
from zworkbench.composition import CompositionOwner
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


def _make_bare_remote(root: Path) -> Path:
    bare = root / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return bare


def _current_branch(repo: Path) -> str:
    return _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def _approved_token(owner, run_id, operation_id, action, resource, key):
    approval = owner.request_approval(run_id, operation_id, action, resource, key, "S4 cli test")
    return owner.approve(approval["approval_id"])["token"]


class WritePushCliTests(unittest.TestCase):
    def test_write_push_requires_gate(self) -> None:
        parser = _parser()
        args = parser.parse_args([
            "write", "push",
            "--db", "/tmp/does-not-matter",
            "--case-root", "/tmp/does-not-matter",
            "--repo", "/tmp/does-not-matter",
            "--remote", "origin",
            "--ref", "main",
            "--expect-commit", "abc123",
            "--source-run-id", "r1",
            "--apply-operation-id", "a1",
            "--approval-token", "tok",
            "--operation-id", "op1",
            "--resource", "/tmp/does-not-matter",
            "--idempotency-key", "k1",
            # NOTE: --push-gate intentionally absent
        ])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = args.handler(args)
        self.assertEqual(code, 2, "write push without --push-gate must be denied")
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["status"], "denied")
        self.assertIn("push-gate", payload.get("reason", ""))

    def test_write_push_end_to_end_with_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            case_root = repo
            worktree_root = repo / ".zw-worktrees"
            branch = _current_branch(repo)
            bare = _make_bare_remote(root)
            owner = CompositionOwner(repo / "state" / "owner.sqlite3")
            try:
                # Produce a real apply receipt + worktree commit.
                apply_run_id = "run-apply-cli"
                apply_op = "applyop-cli"
                owner.create_run(apply_run_id, "write_seam", {"x": 1})
                seam = WriteSeam(owner, worktree_root, case_root=case_root)
                worktree = seam.create_worktree(apply_run_id, repo)
                token = _approved_token(owner, apply_run_id, apply_op, "apply_diff", str(worktree), "kA")
                receipt = seam.apply_diff(
                    apply_run_id, worktree, VALID_PATCH,
                    approval_token=token, operation_id=apply_op, action="apply_diff",
                    resource=str(worktree), idempotency_key="kA",
                )
                commit = receipt.commit_hash
                _run_git(worktree, "remote", "add", "origin", str(bare))

                # Approve the push operation on its own push run.
                push_run_id = "run-push-cli"
                owner.create_run(push_run_id, "push_seam", {"x": 1})
                push_token = _approved_token(owner, push_run_id, "opCli", "push_commit", str(worktree), "kCli")

                parser = _parser()
                args = parser.parse_args([
                    "write", "push",
                    "--db", str(repo / "state" / "owner.sqlite3"),
                    "--case-root", str(case_root),
                    "--repo", str(worktree),
                    "--remote", "origin",
                    "--ref", branch,
                    "--expect-commit", commit,
                    "--source-run-id", apply_run_id,
                    "--apply-operation-id", apply_op,
                    "--run-id", push_run_id,
                    "--approval-token", push_token,
                    "--operation-id", "opCli",
                    "--resource", str(worktree),
                    "--idempotency-key", "kCli",
                    "--push-gate",
                ])
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = args.handler(args)
                self.assertEqual(code, 0, buf.getvalue())
                payload = json.loads(buf.getvalue())
                self.assertEqual(payload["status"], "completed")
                self.assertEqual(payload["receipt"]["external_receipt"]["expect_commit"], commit)
                # The remote ref moved to the pushed commit.
                remote_sha = _run_git(worktree, "ls-remote", "origin", f"refs/heads/{branch}").split()[0]
                self.assertEqual(remote_sha, commit)
            finally:
                owner.close()


if __name__ == "__main__":
    unittest.main()
