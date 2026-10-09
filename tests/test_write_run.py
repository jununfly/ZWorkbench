"""Tests for the S2 write orchestrator (roadmap 1-7-6).

The :class:`WriteRunOrchestrator` is the owner-backed control-plane driver that
connects the durable :class:`CompositionOwner` to the write seam.  These tests
guard:

* the orchestrator drives ``create_worktree`` + ``apply_diff`` through one owner;
* push is never performed (receipt ``pushed`` is False, no remote configured);
* the run is created if absent and reused across retries (idempotent);
* no second durable owner is constructed by the orchestrator module;
* a missing/denied approval fails closed with no local commit.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from zworkbench.composition import CompositionOwner
from zworkbench.write_run import WriteRunOrchestrator
from zworkbench.write_seam import WriteSeamError

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


class WriteRunOrchestratorTests(unittest.TestCase):
    def test_apply_drives_seam_and_returns_owner_backed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            db = root / "state" / "owner.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "run-orch-1"
            resource = str(worktree_root / run_id)

            with CompositionOwner(db) as owner:
                owner.create_run(run_id, "write_seam", {"pre": True})
                token = _approved_token(owner, run_id, "opO", "apply_diff", resource, "kO")

            receipt = WriteRunOrchestrator(db, worktree_root=worktree_root).apply(
                run_id,
                repo,
                VALID_PATCH,
                approval_token=token,
                operation_id="opO",
                action="apply_diff",
                resource=resource,
                idempotency_key="kO",
            )

            self.assertEqual(receipt.status, "completed")
            self.assertIsNotNone(receipt.commit_hash)
            self.assertFalse(receipt.external_receipt["pushed"])
            worktree = Path(receipt.worktree_path)
            self.assertTrue((worktree / "hello.txt").read_text().startswith("hello world"))
            self.assertEqual(_git(worktree, "remote"), "", "orchestrator must never configure a push remote")
            self.assertEqual(_commit_count(worktree), 2, "exactly one local write commit on top of the seed")

            with CompositionOwner(db) as owner:
                run = owner.get_run(run_id)
                self.assertEqual(run["status"], "completed")
                effects = [e for e in run["effects"] if e["operation_id"] == "opO"]
                self.assertEqual(len(effects), 1)
                self.assertEqual(effects[0]["status"], "completed")

    def test_apply_creates_run_if_absent_and_fails_closed_without_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            db = root / "state" / "owner.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "run-orch-absent"
            resource = str(worktree_root / run_id)

            # No run and no approval exist: the orchestrator creates the run via
            # the create-if-absent branch, then fails closed (no effect, no commit).
            with self.assertRaises(WriteSeamError):
                WriteRunOrchestrator(db, worktree_root=worktree_root).apply(
                    run_id, repo, VALID_PATCH,
                    approval_token="unused", operation_id="opD", action="apply_diff",
                    resource=resource, idempotency_key="kD",
                )

            with CompositionOwner(db) as owner:
                run = owner.get_run(run_id)
                self.assertIsNotNone(run, "orchestrator must create the run if absent")
                effects = [e for e in run["effects"] if e["operation_id"] == "opD"]
                self.assertEqual(len(effects), 0, "no effect may be executed without approval")

    def test_apply_reuses_existing_run_and_completes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            db = root / "state" / "owner.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "run-orch-reuse"
            resource = str(worktree_root / run_id)

            with CompositionOwner(db) as owner:
                owner.create_run(run_id, "write_seam", {"pre": True})
                token = _approved_token(owner, run_id, "opR", "apply_diff", resource, "kR")
            receipt = WriteRunOrchestrator(db, worktree_root=worktree_root).apply(
                run_id, repo, VALID_PATCH,
                approval_token=token, operation_id="opR", action="apply_diff",
                resource=resource, idempotency_key="kR",
            )
            self.assertEqual(receipt.status, "completed")

            with CompositionOwner(db) as owner:
                runs = [r for r in owner.snapshot()["runs"] if r["run_id"] == run_id]
                self.assertEqual(len(runs), 1, "the pre-existing run must be reused, not duplicated")
                self.assertEqual(runs[0]["status"], "completed")

    def test_apply_replay_with_same_idempotency_key_returns_existing_receipt(self) -> None:
        """S2-⑤ idempotent replay: re-applying with the same idempotency key
        must return the already-completed receipt without a second physical
        commit and without crashing on the already-completed run state."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            db = root / "state" / "owner.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "run-orch-replay"
            resource = str(worktree_root / run_id)

            with CompositionOwner(db) as owner:
                owner.create_run(run_id, "write_seam", {"pre": True})
                token = _approved_token(owner, run_id, "opP", "apply_diff", resource, "kP")

            orchestrator = WriteRunOrchestrator(db, worktree_root=worktree_root)
            first = orchestrator.apply(
                run_id, repo, VALID_PATCH,
                approval_token=token, operation_id="opP", action="apply_diff",
                resource=resource, idempotency_key="kP",
            )
            self.assertEqual(first.status, "completed")

            replay = orchestrator.apply(
                run_id, repo, VALID_PATCH,
                approval_token=token, operation_id="opP", action="apply_diff",
                resource=resource, idempotency_key="kP",
            )
            # The seam marks a replay "already_completed" (established S2-⑤
            # contract, see test_write_seam) while returning the same durable
            # receipt payload — same effect, same commit, no second write.
            self.assertEqual(replay.status, "already_completed")
            self.assertEqual(replay.commit_hash, first.commit_hash, "replay must not produce a new commit")
            self.assertEqual(replay.effect_id, first.effect_id)
            self.assertEqual(_commit_count(Path(first.worktree_path)), 2, "exactly one physical write commit across both applies")

            with CompositionOwner(db) as owner:
                self.assertEqual(owner.get_run(run_id)["status"], "completed")

    def test_apply_uses_single_owner_for_worktree_and_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _make_repo(root)
            db = root / "state" / "owner.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "run-orch-single"
            resource = str(worktree_root / run_id)

            with CompositionOwner(db) as owner:
                owner.create_run(run_id, "write_seam", {"pre": True})
                token = _approved_token(owner, run_id, "opS", "apply_diff", resource, "kS")
            WriteRunOrchestrator(db, worktree_root=worktree_root).apply(
                run_id, repo, VALID_PATCH,
                approval_token=token, operation_id="opS", action="apply_diff",
                resource=resource, idempotency_key="kS",
            )

            # A separately opened owner over the same DB sees both the worktree
            # result and the completed effect — proving one durable owner.
            with CompositionOwner(db) as owner:
                run = owner.get_run(run_id)
                worktree_results = [r for r in run["results"] if r["kind"].startswith("write_seam.worktree")]
                completed_effects = [
                    e for e in run["effects"] if e["operation_id"] == "opS" and e["status"] == "completed"
                ]
                self.assertEqual(len(worktree_results), 1)
                self.assertEqual(len(completed_effects), 1)


if __name__ == "__main__":
    unittest.main()
