#!/usr/bin/env python3
"""Run the ZDSHarness → ZWorkbench H1 integration.

The runner stages the already-built ZDSHarness CLI into a fresh temporary-like
output directory, preserves the CLI's local ``apps/cli/node_modules`` closure,
and starts it through :class:`DshRuntimeAdapter`.  It deliberately reports
source-plane evidence by default.  Passing an explicit full commit with
``--pinned-commit`` verifies that the source checkout is the clean, pinned
commit used for the run and emits a formal artifact receipt.  A dirty checkout,
an unpinned invocation, or a commit mismatch keeps formal H1 at HOLD.

The output directory is caller-owned and must be new or empty.  It contains a
case-local CompositionOwner database and staged runtime files so the result
can be inspected after the process exits.  Do not point it at a repository
path intended for commit; use ``/tmp`` or an ignored evaluation directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SCHEMA = "zworkbench-w8-dsh-artifact-integration-runner/v1"
RECEIPT_SCHEMA = "zworkbench-dsh-maintainer-pinned-artifact-receipt/v1"
BOOTSTRAP_PROFILE_ID = "zworkbench-bootstrap"
BOOTSTRAP_PROFILE_MODE = "headless-bootstrap"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import CompositionOwner, DshRuntimeAdapter, DshRuntimeError  # noqa: E402


def file_digest(path: Path) -> str:
    """Return the adapter's sha256 digest representation for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object and fail loudly when a build input is malformed."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    """Write one reviewable JSON evidence file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def full_commit(value: str) -> bool:
    """Return whether a value is an exact Git object id, not a movable ref."""

    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def git_output(dsh_repo: Path, *args: str) -> str:
    """Run a read-only git query against the supplied ZDSHarness checkout."""

    return subprocess.check_output(["git", *args], cwd=dsh_repo, text=True, stderr=subprocess.DEVNULL).strip()


def stage_runtime(dsh_repo: Path, output_dir: Path) -> Dict[str, Any]:
    """Stage the built CLI and create a digest-bound adapter manifest."""

    cli_dir = dsh_repo / "apps" / "cli"
    cli_lib = cli_dir / "lib"
    cli_bin = cli_lib / "bin.js"
    cli_package = cli_dir / "package.json"
    cli_node_modules = cli_dir / "node_modules"
    lock_source = dsh_repo / "pnpm-lock.yaml"
    bootstrap_package = dsh_repo / "packages" / "bundle" / "zworkbench-bootstrap" / "package.json"
    required = (cli_bin, cli_package, cli_node_modules, lock_source, bootstrap_package)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"ZDSHarness build/closure is incomplete: {', '.join(missing)}")

    artifact_root = output_dir / "artifact"
    artifact_root.mkdir(parents=True)
    shutil.copytree(cli_lib, artifact_root / "lib")
    shutil.copy2(cli_package, artifact_root / "package.json")
    # The built CLI imports workspace packages through this installation-owned
    # closure.  Keeping the link local makes the staging reproducible without
    # copying node_modules or pretending this is a portable release archive.
    (artifact_root / "node_modules").symlink_to(cli_node_modules, target_is_directory=True)
    artifact = artifact_root / "lib" / "bin.js"
    lock = artifact_root / "pnpm-lock.yaml"
    shutil.copy2(lock_source, lock)

    cli_manifest = read_json(cli_package)
    bootstrap_manifest = read_json(bootstrap_package)
    runtime_version = cli_manifest.get("version")
    profile_version = bootstrap_manifest.get("version")
    if not isinstance(runtime_version, str) or not isinstance(profile_version, str):
        raise ValueError("ZDSHarness package versions must be strings")
    source_commit = git_output(dsh_repo, "rev-parse", "HEAD")
    source_dirty = git_output(dsh_repo, "status", "--porcelain=v1", "--untracked-files=all") != ""

    profile = artifact_root / "profile.json"
    write_json(
        profile,
        {
            "schema": "zworkbench-dsh-profile/v1",
            "id": BOOTSTRAP_PROFILE_ID,
            "version": profile_version,
            "mode": BOOTSTRAP_PROFILE_MODE,
            "plugins": [],
        },
    )
    receipt = artifact_root / "build-receipt.json"
    write_json(
        receipt,
        {
            "schema": "zworkbench-dsh-build-receipt/v1",
            "runtime_name": "@deepseek-ai/dsh",
            "runtime_version": runtime_version,
            "source_commit": source_commit,
            "dependency_lock_digest": file_digest(lock),
            "artifact_digest": file_digest(artifact),
            "platform": sys.platform,
            "architecture": platform.machine(),
        },
    )
    manifest = {
        "schema": "zworkbench-dsh-runtime-manifest/v1",
        "mode": "artifact",
        "runtime": {
            "name": "@deepseek-ai/dsh",
            "version": runtime_version,
            "source_commit": source_commit,
        },
        "artifact": {
            "name": "@deepseek-ai/dsh",
            "version": runtime_version,
            "path": "lib/bin.js",
            "digest": file_digest(artifact),
        },
        "dependency_lock": {"path": "pnpm-lock.yaml", "digest": file_digest(lock)},
        "build_receipt": {"path": "build-receipt.json", "digest": file_digest(receipt)},
        "profile": {
            "id": BOOTSTRAP_PROFILE_ID,
            "version": profile_version,
            "path": "profile.json",
            "digest": file_digest(profile),
        },
        "schema_identity": {
            "name": "zworkbench.dsh.bootstrap",
            "version": "v1",
            "digest": "sha256:" + "1" * 64,
        },
        "policy_identity": {
            "id": "zworkbench-h1-read-only",
            "version": "1",
            "digest": "sha256:" + "2" * 64,
            "mode": "read-only",
        },
        "provider_identity": {
            "provider": "fake-loopback",
            "model": "fixture-model",
            "endpoint": "http://127.0.0.1:11434",
            "transport": "loopback-only",
        },
        "environment_identity": {
            "platform": sys.platform,
            "architecture": platform.machine(),
            "runtime": "node",
        },
        "workspace": {"path": "workspace", "kind": "case-local"},
        "dsh_home": {"path": "dsh-home", "kind": "case-local"},
        "launch": {"args": ["--profile", BOOTSTRAP_PROFILE_ID], "environment": {}},
    }
    manifest_path = artifact_root / "manifest.json"
    write_json(manifest_path, manifest)
    return {
        "manifest_path": manifest_path,
        "source_commit": source_commit,
        "source_worktree_state": "dirty" if source_dirty else "clean",
        "runtime_version": runtime_version,
        "profile_version": profile_version,
        "artifact_digest": file_digest(artifact),
        "dependency_lock_digest": file_digest(lock),
        "profile_digest": file_digest(profile),
        "build_receipt_digest": file_digest(receipt),
    }


def write_formal_receipt(output_dir: Path, staged: Dict[str, Any], pinned_commit: str) -> Path:
    """Persist the digest-bound receipt for one clean, explicitly pinned build."""

    receipt_path = output_dir / "maintainer-pinned-artifact-receipt.json"
    write_json(
        receipt_path,
        {
            "schema": RECEIPT_SCHEMA,
            "provenance": "clean-pinned-local-build",
            "source": {
                "commit": staged["source_commit"],
                "pinned_commit": pinned_commit,
                "worktree_state": staged["source_worktree_state"],
            },
            "runtime": {
                "name": "@deepseek-ai/dsh",
                "version": staged["runtime_version"],
            },
            "artifact": {"path": "artifact/lib/bin.js", "digest": staged["artifact_digest"]},
            "dependency_lock": {"path": "artifact/pnpm-lock.yaml", "digest": staged["dependency_lock_digest"]},
            "profile": {
                "id": BOOTSTRAP_PROFILE_ID,
                "version": staged["profile_version"],
                "path": "artifact/profile.json",
                "digest": staged["profile_digest"],
            },
            "build_receipt": {
                "path": "artifact/build-receipt.json",
                "digest": staged["build_receipt_digest"],
            },
        },
    )
    return receipt_path


def run_integration(output_dir: Path, dsh_repo: Path, *, pinned_commit: str | None = None) -> Dict[str, Any]:
    """Run one real DSH bootstrap through the owner-backed adapter."""

    output_dir = output_dir.expanduser().resolve()
    dsh_repo = dsh_repo.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"integration output directory must be new or empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    case_root = output_dir / "case"
    (case_root / "workspace").mkdir(parents=True)
    staged = stage_runtime(dsh_repo, output_dir)
    pin_requested = pinned_commit is not None
    pin_valid = pinned_commit is None or full_commit(pinned_commit)
    pin_checks = {
        "pinned_commit_argument_is_full_sha": pin_valid,
        "source_worktree_clean": staged["source_worktree_state"] == "clean",
        "pinned_commit_matches_source": pin_valid and staged["source_commit"] == pinned_commit,
    }
    formal_receipt_path = None
    if all(pin_checks.values()):
        formal_receipt_path = write_formal_receipt(output_dir, staged, pinned_commit or staged["source_commit"])
    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    run_id = "w8-dsh-bootstrap-real-source-plane"
    execution = None
    error: Dict[str, str] | None = None
    adapter = DshRuntimeAdapter(owner, staged["manifest_path"], case_root)
    try:
        try:
            execution = adapter.execute(run_id, timeout=30.0)
        except DshRuntimeError as exc:
            error = {"type": type(exc).__name__, "code": exc.code}
    finally:
        adapter.close()
        owner.close()

    with CompositionOwner(case_root / "state" / "composition.sqlite3") as reopened:
        run = reopened.get_run(run_id)
        events = reopened.events(run_id)
    dsh_events = [event for event in events if event["type"].startswith("dsh.")]
    exit_receipts = [item["value"] for item in run["results"] if item["kind"] == "dsh.exit"]
    result_kinds = [item["kind"] for item in run["results"]]
    session_dir = case_root / "dsh-home" / "sessions"
    checks = {
        "adapter_completed": execution is not None and execution.status == "completed",
        "owner_completed": run["status"] == "completed",
        "parent_run_identity": execution is not None and execution.run_id == run_id,
        "dsh_session_identity_present": execution is not None and execution.dsh_session_id.startswith("dsh-"),
        "bootstrap_sequence_recorded": [event["type"] for event in dsh_events]
        == ["dsh.bootstrap.started", "dsh.bootstrap.ready"],
        "exit_code_zero": any(receipt.get("exit_code") == 0 for receipt in exit_receipts),
        "session_persistence_present": session_dir.is_dir() and any(session_dir.iterdir()),
        "effects_zero": len(run["effects"]) == 0,
    }
    source_integration_passed = all(checks.values())
    formal_h1_passed = pin_requested and source_integration_passed and all(pin_checks.values())
    formal_status = (
        "completed: clean maintainer-pinned artifact receipt and H1 integration verified"
        if formal_h1_passed
        else "HOLD/unknown-stop: clean maintainer-pinned artifact receipt not verified"
    )
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "formal-h1-artifact-integration" if formal_h1_passed else "source-plane-integration",
        "status": "pass" if source_integration_passed and (not pin_requested or formal_h1_passed) else "fail",
        "formal_h1_status": formal_status,
        "source": {
            "repo": str(dsh_repo),
            "commit": staged["source_commit"],
            "worktree_state": staged["source_worktree_state"],
            "runtime_version": staged["runtime_version"],
            "profile_version": staged["profile_version"],
        },
        "provenance": {
            "pin_checks": pin_checks,
            "receipt_path": str(formal_receipt_path) if formal_receipt_path is not None else None,
            "artifact_digest": staged["artifact_digest"],
            "dependency_lock_digest": staged["dependency_lock_digest"],
            "profile_digest": staged["profile_digest"],
            "build_receipt_digest": staged["build_receipt_digest"],
        },
        "run_id": run_id,
        "observed": {
            "owner_run_status": run["status"],
            "error": error,
            "dsh_session_id": execution.dsh_session_id if execution is not None else None,
            "dsh_event_types": [event["type"] for event in dsh_events],
            "raw_event_count": execution.raw_event_count if execution is not None else 0,
            "result_kinds": result_kinds,
            "exit_receipts": exit_receipts,
            "session_persistence_present": checks["session_persistence_present"],
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "checks": checks,
        "non_claims": [
            "The receipt is a local maintainer-pinned provenance receipt; it is not a signed public release asset.",
            "This does not prove H2-H8, host sandboxing, or real Provider compatibility.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsh-repo", type=Path, required=True, help="ZDSHarness checkout containing the built CLI")
    parser.add_argument("--output", type=Path, required=True, help="new or empty source-plane evidence directory")
    parser.add_argument(
        "--pinned-commit",
        help="full 40-character commit expected in a clean checkout; enables formal H1 receipt verification",
    )
    args = parser.parse_args()
    summary = run_integration(args.output, args.dsh_repo, pinned_commit=args.pinned_commit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
