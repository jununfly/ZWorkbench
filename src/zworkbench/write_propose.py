"""Single-session write entry helpers (`write propose`).

Motivation (ADR 0009 write boundary; formerly roadmap 1-10-6 §9.2): the measured product path spent one extra
full LLM session (`zworkbench run` read-only analysis) BEFORE the writing
session.  This module merges the two phases into ONE ``codex exec`` session
that writes directly in a disposable worktree; the resulting unified diff is
saved case-locally and bound to a PENDING owner approval.  Approval is async
by construction: the human later runs ``write approve`` + ``write apply``,
so the human wait never enters the propose wall-clock.

Fail-closed rules:
  - the provider config comes ONLY from the single-source file, staged into
    CODEX_HOME byte-for-byte; no credential value is read or printed here;
  - an empty diff never reaches request-approval (there would be nothing to
    apply and the seam would mark the effect uncertain);
  - push is never performed here (S4 is the separate gate, off by default);
  - case-locality of every durable path is validated by the CLI layer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class ProposeError(RuntimeError):
    """Raised when the propose session cannot produce a usable diff."""


def stage_codex_home(provider_config_path: os.PathLike[str] | str, code_home: os.PathLike[str] | str) -> Path:
    """Stage the single-source provider config into ``CODEX_HOME/config.toml``.

    The file is copied byte-for-byte (this is exactly what ``zworkbench run``
    does internally via the codex adapter), so the inline bearer token is read
    natively by codex and never passes through Python.
    """

    src = Path(provider_config_path)
    if not src.is_file():
        raise ProposeError(
            "single-source provider config not found: {0}".format(src))
    dst = Path(code_home)
    dst.mkdir(parents=True, exist_ok=True)
    target = dst / "config.toml"
    shutil.copyfile(src, target)
    return dst


def generate_proposed_diff(
    repo: os.PathLike[str] | str,
    codex_bin: str,
    prompt: str,
    scratch: os.PathLike[str] | str,
    code_home: os.PathLike[str] | str,
    *,
    sandbox: str = "danger-full-access",
    timeout: float = 1800.0,
) -> str:
    """Run ONE codex exec session in a fresh worktree and return its diff.

    The worktree at ``scratch`` is created from the repo HEAD; codex writes
    inside it; the captured unified diff (vs the original HEAD, including new
    files) is returned as text.  The caller owns scratch cleanup.
    """

    repo = Path(repo)
    scratch = Path(scratch)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(scratch), "HEAD"],
        check=True,
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(code_home)
    try:
        result = subprocess.run(
            [codex_bin, "exec", "--skip-git-repo-check", "--sandbox", sandbox, prompt],
            cwd=str(scratch), env=env, timeout=timeout,
        )
        if result.returncode != 0:
            raise ProposeError(
                "codex exec failed rc={0} after one session".format(result.returncode))
        subprocess.run(["git", "-C", str(scratch), "add", "-A"], check=True)
        patch = subprocess.run(
            ["git", "-C", str(scratch), "diff", "--cached", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
    finally:
        remove_worktree(repo, scratch)
    return patch


def remove_worktree(repo: os.PathLike[str] | str, path: os.PathLike[str] | str) -> None:
    """Best-effort force removal of a disposable worktree."""

    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
        stderr=subprocess.DEVNULL,
    )
