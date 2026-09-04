#!/usr/bin/env python3
"""Run the isolated W8 H2 Worker handshake fixture.

The runner exercises the owner-backed :class:`WorkerBridge` against a fixed,
deterministic process.  It intentionally uses a case-local workspace and a
fake loopback Provider; its output is fixture-composed evidence, not proof of
the real Codex runtime or Provider compatibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_handshake" / "v1" / "worker_fixture.py"
RUNNER_SCHEMA = "zworkbench-w8-worker-handshake-runner/v1"
SCENARIOS = (
    "success",
    "unknown",
    "mismatch",
    "identity-mismatch",
    "provenance-mismatch",
    "unknown-message",
    "unknown-field",
    "nonzero",
    "crash",
    "hang",
    "malformed",
)
EXPECTED_FAILURE_CODES = {
    "unknown": "handshake_identity_incomplete",
    "mismatch": "handshake_schema_unknown",
    "identity-mismatch": "handshake_identity_mismatch",
    "provenance-mismatch": "handshake_provenance_mismatch",
    "unknown-message": "handshake_message_unknown",
    "unknown-field": "handshake_field_unknown",
    "nonzero": "worker_exit_nonzero",
    "crash": "handshake_response_missing",
    "hang": "worker_timeout",
    "malformed": "handshake_invalid_json",
}

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import (  # noqa: E402
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


def file_digest(path: Path) -> str:
    """Return a stable digest for a fixture artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def value_digest(value: Any) -> str:
    """Return a digest for non-secret case identity metadata."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write one reviewable JSON evidence file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_bridge(owner: CompositionOwner, case_root: Path, scenario: str) -> WorkerBridge:
    """Construct the fixed H2 bridge configuration for one scenario."""

    workspace_digest = value_digest({"kind": "case-local", "relative_path": "workspace"})
    environment_digest = value_digest(
        {
            "bridge_schema": "zworkbench-worker-bridge/v1",
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "workspace_digest": workspace_digest,
        }
    )
    return WorkerBridge(
        owner,
        sys.executable,
        case_root,
        worker_args=(str(FIXTURE), "--scenario", scenario),
        worker_artifact_identity=ComponentIdentity(
            name="codex-worker-fixture",
            version="1.0.0",
            digest=file_digest(FIXTURE),
            source="evaluation/fixtures/w8_worker_handshake/v1",
        ),
        worker_schema_identity=ComponentIdentity(
            name="zworkbench.worker",
            version="v1",
            digest=value_digest("zworkbench.worker.v1"),
            source="src/zworkbench/worker_contract.py",
        ),
        provider_identity=ProviderIdentity(
            provider="fake-loopback",
            model="fixture-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        ),
        policy_digest=value_digest("h2-read-only-policy"),
        environment_digest=environment_digest,
        workspace_digest=workspace_digest,
    )


def result_by_kind(run: Dict[str, Any], kind: str) -> Dict[str, Any] | None:
    """Return the latest result of a given kind from an owner snapshot."""

    matches = [item for item in run["results"] if item["kind"] == kind]
    return matches[-1] if matches else None


def run_case(output_dir: Path, scenario: str) -> Dict[str, Any]:
    """Run and verify one fresh case-local H2 scenario."""

    if scenario not in SCENARIOS:
        raise ValueError(f"unknown H2 scenario: {scenario}")
    case_root = output_dir / "cases" / scenario
    if case_root.exists():
        raise FileExistsError(f"case output already exists: {case_root}")
    (case_root / "workspace").mkdir(parents=True)

    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    owner.create_run("parent-1", "dsh.bootstrap", {"operation": "worker-handshake"})
    owner.start_run("parent-1")
    bridge = make_bridge(owner, case_root, scenario)
    error = None
    try:
        try:
            bridge.handshake(
                "parent-1",
                child_run_id="child-1",
                attempt_id="attempt-1",
                dsh_session_id="dsh-session-1",
                dsh_turn_id="dsh-turn-1",
                timeout=1.0,
            )
        except WorkerBridgeError as exc:
            error = {"type": type(exc).__name__, "code": exc.code}
    finally:
        bridge.close()
        process_absent = bridge.process is None
        owner.close()

    with CompositionOwner(case_root / "state" / "composition.sqlite3") as reopened:
        parent = reopened.get_run("parent-1")
        child = reopened.get_run("child-1")

    child_kinds = sorted(item["kind"] for item in child["results"])
    exit_result = result_by_kind(child, "worker.exit")
    handshake_result = result_by_kind(child, "worker.handshake")
    if scenario == "success":
        identity = (handshake_result or {}).get("value", {}).get("identity", {})
        checks = {
            "bridge_succeeded": error is None and handshake_result is not None,
            "parent_remains_running": parent["status"] == "running",
            "child_completed": child["status"] == "completed",
            "identity_complete": bool(identity) and all(value != "unknown" for value in identity.values()),
            "identity_correlated": identity.get("parent_run_id") == "parent-1"
            and identity.get("child_run_id") == "child-1"
            and identity.get("attempt_id") == "attempt-1"
            and identity.get("dsh_session_id") == "dsh-session-1"
            and identity.get("dsh_turn_id") == "dsh-turn-1"
            and identity.get("codex_thread_id") == "codex-thread-1"
            and identity.get("codex_turn_id") == "codex-turn-1",
            "request_result_recorded": "worker.handshake.request" in child_kinds,
            "exit_receipt_recorded": exit_result is not None and exit_result["value"]["exit_code"] == 0,
            "effects_zero": not parent["effects"] and not child["effects"],
            "bridge_process_absent": process_absent,
        }
    else:
        checks = {
            "bridge_failed_closed": error is not None and error["code"] == EXPECTED_FAILURE_CODES[scenario],
            "parent_safe_stopped": parent["status"] == "safe_stopped",
            "child_safe_stopped": child["status"] == "safe_stopped",
            "error_result_recorded": "worker.error" in child_kinds,
            "exit_receipt_recorded": exit_result is not None,
            "semantic_success_absent": "semantic" not in child_kinds,
            "effects_zero": not parent["effects"] and not child["effects"],
            "bridge_process_absent": process_absent,
        }

    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "scenario": scenario,
        "run_id": "parent-1",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "parent_status": parent["status"],
            "child_status": child["status"],
            "error": error,
            "child_result_kinds": child_kinds,
            "worker_exit_code": exit_result["value"]["exit_code"] if exit_result else None,
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "checks": checks,
        "non_claims": [
            "This does not prove a real Codex runtime or app-server compatibility.",
            "This does not prove H3 coding, H4 recovery, H5 replay, host sandboxing, or Provider behavior.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_suite(output_dir: Path) -> Dict[str, Any]:
    """Run all H2 fixture scenarios into a new or empty evidence directory."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("H2 output directory must be new or empty")
    if not FIXTURE.is_file():
        raise FileNotFoundError(f"H2 fixture is missing: {FIXTURE}")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [run_case(output_dir, scenario) for scenario in SCENARIOS]
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "status": "pass" if all(item["status"] == "pass" for item in scenarios) else "fail",
        "passed_scenarios": sum(item["status"] == "pass" for item in scenarios),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "formal_h2_status": "HOLD: real Codex Worker artifact and runtime compatibility are not claimed",
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="new or empty case-local output directory")
    args = parser.parse_args()
    summary = run_suite(args.output.expanduser().resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
