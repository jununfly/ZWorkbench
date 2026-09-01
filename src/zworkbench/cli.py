"""The user-facing command line entry point for the first W8 slice.

The CLI is intentionally a thin control-plane layer.  It prepares no global
Codex state, accepts no credential value, and never implements a Harness loop.
Execution is delegated to :class:`LocalReadOnlyRunOrchestrator`; the
composition owner remains the durable source of truth.
"""

from __future__ import annotations

import argparse
import json
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
    preflight,
)


CLI_SCHEMA = "zworkbench-cli/v1"
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
    run.add_argument("--timeout", type=float, default=45.0, help="maximum turn wait in seconds")
    run.add_argument("--export", type=Path, help="optional case-local owner JSON export path")
    run.add_argument("--backup", type=Path, help="optional empty case-local backup directory")
    run.add_argument("--summary", type=Path, help="optional case-local JSON summary path")
    run.set_defaults(handler=_run_command)

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
    provider_identity = {
        "provider": args.provider,
        "model": args.model,
        "endpoint": args.endpoint,
    }
    config = LocalReadOnlyRunConfig(
        case_root=paths["case_root"],
        workspace=paths["workspace"],
        database=paths["database"],
        code_home=paths["code_home"],
        codex_executable=_resolve(args.codex),
        event_log=paths["event_log"],
        provider_identity=provider_identity,
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
