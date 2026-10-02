"""End-to-end CLI tests for the S2 write boundary (roadmap 1-7-6).

These guard that the control-plane `write` command group drives the owner-backed
write seam: request-approval, approve (token never persisted), and apply
(local commit only, push off, case-local fail-closed).
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from zworkbench.cli import CLI_SCHEMA, main
from zworkbench.composition import CompositionOwner

VALID_PATCH = (
    "diff --git a/hello.txt b/hello.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/hello.txt\n"
    "@@ -0,0 +1,1 @@\n"
    "+hello world\n"
)


class ZWorkbenchCliWriteTests(unittest.TestCase):
    def _run(self, arguments: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(arguments)
        return status, json.loads(output.getvalue())

    def _make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        for command in (
            ["init", "-q"],
            ["config", "user.email", "test@zworkbench.local"],
            ["config", "user.name", "ZWorkbench Test"],
            ["config", "commit.gpgsign", "false"],
        ):
            subprocess.run(["git", "-C", str(repo), *command], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return repo

    def _request_and_approve(self, root: Path, db: Path, run_id: str, operation_id: str, resource: str, idempotency_key: str):
        status, req = self._run([
            "write", "request-approval",
            "--db", str(db), "--case-root", str(root),
            "--run-id", run_id, "--operation-id", operation_id,
            "--resource", resource, "--idempotency-key", idempotency_key,
        ])
        self.assertEqual(status, 0, req)
        status, ap = self._run([
            "write", "approve",
            "--db", str(db), "--case-root", str(root),
            "--approval-id", req["approval_id"],
        ])
        self.assertEqual(status, 0, ap)
        return ap["token"]

    def test_write_apply_end_to_end_with_approved_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._make_repo(root)
            db = root / "state" / "composition.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "cli-write-1"
            operation_id = "op-cli-1"
            resource = str(worktree_root / run_id)
            idempotency_key = "k-cli-1"

            token = self._request_and_approve(root, db, run_id, operation_id, resource, idempotency_key)

            diff_path = root / "patch.diff"
            diff_path.write_text(VALID_PATCH, encoding="utf-8")

            status, payload = self._run([
                "write", "apply",
                "--db", str(db), "--case-root", str(root),
                "--repo", str(repo), "--worktree-root", str(worktree_root),
                "--run-id", run_id, "--diff", str(diff_path),
                "--approval-token", token,
                "--operation-id", operation_id,
                "--resource", resource,
                "--idempotency-key", idempotency_key,
            ])

            self.assertEqual(status, 0, payload)
            self.assertEqual(payload["schema"], CLI_SCHEMA)
            self.assertEqual(payload["status"], "completed")
            receipt = payload["receipt"]
            self.assertEqual(receipt["status"], "completed")
            self.assertFalse(receipt["external_receipt"]["pushed"], "S2 write apply must never push")
            self.assertIsNotNone(receipt["commit_hash"])
            worktree = Path(receipt["worktree_path"])
            self.assertTrue((worktree / "hello.txt").exists())
            remote = subprocess.run(
                ["git", "-C", str(worktree), "remote"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ).stdout.strip()
            self.assertEqual(remote, "", "write apply must never configure a push remote")

            with CompositionOwner(db) as owner:
                self.assertEqual(owner.get_run(run_id)["status"], "completed")
                self.assertEqual(len(owner.snapshot()["effects"]), 1)

    def test_write_apply_denied_without_approved_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._make_repo(root)
            db = root / "state" / "composition.sqlite3"
            worktree_root = root / "worktrees"
            run_id = "cli-write-denied"
            resource = str(worktree_root / run_id)
            diff_path = root / "patch.diff"
            diff_path.write_text(VALID_PATCH, encoding="utf-8")

            status, payload = self._run([
                "write", "apply",
                "--db", str(db), "--case-root", str(root),
                "--repo", str(repo), "--worktree-root", str(worktree_root),
                "--run-id", run_id, "--diff", str(diff_path),
                "--approval-token", "bogus-token",
                "--operation-id", "opX", "--resource", resource,
                "--idempotency-key", "kX",
            ])

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")

    def test_write_approve_token_redacted_in_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._make_repo(root)
            db = root / "state" / "composition.sqlite3"
            run_id = "cli-write-tok"
            resource = str(root / "wt" / run_id)

            status, req = self._run([
                "write", "request-approval",
                "--db", str(db), "--case-root", str(root),
                "--run-id", run_id, "--operation-id", "opT",
                "--resource", resource, "--idempotency-key", "kT",
            ])
            self.assertEqual(status, 0, req)

            summary = root / "summary.json"
            status, ap = self._run([
                "write", "approve",
                "--db", str(db), "--case-root", str(root),
                "--approval-id", req["approval_id"],
                "--summary", str(summary),
            ])
            self.assertEqual(status, 0, ap)
            self.assertTrue(ap["token"], "the one-use token must be shown on stdout")

            saved = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(saved["token"], "<redacted>", "bearer token must never be persisted in plaintext")

    def test_write_apply_case_local_boundary_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external:
            root = Path(temporary)
            repo = self._make_repo(root)
            db = root / "state" / "composition.sqlite3"
            worktree_root = Path(external) / "worktrees"  # outside case-root
            run_id = "cli-write-boundary"
            resource = str(worktree_root / run_id)
            diff_path = root / "patch.diff"
            diff_path.write_text(VALID_PATCH, encoding="utf-8")

            status, payload = self._run([
                "write", "apply",
                "--db", str(db), "--case-root", str(root),
                "--repo", str(repo), "--worktree-root", str(worktree_root),
                "--run-id", run_id, "--diff", str(diff_path),
                "--approval-token", "x", "--operation-id", "opB",
                "--resource", resource, "--idempotency-key", "kB",
            ])

            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertEqual(payload["violations"][0]["code"], "cli_path_outside_case_root")
            self.assertFalse(db.exists(), "a denied apply must not create owner state")

    def test_write_request_approval_records_pending_in_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = self._make_repo(root)
            db = root / "state" / "composition.sqlite3"
            run_id = "cli-write-pending"
            resource = str(root / "wt" / run_id)

            status, req = self._run([
                "write", "request-approval",
                "--db", str(db), "--case-root", str(root),
                "--run-id", run_id, "--operation-id", "opP",
                "--resource", resource, "--idempotency-key", "kP",
            ])
            self.assertEqual(status, 0, req)
            self.assertEqual(req["status_detail"], "pending")

            with CompositionOwner(db) as owner:
                approvals = [a for a in owner.snapshot()["approvals"] if a["operation_id"] == "opP"]
                self.assertEqual(len(approvals), 1)
                self.assertEqual(approvals[0]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
