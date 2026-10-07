"""The user-facing command line entry point for the first W8 slice.

The CLI is intentionally a thin control-plane layer.  It prepares no global
Codex state, accepts no credential value, and never implements a Harness loop.
Execution is delegated to :class:`LocalReadOnlyRunOrchestrator`; the
composition owner remains the durable source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
import re
import uuid
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .composition import CompositionOwner
from .local_run import (
    LOCAL_READ_ONLY_MODE,
    LocalReadOnlyRunConfig,
    LocalReadOnlyRunOrchestrator,
    PreflightResult,
    PreflightViolation,
    ProviderProfile,
    load_provider_profiles,
    preflight,
)
from .write_run import WriteRunOrchestrator
from .write_seam import WriteSeamError


CLI_SCHEMA = "zworkbench-cli/v1"
LOOPBACK = "127.0.0.1"
#: Addresses that keep the service on this machine. Anything else would put
#: review material, including manifest identity, on the network.
LOOPBACK_ADDRESSES = frozenset({LOOPBACK, "localhost", "::1"})
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}|(?:api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zworkbench",
        description="Controlled local ZWorkbench runs",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="run one case-local, read-only Codex task",
        description=(
            "Run one local_read_only task. The case root, workspace, owner DB, "
            "CODEX_HOME and event log must remain case-local."
        ),
    )
    run.add_argument("--case-root", required=True, type=Path, help="existing case-local root directory")
    run.add_argument("--workspace", required=True, type=Path, help="existing workspace inside --case-root")
    run.add_argument("--prompt", required=True, help="one read-only task prompt")
    run.add_argument("--codex", required=True, type=Path, help="fixed executable path for Codex app-server")
    run.add_argument("--run-id", help="durable run identity; generated when omitted")
    run.add_argument("--db", type=Path, help="case-local SQLite owner path")
    run.add_argument("--code-home", type=Path, help="case-local CODEX_HOME path")
    run.add_argument("--event-log", type=Path, help="case-local Codex event log path")
    run.add_argument("--provider", default="fake-loopback", help="non-secret Provider identity")
    run.add_argument("--model", default="fake-model", help="non-secret model identity")
    run.add_argument("--endpoint", default="http://127.0.0.1:11434", help="loopback Provider endpoint")
    run.add_argument(
        "--provider-profile",
        default=None,
        help=(
            "select an explicitly configured remote/custom Provider by name from "
            "--provider-config; authorizes its non-loopback endpoint and switches "
            "the adapter off the ollama default. Omit to keep the ollama fallback"
        ),
    )
    run.add_argument(
        "--provider-config",
        default=None,
        help="Codex-style config.toml with [model_providers.<name>] / [provider.<name>] tables",
    )
    run.add_argument("--timeout", type=float, default=45.0, help="maximum turn wait in seconds")
    run.add_argument(
        "--host-enforcement",
        action="store_true",
        default=False,
        help=(
            "make ZWorkbench the single sandbox authority (ADR 0008 intent): "
            "launch Codex with --dangerously-bypass-approvals-and-sandbox so it "
            "does not re-seatbelt its own shell children. ZWorkbench does NOT "
            "wrap Codex in a macOS seatbelt (roadmap 1-9-3 direction b: nested "
            "sandbox_apply fails with EPERM). Read-only enforcement then relies "
            "on Codex's own sandbox or the external host seatbelt."
        ),
    )
    run.add_argument(
        "--real-provider-gate",
        action="store_true",
        default=False,
        help=(
            "explicitly consent to a real Provider egress/billing path. Required "
            "when --provider-profile is set: the controlled gate that keeps the "
            "loopback/fake baseline from silently reaching a real Provider "
            "(roadmap node 1-1-4). Without it, a real profile is denied."
        ),
    )
    run.add_argument("--export", type=Path, help="optional case-local owner JSON export path")
    run.add_argument("--backup", type=Path, help="optional empty case-local backup directory")
    run.add_argument("--summary", type=Path, help="optional case-local JSON summary path")
    run.set_defaults(handler=_run_command)

    # ------------------------------------------------------------------
    # write — the S2 reversible write boundary, driven from the control plane.
    # push is intentionally absent: it is the S4 separate gate and stays off.
    # ------------------------------------------------------------------
    write = commands.add_parser(
        "write",
        help="S2 reversible write boundary (isolated worktree + local commit)",
        description=(
            "Apply a Codex-generated unified diff to an isolated git worktree "
            "and commit it locally through the owner-backed write seam. Push is "
            "never performed: it is the separate S4 gate and stays off by "
            "default. The diff is generated elsewhere and piped in; this "
            "command only applies it."
        ),
    )
    write_commands = write.add_subparsers(dest="write_command", required=True)

    write_request = write_commands.add_parser(
        "request-approval",
        help="create a pending approval for one write operation",
        description=(
            "Create a pending owner approval bound to one operation/action/"
            "resource/idempotency key. The resulting approval_id is later "
            "approved to obtain the one-use token consumed by `write apply`."
        ),
    )
    write_request.add_argument("--db", required=True, type=Path, help="case-local SQLite owner path")
    write_request.add_argument("--case-root", required=True, type=Path, help="existing case-local root directory")
    write_request.add_argument("--run-id", required=True, help="durable run identity that owns the approval")
    write_request.add_argument("--operation-id", required=True, help="operation identity the approval binds to")
    write_request.add_argument("--action", default="apply_diff", help="effect action the approval binds to")
    write_request.add_argument("--resource", required=True, help="effect resource the approval binds to")
    write_request.add_argument("--idempotency-key", required=True, help="idempotency key the approval binds to")
    write_request.add_argument("--reason", default="S2 write seam approval", help="human-readable reason")
    write_request.add_argument("--summary", type=Path, help="optional case-local JSON summary path")
    write_request.set_defaults(handler=_write_request_approval_command)

    write_approve = write_commands.add_parser(
        "approve",
        help="approve a pending approval and print the one-use token",
        description=(
            "Approve one pending approval and print the one-use bearer token. "
            "The token is shown on stdout for the caller to copy; it is never "
            "written to a summary file in plaintext."
        ),
    )
    write_approve.add_argument("--db", required=True, type=Path, help="case-local SQLite owner path")
    write_approve.add_argument("--case-root", required=True, type=Path, help="existing case-local root directory")
    write_approve.add_argument("--approval-id", required=True, help="pending approval identity to approve")
    write_approve.add_argument("--ttl", type=int, default=300, help="token lifetime in seconds (default 300)")
    write_approve.add_argument("--summary", type=Path, help="optional case-local JSON summary path")
    write_approve.set_defaults(handler=_write_approve_command)

    write_apply = write_commands.add_parser(
        "apply",
        help="apply a unified diff to an isolated worktree and commit locally",
        description=(
            "Apply a unified diff to an isolated worktree and commit it locally "
            "through the owner-backed write seam. Push is never performed (S4 "
            "separate gate, off by default). The diff is read from --diff (a "
            "file path) or `-` for stdin."
        ),
    )
    write_apply.add_argument("--db", required=True, type=Path, help="case-local SQLite owner path")
    write_apply.add_argument("--case-root", required=True, type=Path, help="existing case-local root directory")
    write_apply.add_argument("--repo", required=True, type=Path, help="existing git repo to branch the worktree from")
    write_apply.add_argument("--worktree-root", required=True, type=Path, help="case-local directory for isolated worktrees")
    write_apply.add_argument("--run-id", help="durable run identity; generated when omitted")
    write_apply.add_argument("--diff", required=True, help="unified diff file path, or `-` to read from stdin")
    write_apply.add_argument("--approval-token", required=True, help="one-use token from `write approve`")
    write_apply.add_argument("--operation-id", required=True, help="operation identity bound to the approval")
    write_apply.add_argument("--resource", required=True, help="effect resource bound to the approval")
    write_apply.add_argument("--idempotency-key", required=True, help="idempotency key bound to the approval")
    write_apply.add_argument("--action", default="apply_diff", help="effect action (default apply_diff)")
    write_apply.add_argument("--base-ref", default="HEAD", help="base ref the worktree is checked out from")
    write_apply.add_argument("--summary", type=Path, help="optional case-local JSON summary path")
    write_apply.set_defaults(handler=_write_apply_command)

    snapshot = commands.add_parser("snapshot", help="print the durable owner snapshot")
    snapshot.add_argument("--db", required=True, type=Path, help="SQLite composition state path")
    snapshot.set_defaults(handler=_snapshot_command)

    export = commands.add_parser("export", help="write a portable owner JSON export")
    export.add_argument("--db", required=True, type=Path, help="SQLite composition state path")
    export.add_argument("destination", type=Path)
    export.set_defaults(handler=_export_command)

    backup = commands.add_parser("backup", help="create a self-validating owner backup")
    backup.add_argument("--db", required=True, type=Path, help="SQLite composition state path")
    backup.add_argument("destination", type=Path)
    backup.set_defaults(handler=_backup_command)

    restore = commands.add_parser("restore", help="validate and restore an owner backup")
    restore.add_argument("--db", required=True, type=Path, help="SQLite composition state path")
    restore.add_argument("backup_directory", type=Path)
    restore.add_argument("--replace", action="store_true", help="explicitly replace an existing target DB")
    restore.set_defaults(handler=_restore_command)

    ui_ref = commands.add_parser(
        "ui-ref",
        help="read-only UI reference manifest queries",
        description=(
            "Query a stored UI reference manifest artifact. The command is "
            "read-only: it makes no network request, starts no run and changes "
            "no owner state."
        ),
    )
    ui_ref.add_argument("--store", required=True, type=Path, help="local manifest artifact directory")
    ui_ref_commands = ui_ref.add_subparsers(dest="ui_ref_command", required=True)

    ui_ref_identity = ui_ref_commands.add_parser("identity", help="print the artifact identity")
    ui_ref_identity.add_argument("--ui-map", required=True, help="expected manifest digest")
    ui_ref_identity.add_argument("--build", required=True, help="expected build receipt digest")

    ui_ref_list = ui_ref_commands.add_parser("list", help="list declared references")
    ui_ref_list.add_argument("--ui-map", required=True, help="expected manifest digest")
    ui_ref_list.add_argument("--build", required=True, help="expected build receipt digest")

    ui_ref_resolve = ui_ref_commands.add_parser("resolve", help="resolve one reference")
    ui_ref_resolve.add_argument("ref")
    ui_ref_resolve.add_argument("--ui-map", required=True, help="expected manifest digest")
    ui_ref_resolve.add_argument("--build", required=True, help="expected build receipt digest")

    ui_ref.set_defaults(handler=_ui_ref_command)

    ui_host = commands.add_parser(
        "ui-host",
        help="serve the declared UI views for local review",
        description=(
            "Serve the declared views on a loopback port for local review. "
            "The command is read-only: it opens no owner database, starts no "
            "run and changes no owner state. It takes no --db for that reason. "
            "Interrupt it to stop; the port is released before it exits."
        ),
    )
    ui_host.add_argument(
        "--host",
        default=LOOPBACK,
        help=(
            "bind address; only loopback is accepted, because the host "
            "renders review material rather than a network service"
        ),
    )
    ui_host.add_argument(
        "--port",
        type=int,
        default=0,
        help="bind port; the default asks the OS for a free one",
    )
    ui_host.add_argument(
        "--review",
        action="store_true",
        help=(
            "enable the local review annotation mode; off by default, so a "
            "normal page carries no overlay, panel, token or script"
        ),
    )
    ui_host.set_defaults(handler=_ui_host_command)

    ui = commands.add_parser(
        "ui",
        help="serve the writable workbench UI backed by a real owner DB (dogfood)",
        description=(
            "Serve the workbench UI wired to a real CompositionOwner. Unlike "
            "ui-host, this opens --db, renders real runs through owner_view_source, "
            "and wires every write seam (composer send, approval execution, "
            "scenario state, reconcile). It changes owner state, so point it at a "
            "scratch DB you can discard."
        ),
    )
    ui.add_argument(
        "--db",
        required=True,
        type=Path,
        help="path to the CompositionOwner sqlite database; created if absent",
    )
    ui.add_argument(
        "--host",
        default=LOOPBACK,
        help="bind address; only loopback is accepted",
    )
    ui.add_argument(
        "--port",
        type=int,
        default=0,
        help="bind port; the default asks the OS for a free one",
    )
    ui.add_argument(
        "--review",
        action="store_true",
        help="enable the local review annotation mode",
    )
    ui.set_defaults(handler=_ui_command)

    ui_build = commands.add_parser(
        "ui-build",
        help="generate and store the UI reference manifest artifacts",
        description=(
            "Generate the UI reference manifest for every view from the "
            "declaring sources and store each artifact under its own identity. "
            "The build only reads sources and writes artifacts: it starts no "
            "run, opens no owner database and changes no owner state. The "
            "produced --store directory is what `ui-ref` queries against, which "
            "closes the R1 review-token -> code loop on the AI side."
        ),
    )
    ui_build.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "repository root that contains src/zworkbench; defaults to the "
            "package's own repository root"
        ),
    )
    ui_build.add_argument(
        "--store",
        required=True,
        type=Path,
        help="local manifest artifact directory to write the generated artifacts into",
    )
    ui_build.set_defaults(handler=_ui_build_command)

    return parser


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        return candidate == root or candidate.is_relative_to(root)
    except AttributeError:  # pragma: no cover - Python 3.9 compatibility
        try:
            return str(candidate) == str(root) or str(candidate).startswith(str(root) + "/")
        except OSError:
            return False


def _case_local_violations(root: Path, paths: Iterable[Tuple[str, Optional[Path]]]) -> list[PreflightViolation]:
    violations: list[PreflightViolation] = []
    for name, candidate in paths:
        if candidate is None:
            continue
        if not _is_inside(root, candidate):
            violations.append(
                PreflightViolation(
                    "cli_path_outside_case_root",
                    "{0} must remain inside case_root".format(name),
                )
            )
    return violations


def _path_conflict_violations(
    protected: Iterable[Tuple[str, Path]],
    outputs: Iterable[Tuple[str, Optional[Path]]],
) -> list[PreflightViolation]:
    protected_paths = list(protected)
    output_paths = [(name, path) for name, path in outputs if path is not None]
    violations: list[PreflightViolation] = []
    for output_name, output_path in output_paths:
        for protected_name, protected_path in protected_paths:
            if output_path == protected_path:
                violations.append(
                    PreflightViolation(
                        "cli_path_conflict",
                        "{0} must not overwrite {1}".format(output_name, protected_name),
                    )
                )
    for index, (left_name, left_path) in enumerate(output_paths):
        for right_name, right_path in output_paths[index + 1 :]:
            if left_path == right_path:
                violations.append(
                    PreflightViolation(
                        "cli_path_conflict",
                        "{0} and {1} must use different paths".format(left_name, right_name),
                    )
                )
    return violations


def _denied_payload(
    run_id: str,
    *,
    preflight_result: Optional[PreflightResult] = None,
    violations: Sequence[PreflightViolation] = (),
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema": CLI_SCHEMA,
        "command": "run",
        "status": "denied",
        "run_id": run_id,
    }
    if preflight_result is not None:
        payload["preflight"] = preflight_result.to_dict()
    if violations:
        payload["violations"] = [item.to_dict() for item in violations]
    if reason is not None:
        payload["reason"] = reason
    return payload


def _run_config(args: argparse.Namespace) -> LocalReadOnlyRunConfig:
    case_root = _resolve(args.case_root)
    paths = {
        "case_root": case_root,
        "workspace": _resolve(args.workspace),
        "database": _resolve(args.db or case_root / "state" / "composition.sqlite3"),
        "code_home": _resolve(args.code_home or case_root / "codex-home"),
        "event_log": _resolve(args.event_log or case_root / "events" / "codex.jsonl"),
    }
    authorized_providers = frozenset()
    provider_profile: Optional[ProviderProfile] = None
    provider_config_path: Optional[Path] = None
    if args.provider_profile:
        config_path = _resolve(Path(args.provider_config)) if args.provider_config else (Path.home() / ".codex" / "config.toml")
        profiles = load_provider_profiles(config_path)
        provider_config_path = config_path
        if args.provider_profile not in profiles:
            raise ValueError(
                "provider profile {0!r} not found in {1}".format(args.provider_profile, config_path)
            )
        profile = profiles[args.provider_profile]
        provider_profile = profile
        authorized_providers = frozenset(profiles.keys())
        provider_identity = {
            "provider": profile.name,
            "model": profile.model,
            "endpoint": profile.base_url,
            "model_provider": profile.model_provider,
        }
    else:
        provider_identity = {
            "provider": args.provider,
            "model": args.model,
            "endpoint": args.endpoint,
            "model_provider": "ollama",
        }
    config = LocalReadOnlyRunConfig(
        case_root=paths["case_root"],
        workspace=paths["workspace"],
        database=paths["database"],
        code_home=paths["code_home"],
        codex_executable=_resolve(args.codex),
        event_log=paths["event_log"],
        provider_identity=provider_identity,
        authorized_providers=authorized_providers,
        provider_profile=provider_profile,
        provider_config_path=provider_config_path,
        host_enforcement=args.host_enforcement,
        real_provider_gate=bool(args.real_provider_gate),
    )
    return config


def _owner_projection(database: Path, run_id: str) -> Dict[str, Any]:
    if not database.is_file():
        return {
            "database_present": False,
            "run_status": None,
            "state_digest": None,
            "recorded_view_present": False,
            "event_count": 0,
        }
    with CompositionOwner(database) as owner:
        snapshot = owner.snapshot()
        return {
            "database_present": True,
            "run_status": next((item.get("status") for item in snapshot["runs"] if item.get("run_id") == run_id), None),
            "state_digest": owner.state_digest(),
            "recorded_view_present": any(
                item.get("run_id") == run_id and item.get("mode") == "recorded_view"
                for item in snapshot["replays"]
            ),
            "event_count": sum(item.get("run_id") == run_id for item in snapshot["events"]),
        }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_command(args: argparse.Namespace) -> int:
    run_id = args.run_id or "zworkbench-run-" + uuid.uuid4().hex
    # `--prompt -` reads the task prompt from stdin so it never lands in the
    # process argument list (which is world-readable via ps). The prompt is
    # still subject to the same credential-pattern admission check below.
    if args.prompt == "-":
        args.prompt = sys.stdin.read()
    if args.timeout <= 0:
        payload = _denied_payload(
            run_id,
            violations=(PreflightViolation("timeout_not_positive", "timeout must be positive"),),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    try:
        config = _run_config(args)
    except (TypeError, ValueError, OSError) as exc:
        payload = _denied_payload(run_id, reason="invalid local configuration: " + type(exc).__name__)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    managed_paths = [
        ("database", config.database),
        ("code_home", config.code_home),
        ("event_log", config.event_log),
        ("export", _resolve(args.export) if args.export else None),
        ("backup", _resolve(args.backup) if args.backup else None),
        ("summary", _resolve(args.summary) if args.summary else None),
    ]
    path_violations = _case_local_violations(config.case_root, managed_paths)
    path_violations.extend(
        _path_conflict_violations(
            (
                ("case_root", config.case_root),
                ("workspace", config.workspace),
                ("database", config.database),
                ("code_home", config.code_home),
                ("event_log", config.event_log),
            ),
            managed_paths[3:],
        )
    )
    if path_violations:
        payload = _denied_payload(run_id, violations=path_violations)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    if _SECRET_VALUE.search(args.prompt):
        payload = _denied_payload(
            run_id,
            violations=(
                PreflightViolation(
                    "prompt_contains_credential_pattern",
                    "prompt contains a credential-like value and was not recorded",
                ),
            ),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    admission = preflight(config)
    if not admission.allowed:
        print(json.dumps(_denied_payload(run_id, preflight_result=admission), ensure_ascii=False, indent=2))
        return 2

    try:
        result = LocalReadOnlyRunOrchestrator(config).run(run_id, args.prompt, timeout=args.timeout)
    except Exception as exc:
        projection = _owner_projection(config.database, run_id)
        payload = {
            "schema": CLI_SCHEMA,
            "command": "run",
            "status": "failed",
            "run_id": run_id,
            "preflight": admission.to_dict(),
            "error": {"type": type(exc).__name__},
            "owner": projection,
        }
        if args.summary:
            _write_json(_resolve(args.summary), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    payload: Dict[str, Any] = {
        "schema": CLI_SCHEMA,
        "command": "run",
        "mode": LOCAL_READ_ONLY_MODE,
        "status": result.status,
        "run_id": result.run_id,
        "preflight": result.preflight.to_dict(),
        "execution": result.to_dict().get("execution"),
        "owner": _owner_projection(config.database, run_id),
        "artifacts": {},
    }
    artifact_error: Optional[Dict[str, str]] = None
    if config.database.is_file() and (args.export or args.backup):
        try:
            with CompositionOwner(config.database) as owner:
                if args.export:
                    payload["artifacts"]["export"] = owner.export_state(_resolve(args.export))
                if args.backup:
                    payload["artifacts"]["backup"] = owner.backup(_resolve(args.backup))
        except Exception as exc:
            artifact_error = {"type": type(exc).__name__}
            payload["artifact_error"] = artifact_error

    if args.summary:
        _write_json(_resolve(args.summary), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if artifact_error else (0 if result.status == "completed" else 1)


def _ensure_run_for_approval(owner: CompositionOwner, run_id: str) -> None:
    """Create the run if absent so the approval has a durable home."""

    from .composition import CompositionError

    try:
        owner.create_run(run_id, "write_seam", {"driver": "cli-write"})
    except CompositionError:
        # Reuse an existing run (e.g. a read-only run that produced the diff).
        pass


def _write_request_approval_command(args: argparse.Namespace) -> int:
    """Create a pending owner approval bound to one write operation."""

    case_root = _resolve(args.case_root)
    db = _resolve(args.db)
    summary = _resolve(args.summary) if args.summary else None
    violations = _case_local_violations(case_root, (("database", db), ("summary", summary)))
    if violations:
        print(json.dumps(_denied_payload(args.run_id, violations=violations), ensure_ascii=False, indent=2))
        return 2
    with CompositionOwner(db) as owner:
        _ensure_run_for_approval(owner, args.run_id)
        approval = owner.request_approval(
            args.run_id,
            args.operation_id,
            args.action,
            args.resource,
            args.idempotency_key,
            args.reason,
        )
    payload = {
        "schema": CLI_SCHEMA,
        "command": "write-request-approval",
        "status": "completed",
        "approval_id": approval["approval_id"],
        "operation_id": approval["operation_id"],
        "status_detail": approval["status"],
        "owner": _owner_projection(db, args.run_id),
    }
    if summary:
        _write_json(summary, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _write_approve_command(args: argparse.Namespace) -> int:
    """Approve a pending approval and print the one-use token."""

    case_root = _resolve(args.case_root)
    db = _resolve(args.db)
    summary = _resolve(args.summary) if args.summary else None
    violations = _case_local_violations(case_root, (("database", db), ("summary", summary)))
    if violations:
        print(json.dumps(_denied_payload(args.approval_id, violations=violations), ensure_ascii=False, indent=2))
        return 2
    with CompositionOwner(db) as owner:
        granted = owner.approve(args.approval_id, ttl_seconds=args.ttl)
    payload = {
        "schema": CLI_SCHEMA,
        "command": "write-approve",
        "status": "completed",
        "approval_id": granted["approval_id"],
        "operation_id": granted["operation_id"],
        "token": granted["token"],
        "expires_at": granted["expires_at"],
    }
    if summary:
        # The bearer token must never be persisted in plaintext.
        _write_json(summary, {**payload, "token": "<redacted>"})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _write_apply_command(args: argparse.Namespace) -> int:
    """Apply a unified diff to an isolated worktree and commit it locally.

    Push is never performed here — it is the S4 separate gate and stays off.
    """

    import uuid as _uuid

    case_root = _resolve(args.case_root)
    db = _resolve(args.db)
    repo = _resolve(args.repo)
    worktree_root = _resolve(args.worktree_root)
    summary = _resolve(args.summary) if args.summary else None
    run_id = args.run_id or "zworkbench-write-" + _uuid.uuid4().hex

    violations = _case_local_violations(
        case_root,
        (("database", db), ("repo", repo), ("worktree_root", worktree_root), ("summary", summary)),
    )
    if violations:
        print(json.dumps(_denied_payload(run_id, violations=violations), ensure_ascii=False, indent=2))
        return 2

    # The diff is generated elsewhere; this command only applies it.
    if args.diff == "-":
        patch_text = sys.stdin.read()
    else:
        patch_text = Path(args.diff).read_text(encoding="utf-8")

    orchestrator = WriteRunOrchestrator(db, worktree_root=worktree_root)
    try:
        receipt = orchestrator.apply(
            run_id,
            repo,
            patch_text,
            approval_token=args.approval_token,
            operation_id=args.operation_id,
            action=args.action,
            resource=args.resource,
            idempotency_key=args.idempotency_key,
            base_ref=args.base_ref,
        )
    except WriteSeamError as exc:
        payload = {
            "schema": CLI_SCHEMA,
            "command": "write-apply",
            "status": "denied",
            "run_id": run_id,
            "reason": str(exc),
            "owner": _owner_projection(db, run_id),
        }
        if summary:
            _write_json(summary, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        payload = {
            "schema": CLI_SCHEMA,
            "command": "write-apply",
            "status": "failed",
            "run_id": run_id,
            "error": {"type": type(exc).__name__},
            "owner": _owner_projection(db, run_id),
        }
        if summary:
            _write_json(summary, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    receipt_data = {
        "effect_id": receipt.effect_id,
        "status": receipt.status,
        "worktree_path": receipt.worktree_path,
        "commit_hash": receipt.commit_hash,
        "diff_digest": receipt.diff_digest,
        "external_receipt": dict(receipt.external_receipt),
    }
    payload = {
        "schema": CLI_SCHEMA,
        "command": "write-apply",
        "status": "completed",
        "run_id": run_id,
        "receipt": receipt_data,
        "owner": _owner_projection(db, run_id),
    }
    if summary:
        _write_json(summary, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _ui_ref_command(args: argparse.Namespace) -> int:
    """Answer one read-only manifest query.

    The caller must name both halves of the artifact identity, so the stored
    current manifest can never silently answer for a different version.
    """
    from .ui_manifest import load_manifest
    from .ui_ref import resolve as resolve_ui_ref

    loaded = load_manifest(_resolve(args.store), ui_map=args.ui_map, build=args.build)
    if loaded["outcome"] != "found":
        print(json.dumps(_ui_ref_payload(loaded), ensure_ascii=False, indent=2))
        return 3

    manifest = loaded["manifest"]
    if args.ui_ref_command == "identity":
        result: Dict[str, Any] = {
            "outcome": "found",
            "ui_map": manifest["ui_map"],
            "build": manifest["build"],
            "schema": manifest["schema"],
            "declared": len(manifest["refs"]),
        }
    elif args.ui_ref_command == "list":
        result = {
            "outcome": "found",
            "refs": [
                {
                    "ref": entry["ref"],
                    "semantic_zh": entry["semantic_zh"],
                    "kind": entry["kind"],
                    "view": entry["view"],
                }
                for entry in manifest["refs"]
            ],
        }
    else:
        result = resolve_ui_ref(manifest, args.ref, ui_map=args.ui_map)

    print(json.dumps(_ui_ref_payload(result), ensure_ascii=False, indent=2))
    return 0 if result["outcome"] == "found" else 3


def _ui_ref_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    status = "completed" if result["outcome"] == "found" else result["outcome"]
    return {
        "schema": CLI_SCHEMA,
        "command": "ui-ref",
        "status": status,
        "result": result,
    }


def _owner_command_payload(command: str, value: Any) -> Dict[str, Any]:
    return {"schema": CLI_SCHEMA, "command": command, "status": "completed", "result": value}


def _snapshot_command(args: argparse.Namespace) -> int:
    with CompositionOwner(_resolve(args.db)) as owner:
        print(json.dumps(_owner_command_payload("snapshot", owner.snapshot()), ensure_ascii=False, indent=2))
    return 0


def _export_command(args: argparse.Namespace) -> int:
    with CompositionOwner(_resolve(args.db)) as owner:
        result = owner.export_state(_resolve(args.destination))
    print(json.dumps(_owner_command_payload("export", result), ensure_ascii=False, indent=2))
    return 0


def _backup_command(args: argparse.Namespace) -> int:
    with CompositionOwner(_resolve(args.db)) as owner:
        result = owner.backup(_resolve(args.destination))
    print(json.dumps(_owner_command_payload("backup", result), ensure_ascii=False, indent=2))
    return 0


def _restore_command(args: argparse.Namespace) -> int:
    result = CompositionOwner.restore(_resolve(args.backup_directory), _resolve(args.db), replace=args.replace)
    print(json.dumps(_owner_command_payload("restore", result), ensure_ascii=False, indent=2))
    return 0


def _ui_host_command(args: argparse.Namespace) -> int:
    """Serve the declared views until interrupted, then release the port.

    The announcement is written before the serving loop starts, so a caller
    that has read the line can connect straight away without polling. Stopping
    is reported on the same stream, which is what lets a supervisor tell a
    clean exit from a killed process.
    """
    import signal as signal_module

    from .ui_host import serve_workbench

    if args.host not in LOOPBACK_ADDRESSES:
        raise SystemExit(
            "ui-host binds loopback only; {0!r} would expose review material "
            "on the network".format(args.host)
        )

    host = serve_workbench(bind=(args.host, args.port), review=args.review)
    _announce(
        {
            "event": "serving",
            "mode": "read-only",
            "review": bool(args.review),
            "base_url": host.base_url,
        }
    )

    stopping = threading.Event()

    def _stop(signum: int, frame: Any) -> None:
        stopping.set()

    previous = {
        number: signal_module.signal(number, _stop)
        for number in (signal_module.SIGINT, signal_module.SIGTERM)
    }
    try:
        stopping.wait()
    finally:
        for number, handler in previous.items():
            signal_module.signal(number, handler)
        host.close()
        _announce({"event": "stopped", "base_url": host.base_url})
    return 0


def _ui_command(args: argparse.Namespace) -> int:
    """Serve the writable workbench UI against a real owner DB (dogfood).

    Opens ``--db`` as a CompositionOwner, renders real runs through
    ``owner_view_source``, and wires every write seam so the composer send,
    approval execution, scenario state machine and reconcile controls are live.
    This is the dogfood entry the read-only ``ui-host`` deliberately is not.
    """

    import signal as signal_module

    from .ui_approval import owner_approval_source
    from .ui_host import serve_workbench
    from .ui_reconcile import owner_reconcile_source
    from .ui_run import owner_command_source
    from .ui_scenario_state import owner_scenario_source
    from .ui_view_model import owner_view_source

    if args.host not in LOOPBACK_ADDRESSES:
        raise SystemExit(
            "ui binds loopback only; {0!r} would expose owner state "
            "on the network".format(args.host)
        )

    owner = CompositionOwner(args.db)
    stopping = threading.Event()
    host = None
    try:
        host = serve_workbench(
            view_source=owner_view_source(owner),
            command_source=owner_command_source(owner),
            approval_source=owner_approval_source(owner),
            reconcile_source=owner_reconcile_source(owner),
            scenario_source=owner_scenario_source(owner),
            bind=(args.host, args.port),
            review=args.review,
        )
        _announce(
            {
                "event": "serving",
                "mode": "dogfood",
                "db": str(owner.database),
                "review": bool(args.review),
                "base_url": host.base_url,
            }
        )

        def _stop(signum: int, frame: Any) -> None:
            stopping.set()

        previous = {
            number: signal_module.signal(number, _stop)
            for number in (signal_module.SIGINT, signal_module.SIGTERM)
        }
        try:
            stopping.wait()
        finally:
            for number, handler in previous.items():
                signal_module.signal(number, handler)
            if host is not None:
                host.close()
            _announce(
                {
                    "event": "stopped",
                    "base_url": host.base_url if host is not None else None,
                }
            )
    finally:
        owner.close()
    return 0


def _ui_build_command(args: argparse.Namespace) -> int:
    """Generate and store every view manifest against one shared receipt.

    The produced --store directory is the artifact `ui-ref` reads, so after
    this command the AI side of the R1 loop (token -> code) is reachable: copy
    a review token's ref/ui_map/build and run `ui-ref resolve` against the
    same --store.
    """

    from .ui_build import build_ui_artifacts, served_source_root_and_sources

    # Default root adapts to a source checkout or an installed wheel; an
    # explicit --root always wins.
    root = (
        _resolve(args.root)
        if args.root is not None
        else served_source_root_and_sources()[0]
    )
    store = _resolve(args.store)
    try:
        result = build_ui_artifacts(root, store)
    except OSError as exc:
        raise SystemExit(
            "ui-build could not read the declaring sources under {0!r}: {1}. "
            "Pass --root to point at the repository that contains src/zworkbench."
            .format(str(root), type(exc).__name__)
        )
    payload = {
        "schema": CLI_SCHEMA,
        "command": "ui-build",
        "status": "completed",
        "root": str(root),
        "store": str(store),
        "build": result["receipt"]["build"],
        "sources": [entry["repo_path"] for entry in result["receipt"]["sources"]],
        "views": {
            view: {"ui_map": identity["ui_map"], "build": identity["build"]}
            for view, identity in result["views"].items()
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _announce(payload: Dict[str, Any]) -> None:
    """Emit one line and flush, so a reader is never blocked by buffering."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
