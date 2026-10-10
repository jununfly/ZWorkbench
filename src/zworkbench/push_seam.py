"""Push seam — the separate S4 gate for the hard-to-undo ``git push``.

S4 productizes the third blast-radius grade (R3 「写操作爆炸半径分级」):
``apply`` (revertible) -> ``commit`` (resettable) -> ``push`` (hard to undo).
S2 implemented the first two inside :mod:`write_seam`; push is a *separate*
gate that is **off by default** and must be explicitly enabled.  The seam is
physically isolated from :mod:`write_seam` so that the ``apply`` run never
acquires a network/credential execution path — reading ``write_seam.py``
source proves there is no ``push`` execution surface (guarded by a static
test).

The seam is stateless across runs except for the single
:class:`~zworkbench.composition.CompositionOwner` it is given.  Three locks
keep push inert unless deliberately opened:

* Lock 1 (library default): ``PushSeam(push_enabled=False)`` refuses to claim
  an effect at all — no approval token is consumed and no effect row is
  created.
* Lock 2 (CLI gate): the ``zworkbench write push`` subcommand requires an
  explicit ``--push-gate`` flag; without it the command is denied.
* Lock 3 (separate approval): push carries its own operation/action/resource/
  idempotency key and one-use token; it never reuses the ``apply`` approval.

Credential discipline: the CLI accepts *only* a remote **name** (never a URL
or path literal), so no credential can enter through ``argv``.  The remote URL
is read from the local repo's own configuration (ambient git credentials /
SSH agent); the receipt records ``credential_source=ambient`` and stores the
URL with userinfo stripped plus a sha256 digest of the full URL — no secret
ever lands in durable owner state.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from .composition import CompositionOwner


PUSH_SEAM_SCHEMA = "zworkbench-push-seam/v1"
#: S4 push effects require an explicit, approved token bound to the same
#: operation/action/resource/idempotency key (``approval-required``).
EFFECT_CLASS_PUSH = "approval-required"
#: Push declares the three capabilities that an apply effect does NOT.
PUSH_EXPOSURE = {
    "network": True,
    "credentials": True,
    "subprocess": True,
}


class PushSeamError(RuntimeError):
    """Base error for the push seam."""


class PushDisabledError(PushSeamError):
    """Raised when push is disabled (lock 1): no token consumed, no effect."""


class PushPrecheckError(PushSeamError):
    """A-class failure: a pre-push precondition was violated.

    Raised *after* the effect is reconciled as ``not-applied`` so the operator
    can retry with a fresh approval (bounded retry).  No physical push happened.
    """


class PushUncertainError(PushSeamError):
    """B-class failure: a push command was issued but the outcome is unknown.

    Raised *after* the effect is marked uncertain and the run is moved to
    ``recovering``.  Never silently retried — an irreversible action with no
    deterministic proof of success must not be assumed to have failed.
    """


@dataclass(frozen=True)
class PushReceipt:
    """The bounded, owner-backed outcome of one push effect."""

    effect_id: str
    status: str
    remote: str
    ref: str
    expect_commit: str
    pushed: bool
    physical_push_performed: bool
    noop: bool
    external_receipt: Mapping[str, Any]


class PushSeam:
    """Push a known local commit to a named remote ref, behind the S4 gate.

    The seam is stateless across runs except for the owner it is given.  It
    never opens a second owner database and it never performs a ``git push``
    unless ``push_enabled`` is true AND the CLI gate is present.
    """

    SCHEMA = PUSH_SEAM_SCHEMA

    def __init__(
        self,
        owner: CompositionOwner,
        *,
        push_enabled: bool = False,
        case_root: Path | str | None = None,
    ) -> None:
        self.owner = owner
        # Lock 1: off by default.  The CLI / orchestrator must opt in.
        self.push_enabled = push_enabled
        self.case_root = Path(case_root).expanduser().resolve() if case_root is not None else None

    # ------------------------------------------------------------------
    # Push (S4)
    # ------------------------------------------------------------------

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
        """Claim, verify custody and blast-radius, then push one commit.

        The effect is ``approval-required`` and carries its own operation/action/
        resource/idempotency key (lock 3).  Idempotency is enforced twice: the
        owner returns the already-completed receipt on a same-key replay
        (physical push at most once), and a cross-process probe before any
        physical push skips the push when the remote ref already points at
        ``expect_commit`` (so a crash/restart cannot produce a second physical
        side effect).

        Failure semantics:
        * A-class (pre-push preconditions: remote missing, ref not a branch,
          HEAD != expect_commit, custody mismatch) -> reconcile as ``not-applied``
          and raise :class:`PushPrecheckError`; the effect stays retryable and no
          physical push happens.
        * B-class (a push command was issued but the outcome is undetermined: git
          non-zero, timeout, or the post-push probe disagrees) -> mark uncertain
          and raise :class:`PushUncertainError`; the run moves to ``recovering``
          and is never silently retried.
        """

        if not self.push_enabled:
            # Lock 1: refuse before claiming — no token consumed, no effect row.
            raise PushDisabledError("push is disabled; enable the S4 gate explicitly")

        repo = Path(repo).expanduser().resolve()

        # Q4 preflight: declare this run's exposure.  Push needs the network,
        # ambient credentials, and a git subprocess; unlike apply it does NOT
        # declare an isolated worktree write-only boundary.  The resource
        # (the local repo holding the commit) is bounded to the case root when
        # one is configured.
        self.owner.declare_exposure(
            run_id,
            declared_side_effects=[EFFECT_CLASS_PUSH],
            exposure={
                "workspace_root": str(self.case_root) if self.case_root is not None else str(repo),
                "network": True,
                "credentials": True,
                "subprocess": True,
            },
        )
        claim = self.owner.claim_effect(
            run_id,
            operation_id,
            action,
            resource,
            idempotency_key,
            EFFECT_CLASS_PUSH,
            approval_token=approval_token,
            required_exposure={"network", "credentials", "subprocess"},
        )
        if not claim.executable:
            existing = self._completed_receipt(run_id, operation_id)
            if existing is not None:
                return existing
            raise PushSeamError(f"effect not executable: {claim.reason}")

        effect_id = claim.effect_id
        assert effect_id is not None

        # ---- A-class pre-push preconditions (no physical push yet) ----------
        normalized_ref = self._normalize_ref(ref, repo)
        if normalized_ref is None:
            # ref is not a branch (tag / deletion / dash-prefixed / unknown).
            self._reconcile_not_applied(effect_id, {"reason": "ref_not_a_branch", "ref": ref})
            raise PushPrecheckError(f"ref {ref!r} is not a branch (refs/heads/<branch> only)")

        if not self._validate_remote_name(remote):
            self._reconcile_not_applied(effect_id, {"reason": "remote_not_a_name", "remote": remote})
            raise PushPrecheckError(f"remote {remote!r} must be a remote name, not a URL or path literal")

        remote_url = self._remote_get_url(repo, remote)
        if remote_url is None:
            # git remote get-url failed: the remote does not exist.
            self._reconcile_not_applied(effect_id, {"reason": "remote_not_found", "remote": remote})
            raise PushPrecheckError(f"remote {remote!r} is not configured in {repo}")

        head = _git(repo, ["rev-parse", "HEAD"]).strip()
        if head != expect_commit:
            self._reconcile_not_applied(
                effect_id, {"reason": "head_mismatch", "head": head, "expect_commit": expect_commit},
            )
            raise PushPrecheckError(f"repo HEAD {head} != expect_commit {expect_commit}")

        if not self._custody_matches(run_id, source_run_id, apply_operation_id, expect_commit):
            self._reconcile_not_applied(
                effect_id, {"reason": "custody_mismatch", "source_run_id": source_run_id,
                            "apply_operation_id": apply_operation_id, "expect_commit": expect_commit},
            )
            raise PushPrecheckError(
                f"upstream apply receipt for {source_run_id}/{apply_operation_id} does not commit {expect_commit}"
            )

        # ---- Cross-process idempotency probe --------------------------------
        branch = normalized_ref.split("/", 2)[2]  # refs/heads/<branch>
        remote_before = self._ls_remote(repo, remote, normalized_ref)
        noop = remote_before == expect_commit
        physical_push_performed = False

        if noop:
            # The target object is already at the remote ref (someone else
            # pushed it, a prior crash that did push, or a replay).  Skip the
            # physical push so we never produce a second side effect.
            pushed = True
        else:
            # ---- Physical push (B-class guard) -----------------------------
            try:
                self._git_push(repo, remote, expect_commit, branch, remote_before if force_with_lease else None)
            except subprocess.CalledProcessError as exc:
                self.owner.mark_effect_uncertain(
                    effect_id,
                    {"error": str(exc), "stage": "push", "forced": force_with_lease,
                     "remote_before": remote_before},
                )
                raise PushUncertainError(f"git push failed (outcome uncertain): {exc}") from exc

            # Deterministic verification: the remote ref must now report the
            # exact object we pushed.  Anything else is B-class uncertain.
            remote_after = self._ls_remote(repo, remote, normalized_ref)
            if remote_after != expect_commit:
                self.owner.mark_effect_uncertain(
                    effect_id,
                    {"stage": "verify", "remote_before": remote_before,
                     "remote_after": remote_after, "expect_commit": expect_commit},
                )
                raise PushUncertainError(
                    f"push verification failed: remote {normalized_ref} is {remote_after}, expected {expect_commit}"
                )
            pushed = True
            physical_push_performed = True

        anonymous_url, url_digest = _strip_userinfo(remote_url)
        external_receipt = {
            "schema": PUSH_SEAM_SCHEMA,
            "operation": action,
            "operation_id": operation_id,
            "action": action,
            "resource": resource,
            "idempotency_key": idempotency_key,
            "remote": remote,
            "remote_url_anonymous": anonymous_url,
            "remote_url_sha256": url_digest,
            "ref": normalized_ref,
            "expect_commit": expect_commit,
            "head_at_push": head,
            "pushed": pushed,
            "physical_push_performed": physical_push_performed,
            "noop": noop,
            "force_with_lease": force_with_lease,
            "credential_source": "ambient",
            "source_run_id": source_run_id,
            "apply_operation_id": apply_operation_id,
        }
        self.owner.complete_effect(
            effect_id,
            {"remote": remote, "ref": normalized_ref, "expect_commit": expect_commit,
             "physical_push_performed": physical_push_performed, "noop": noop},
            external_receipt,
        )
        return PushReceipt(
            effect_id=effect_id,
            status="completed",
            remote=remote,
            ref=normalized_ref,
            expect_commit=expect_commit,
            pushed=pushed,
            physical_push_performed=physical_push_performed,
            noop=noop,
            external_receipt=external_receipt,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_ref(ref: str, repo: Path) -> Optional[str]:
        """Return ``refs/heads/<branch>`` for a branch ref, else ``None``.

        Only branch refs are pushed (tag / deletion / dash-prefixed refs are
        rejected).  A bare branch name or ``HEAD`` (resolved to the current
        branch) is accepted; anything else returns ``None``.
        """

        if ref.startswith("refs/heads/"):
            return ref
        if ref in {"", "-", "--", "refs/tags/", "refs/"}:
            return None
        if ref.startswith("refs/tags/") or ref.startswith("-") or ref.startswith("refs/"):
            # tags, deletion specs, and any non-head ref are rejected
            return None
        if "/" in ref:
            # looks like a full ref we do not accept, or a remote/branch pair
            return None
        # Bare branch name: validate it exists locally before accepting.
        try:
            _git(repo, ["show-ref", "--verify", f"refs/heads/{ref}"])
            return f"refs/heads/{ref}"
        except subprocess.CalledProcessError:
            return None

    @staticmethod
    def _validate_remote_name(remote: str) -> bool:
        """True when ``remote`` is a remote *name*, never a URL or path literal."""

        if not remote or any(ch in remote for ch in (" ", "\t", "\n")):
            return False
        if "://" in remote:
            return False
        if remote.startswith(("/", "./", "../", "~")):
            return False
        # A colon in the middle of the string is characteristic of a scp-like URL
        # or a path literal; remote names contain no colon.
        if ":" in remote:
            return False
        return True

    @staticmethod
    def _remote_get_url(repo: Path, remote: str) -> Optional[str]:
        """Return the configured URL for ``remote``, or ``None`` if absent."""

        try:
            return _git(repo, ["remote", "get-url", remote]).strip()
        except subprocess.CalledProcessError:
            return None

    @staticmethod
    def _ls_remote(repo: Path, remote: str, ref: str) -> Optional[str]:
        """Return the SHA the remote reports for ``ref``, or ``None`` if absent."""

        try:
            out = _git(repo, ["ls-remote", remote, ref]).strip()
        except subprocess.CalledProcessError:
            return None
        if not out:
            return None
        # Lines look like "<sha>\t<ref>"; take the first token of the first line.
        return out.splitlines()[0].split("\t", 1)[0].strip() or None

    def _git_push(
        self,
        repo: Path,
        remote: str,
        commit: str,
        branch: str,
        lease_expected_oid: Optional[str],
    ) -> None:
        """Issue the physical ``git push`` with the exact refspec.

        ``<commit>:refs/heads/<branch>`` pins the source object so we push exactly
        the approved commit even if HEAD moved.  With a lease we require the
        remote ref to still point at ``lease_expected_oid`` (precise, non-empty
        lease), preventing accidental overwrites.
        """

        refspec = f"{commit}:refs/heads/{branch}"
        args = ["-C", str(repo), "push"]
        if lease_expected_oid is not None:
            args.append(f"--force-with-lease=refs/heads/{branch}:{lease_expected_oid}")
        args.extend([remote, refspec])
        proc = subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return None  # pragma: no cover - typing only

    def _custody_matches(
        self,
        run_id: str,
        source_run_id: str,
        apply_operation_id: str,
        expect_commit: str,
    ) -> bool:
        """Verify the upstream apply receipt committed exactly ``expect_commit``.

        The push is the final link in diff apply -> commit -> push.  It must be
        bound to the apply effect that produced the commit we are about to push,
        so a mismatched or missing upstream receipt fails closed (A-class).
        """

        try:
            source_run = self.owner.get_run(source_run_id)
        except Exception:
            return False
        for effect in source_run.get("effects", []):
            if effect.get("operation_id") == apply_operation_id and effect.get("status") == "completed":
                receipt_commit = (effect.get("external_receipt") or {}).get("commit_hash")
                return receipt_commit == expect_commit
        return False

    def _reconcile_not_applied(self, effect_id: str, detail: Mapping[str, Any]) -> None:
        """Record an A-class precondition failure as retryable (not completed).

        The owner's ``reconcile_effect`` only accepts ``uncertain``/``retryable``,
        so a freshly-claimed effect must first be marked uncertain and then
        reconciled as ``not-applied``.  The final state is ``retryable`` with the
        run returned to ``running`` — no physical push happened, the effect is
        not completed and is not accounted as a success, and the operator can
        retry with a fresh approval (bounded retry).
        """

        self.owner.mark_effect_uncertain(effect_id, detail)
        self.owner.reconcile_effect(effect_id, "not-applied", detail)

    def _completed_receipt(self, run_id: str, operation_id: str) -> Optional[PushReceipt]:
        """Return the durable receipt for an already-completed effect, if any."""

        run = self.owner.get_run(run_id)
        for effect in run.get("effects", []):
            if effect.get("operation_id") == operation_id and effect.get("status") == "completed":
                receipt = effect.get("external_receipt") or {}
                return PushReceipt(
                    effect_id=effect["effect_id"],
                    status="already_completed",
                    remote=receipt.get("remote", ""),
                    ref=receipt.get("ref", ""),
                    expect_commit=receipt.get("expect_commit", ""),
                    pushed=bool(receipt.get("pushed")),
                    physical_push_performed=bool(receipt.get("physical_push_performed")),
                    noop=bool(receipt.get("noop")),
                    external_receipt=receipt,
                )
        return None


def _git(repo: Path, args: list[str]) -> str:
    """Run one git command in ``repo`` and return stdout (utf-8, replace errors)."""

    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _strip_userinfo(url: str) -> tuple[str, str]:
    """Return (anonymous_url, sha256_of_full_url).

    The anonymous URL keeps the scheme/host/path but drops any ``user:pass@``
    so no credential reaches durable owner state; the full URL is reduced to a
    sha256 digest for tamper-evident audit.
    """

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            netloc = parsed.hostname or parsed.netloc
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            anonymous = parsed._replace(netloc=netloc).geturl()
            return anonymous, digest
    except ValueError:
        pass
    # Non-parseable URL (e.g. a local path remote): keep as-is, still digested.
    return url, digest


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "PUSH_SEAM_SCHEMA",
    "EFFECT_CLASS_PUSH",
    "PUSH_EXPOSURE",
    "PushSeamError",
    "PushDisabledError",
    "PushPrecheckError",
    "PushUncertainError",
    "PushReceipt",
    "PushSeam",
]
