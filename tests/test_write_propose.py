"""Tests for the `write propose` single-session write entry (1-10-6 §9.2).

Covers the fail-closed branches and the happy path with a FAKE codex binary
(no network, no real provider):

* happy path: one session produces a diff, the patch is saved case-locally,
  a PENDING approval is bound, the digest matches the saved patch, the
  disposable scratch worktree is removed;
* empty diff is rejected BEFORE requesting an approval (nothing to apply);
* a missing single-source provider config fails closed;
* case-locality: a db outside the case root is denied.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from zworkbench.cli import main


WRITING_FAKE_CODEX = """#!/bin/sh
echo "proposed by fake codex" > "$PWD/proposed.txt"
"""

IDLE_FAKE_CODEX = """#!/bin/sh
true
"""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _ProposeFixture:
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("demo\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@local"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
        return repo

    def make_fake_codex(self, root: Path, body: str) -> Path:
        executable = root / "fake-codex"
        executable.write_text(body, encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def make_provider_config(self, root: Path) -> Path:
        path = root / "providers.toml"
        path.write_text(
            '[model_providers.fake]\nbase_url = "http://127.0.0.1:1"\n',
            encoding="utf-8",
        )
        return path

    def propose(self, repo: Path, codex: Path, config: Path, **overrides):
        root = repo.parent
        db = overrides.get("db", root / "owner.db")
        argv = [
            "write", "propose",
            "--db", str(db),
            "--case-root", str(overrides.get("case_root", root)),
            "--repo", str(repo),
            "--worktree-root", str(root / "seam-worktrees"),
            "--prompt", overrides.get("prompt", "add one file"),
            "--codex", str(codex),
        ]
        buffer = io.StringIO()
        with patch("zworkbench.cli.PROVIDER_CONFIG_PATH", config), redirect_stdout(buffer):
            status = main(argv)
        return status, buffer.getvalue(), db


class WriteProposeTests(unittest.TestCase):
    def test_happy_path_creates_patch_and_pending_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _ProposeFixture().make_repo(root)
            codex = _ProposeFixture().make_fake_codex(root, WRITING_FAKE_CODEX)
            config = _ProposeFixture().make_provider_config(root)

            status, stdout, db = _ProposeFixture().propose(repo, codex, config)
            self.assertEqual(status, 0, stdout)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertTrue(payload["approval_id"])
            self.assertEqual(payload["approval_status"], "pending")
            self.assertEqual(payload["operation_id"], "apply-" + payload["run_id"])

            # the patch is saved case-locally and the digest matches it
            patch_path = Path(payload["patch_path"])
            self.assertTrue(patch_path.is_file())
            self.assertIn("proposed by fake codex", patch_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["diff_digest"], _sha256_text(patch_path.read_text(encoding="utf-8")))

            # the approval is durably pending in the owner db
            con = sqlite3.connect(db)
            rows = list(con.execute("SELECT status FROM approvals"))
            con.close()
            self.assertEqual([r[0] for r in rows], ["pending"])

            # the disposable scratch worktree was removed
            scratch = root / ".zw-propose" / "scratch"
            leftovers = [p.name for p in scratch.iterdir()] if scratch.is_dir() else []
            self.assertEqual(leftovers, [])

    def test_empty_diff_is_rejected_before_requesting_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _ProposeFixture().make_repo(root)
            codex = _ProposeFixture().make_fake_codex(root, IDLE_FAKE_CODEX)
            config = _ProposeFixture().make_provider_config(root)

            status, stdout, db = _ProposeFixture().propose(repo, codex, config)
            self.assertEqual(status, 1, stdout)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "empty_diff")

            # no approval was ever requested: the db has no approvals table
            # (the test connection itself may create the empty file)
            if db.is_file():
                con = sqlite3.connect(db)
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                con.close()
                self.assertNotIn("approvals", tables)

    def test_missing_provider_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = _ProposeFixture().make_repo(root)
            codex = _ProposeFixture().make_fake_codex(root, WRITING_FAKE_CODEX)
            missing = root / "no-such-providers.toml"

            status, stdout, _ = _ProposeFixture().propose(repo, codex, missing)
            self.assertEqual(status, 1, stdout)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "provider_config_missing")

    def test_db_outside_case_root_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = Path(tempfile.mkdtemp())
            repo = _ProposeFixture().make_repo(root)
            codex = _ProposeFixture().make_fake_codex(root, WRITING_FAKE_CODEX)
            config = _ProposeFixture().make_provider_config(root)

            status, stdout, _ = _ProposeFixture().propose(
                repo, codex, config, db=outside / "outside.db")
            self.assertEqual(status, 2, stdout)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "denied")


if __name__ == "__main__":
    unittest.main()
