#!/usr/bin/env python3
"""Run W8 identity, redaction, network, and default-deny controls.

This is an isolated seam-level runner.  It uses the real composition owner and
the W8 deterministic adapter, but never starts Codex, contacts a Provider, or
executes a tool.  The network tripwire is deliberately process-local and is
not a claim about host-level firewall enforcement.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import tempfile
from typing import Any, Dict, Iterator
from unittest.mock import patch

# Keep the runner executable both as ``python -m ...`` and as a direct script
# from the repository root, without requiring an installed package.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from evaluation.fixtures.w8_local_read_only.v1.fixture_adapters import (
    FIXTURE_ADAPTER_SCHEMA,
    FIXTURE_ENVIRONMENT_DIGEST,
    FIXTURE_EVENT_DIGEST,
    FIXTURE_THREAD_ID,
    FIXTURE_TURN_ID,
)
from evaluation.runner.run_w8_local_read_only import (
    DEFAULT_PROVIDER,
    MANIFEST,
    RUNNER_SCHEMA,
    _build_config,
    _prepare_case,
    read_json,
    run_case,
    write_json,
)


SECURITY_RUNNER_SCHEMA = "zworkbench-w8-local-read-only-security-runner/v1"


@contextmanager
def network_tripwire() -> Iterator[list[Dict[str, Any]]]:
    """Record and reject socket/DNS attempts made inside the fixture process."""

    attempts: list[Dict[str, Any]] = []

    def blocked_connect(_sock, address, *args, **kwargs):
        del args, kwargs
        attempts.append({"operation": "socket.connect", "address": repr(address)})
        raise AssertionError("network access denied by W8 fixture tripwire")

    def blocked_create_connection(address, *args, **kwargs):
        del args, kwargs
        attempts.append({"operation": "socket.create_connection", "address": repr(address)})
        raise AssertionError("network access denied by W8 fixture tripwire")

    def blocked_getaddrinfo(*args, **kwargs):
        del args, kwargs
        attempts.append({"operation": "socket.getaddrinfo"})
        raise AssertionError("DNS access denied by W8 fixture tripwire")

    with patch.object(socket.socket, "connect", blocked_connect), patch.object(
        socket, "create_connection", blocked_create_connection
    ), patch.object(socket, "getaddrinfo", blocked_getaddrinfo):
        yield attempts


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        return candidate == root or str(candidate).startswith(str(root) + "/")


def _case_paths(case_dir: Path) -> Dict[str, Path]:
    return {
        "case_root": case_dir,
        "workspace": case_dir / "workspace",
        "database": case_dir / "state" / "composition.sqlite3",
        "code_home": case_dir / "codex-home",
        "codex_executable": case_dir / "bin" / "codex",
        "event_log": case_dir / "events" / "codex.jsonl",
    }


def _identity_control(output_dir: Path) -> Dict[str, Any]:
    """Run success fixture and check every identity edge in the owner state."""

    with network_tripwire() as network_attempts:
        result = run_case(output_dir / "identity", "success")
    case_dir = Path(result["case_root"])
    run_id = "w8-local-read-only-success-repeat-01"

    from zworkbench import CompositionOwner

    with CompositionOwner(case_dir / "state" / "composition.sqlite3") as owner:
        snapshot = owner.snapshot()
        run = owner.get_run(run_id)
        results = [item for item in snapshot["results"] if item.get("run_id") == run_id]
        replays = [item for item in snapshot["replays"] if item.get("run_id") == run_id]
        events = [item for item in snapshot["events"] if item.get("run_id") == run_id]

    by_kind = {item["kind"]: item["value"] for item in results}
    semantic = by_kind.get("semantic", {})
    replay = replays[0] if len(replays) == 1 else {}
    provider_matches = semantic.get("provider_identity") == DEFAULT_PROVIDER and replay.get("provider_identity") == DEFAULT_PROVIDER
    checks = {
        "fixture_run_passed": result["status"] == "pass",
        "run_id_present": run.get("run_id") == run_id,
        "run_status_completed": run.get("status") == "completed",
        "thread_id_bound_to_run": by_kind.get("adapter.fixture.thread", {}).get("thread_id") == FIXTURE_THREAD_ID,
        "turn_id_bound_to_run": by_kind.get("adapter.fixture.turn", {}).get("turn_id") == FIXTURE_TURN_ID,
        "thread_turn_relationship_bound": by_kind.get("adapter.fixture.turn", {}).get("thread_id") == FIXTURE_THREAD_ID,
        "provider_identity_bound_to_semantic": provider_matches,
        "provider_identity_bound_to_replay": replay.get("run_id") == run_id and provider_matches,
        "environment_identity_bound": semantic.get("environment_digest") == FIXTURE_ENVIRONMENT_DIGEST and replay.get("environment_digest") == FIXTURE_ENVIRONMENT_DIGEST,
        "event_identity_bound_to_run": bool(events) and all(item.get("run_id") == run_id for item in events),
        "result_identity_bound_to_run": len(results) == 4 and all(item.get("run_id") == run_id for item in results),
        "event_digest_recorded": semantic.get("event_digest") == FIXTURE_EVENT_DIGEST and replay.get("source_event_digest") == FIXTURE_EVENT_DIGEST,
        "adapter_schema_recorded": run.get("metadata", {}).get("adapter_schema") == FIXTURE_ADAPTER_SCHEMA,
        "network_attempts_zero": len(network_attempts) == 0,
    }
    return {
        "control": "identity",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "run_id": run_id,
            "thread_id": by_kind.get("adapter.fixture.thread", {}).get("thread_id"),
            "turn_id": by_kind.get("adapter.fixture.turn", {}).get("turn_id"),
            "provider_identity": semantic.get("provider_identity"),
            "event_digest": semantic.get("event_digest"),
            "environment_digest": semantic.get("environment_digest"),
            "result_count": len(results),
            "replay_count": len(replays),
            "event_count": len(events),
            "network_attempts": network_attempts,
        },
        "checks": checks,
        "case_root": str(case_dir),
    }


def _redaction_control(output_dir: Path) -> Dict[str, Any]:
    """Prove secret-bearing input is denied before an adapter or owner starts."""

    case_dir = output_dir / "redaction" / "repeat-01"
    paths = _prepare_case(case_dir)
    from zworkbench import LocalReadOnlyRunOrchestrator, LocalReadOnlyRunConfig

    secret = "sk-w8-redaction-fixture-secret-0001"
    provider_identity = dict(DEFAULT_PROVIDER)
    provider_identity["api_key"] = secret
    config = LocalReadOnlyRunConfig(
        case_root=paths["case_root"],
        workspace=paths["workspace"],
        database=paths["database"],
        code_home=paths["code_home"],
        codex_executable=paths["codex_executable"],
        event_log=paths["event_log"],
        provider_identity=provider_identity,
    )
    factory_calls: list[Any] = []

    def forbidden_factory(owner, factory_config):
        del owner, factory_config
        factory_calls.append(True)
        raise AssertionError("adapter factory must not be called after redaction deny")

    result = LocalReadOnlyRunOrchestrator(config, adapter_factory=forbidden_factory).run(
        "w8-local-read-only-redaction-repeat-01",
        "must not execute",
    )
    serialized = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)
    checks = {
        "preflight_denied": result.preflight.status == "deny",
        "adapter_not_called": factory_calls == [],
        "owner_database_not_created": not paths["database"].exists(),
        "secret_absent_from_result": secret not in serialized,
        "redaction_status_is_denied": result.status == "denied",
        "config_digest_present": bool(result.preflight.config_digest),
        "case_paths_inside_case_root": all(_inside(case_dir, path) for path in paths.values()),
    }
    summary = {
        "control": "redaction",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "preflight_status": result.preflight.status,
            "orchestration_status": result.status,
            "adapter_factory_calls": len(factory_calls),
            "owner_database_present": paths["database"].exists(),
            "secret_occurrences_in_result": serialized.count(secret),
            "violation_codes": [item.code for item in result.preflight.violations],
        },
        "checks": checks,
        "case_root": str(case_dir),
    }
    write_json(case_dir / "summary.json", summary)
    return summary


def _default_deny_control(output_dir: Path) -> Dict[str, Any]:
    """Exercise the Codex adapter's unknown server-request default deny seam."""

    case_dir = output_dir / "default-deny" / "repeat-01"
    paths = _prepare_case(case_dir)
    run_id = "w8-local-read-only-default-deny-repeat-01"
    from zworkbench import CodexAppServerAdapter, CompositionOwner

    sent: list[Dict[str, Any]] = []
    with network_tripwire() as network_attempts:
        with CompositionOwner(paths["database"]) as owner:
            owner.create_run(run_id, "local_read_only", {"prompt": "unknown request"}, {"fixture": True})
            owner.start_run(run_id)
            adapter = CodexAppServerAdapter(
                owner,
                paths["codex_executable"],
                paths["code_home"],
                paths["workspace"],
                provider_identity=DEFAULT_PROVIDER,
                event_log=paths["event_log"],
            )
            adapter._write_message = lambda message: sent.append(dict(message))  # type: ignore[method-assign]
            adapter.active_run_id = run_id
            adapter._handle_server_request(
                {
                    "jsonrpc": "2.0",
                    "id": 77,
                    "method": "future/server-request.v1",
                    "params": {},
                }
            )
            adapter.active_run_id = None
            run = owner.get_run(run_id)
            results = run["results"]

    error = sent[0].get("error", {}) if len(sent) == 1 else {}
    checks = {
        "unknown_request_denied": error.get("code") == -32001,
        "deny_reason_identifies_request": "future/server-request.v1" in error.get("message", ""),
        "owner_safe_stopped": run.get("status") == "safe_stopped",
        "deny_result_recorded": any(item.get("kind") == "adapter.server_request.denied" for item in results),
        "no_semantic_completion": not any(item.get("kind") == "semantic" for item in results),
        "network_attempts_zero": len(network_attempts) == 0,
        "case_paths_inside_case_root": all(_inside(case_dir, path) for path in paths.values()),
    }
    summary = {
        "control": "default_deny",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "owner_run_status": run.get("status"),
            "responses_sent": len(sent),
            "response_error": error,
            "result_kinds": sorted(item.get("kind") for item in results),
            "network_attempts": network_attempts,
        },
        "checks": checks,
        "case_root": str(case_dir),
    }
    write_json(case_dir / "summary.json", summary)
    return summary


def run_security_suite(output_dir: Path) -> Dict[str, Any]:
    """Run all four W8 security controls in isolated case roots."""

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise FileExistsError("security output directory must be new or empty")
    else:
        output_dir.mkdir(parents=True)
    if read_json(MANIFEST).get("schema") != "zworkbench-w8-local-read-only-fixture/v1":
        raise ValueError("unexpected W8 fixture manifest schema")

    cases = [
        _identity_control(output_dir),
        _redaction_control(output_dir),
        _default_deny_control(output_dir),
    ]
    checks = {
        "all_controls_pass": all(item["status"] == "pass" for item in cases),
        "identity_control_present": any(item["control"] == "identity" for item in cases),
        "redaction_control_present": any(item["control"] == "redaction" for item in cases),
        "default_deny_control_present": any(item["control"] == "default_deny" for item in cases),
        "network_zero_across_controls": all(
            item.get("checks", {}).get("network_attempts_zero", True) for item in cases
        ),
    }
    summary = {
        "schema": SECURITY_RUNNER_SCHEMA,
        "fixture_schema": "zworkbench-w8-local-read-only-fixture/v1",
        "source_runner_schema": RUNNER_SCHEMA,
        "adapter_schema": FIXTURE_ADAPTER_SCHEMA,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "case_count": len(cases),
        "passed_case_count": sum(item["status"] == "pass" for item in cases),
        "cases": cases,
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "non_claims": [
            "The socket tripwire is process-local and is not host firewall evidence.",
            "The default-deny control is adapter seam evidence, not Codex native approval evidence.",
            "No real Provider, credential, or external side effect was used.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh evidence directory; defaults to a temporary directory")
    args = parser.parse_args()
    output_dir = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="w8-local-read-only-security-"))
    try:
        summary = run_security_suite(output_dir)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
