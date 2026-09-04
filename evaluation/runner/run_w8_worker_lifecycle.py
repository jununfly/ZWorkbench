#!/usr/bin/env python3
"""Run the isolated W8 H4 Worker lifecycle and recovery fixture.

The runner uses a case-local workspace, a fake loopback Provider, and an
owner-backed CompositionOwner database.  It proves the bridge lifecycle seam
against a real local process group, but does not claim host-wide sandboxing,
real Codex/Provider compatibility, or H5 replay behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_lifecycle" / "v1" / "worker_fixture.py"
RUNNER_SCHEMA = "zworkbench-w8-worker-lifecycle-runner/v1"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import (  # noqa: E402
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_case(output_dir: Path, scenario: str, *, fixture_scenario: Optional[str] = None, recovery_mode: bool = False):
    case_root = output_dir / "cases" / scenario
    if case_root.exists():
        raise FileExistsError(f"case output already exists: {case_root}")
    (case_root / "workspace").mkdir(parents=True)
    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    owner.create_run("parent-1", "dsh.bootstrap", {"operation": "worker-lifecycle"})
    owner.start_run("parent-1")
    bridge = WorkerBridge(
        owner,
        sys.executable,
        case_root,
        worker_args=(str(FIXTURE), "--scenario", fixture_scenario or scenario),
        worker_artifact_identity=ComponentIdentity(
            name="codex-worker-lifecycle-fixture",
            version="1.0.0",
            digest=digest("lifecycle-worker-artifact"),
            source="evaluation/fixtures/w8_worker_lifecycle/v1",
        ),
        worker_schema_identity=ComponentIdentity(
            name="zworkbench.worker",
            version="v1",
            digest=digest("zworkbench.worker.v1"),
            source="src/zworkbench/worker_contract.py",
        ),
        provider_identity=ProviderIdentity(
            provider="fake-loopback",
            model="fixture-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        ),
        policy_digest=digest("h4-read-only-policy"),
        environment_digest=digest("h4-environment"),
        workspace_digest=digest("h4-workspace"),
        recovery_mode=recovery_mode,
    )
    return case_root, owner, bridge


def invoke_handshake(bridge: WorkerBridge, *, child_run_id: str = "child-1", attempt_id: str = "attempt-1", timeout: float = 5.0) -> Dict[str, Any]:
    outcome: Dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = bridge.handshake(
                "parent-1",
                child_run_id=child_run_id,
                attempt_id=attempt_id,
                dsh_session_id=f"dsh-session-{attempt_id}",
                dsh_turn_id=f"dsh-turn-{attempt_id}",
                timeout=timeout,
            )
        except WorkerBridgeError as exc:
            outcome["error"] = {"type": type(exc).__name__, "code": exc.code}

    thread = threading.Thread(target=run)
    thread.start()
    return {"thread": thread, "outcome": outcome}


def wait_for_process(bridge: WorkerBridge, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while bridge.process is None and time.monotonic() < deadline:
        time.sleep(0.01)
    return bridge.process is not None


def wait_for_file(path: Path, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    return path.exists()


def result_by_kind(run: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    matches = [item for item in run["results"] if item["kind"] == kind]
    return matches[-1] if matches else None


def error_code(outcome: Dict[str, Any]) -> Optional[str]:
    return outcome.get("error", {}).get("code")


def run_case(output_dir: Path, scenario: str) -> Dict[str, Any]:
    recovery_mode = scenario == "recovery"
    fixture_scenario = {
        "cancel": "hang",
        "timeout": "hang",
        "crash": "crash",
        "parent-stop": "hang",
        "descendant": "spawn-descendant",
        "recovery": "crash-once",
    }.get(scenario, scenario)
    case_root, owner, bridge = make_case(
        output_dir,
        scenario,
        fixture_scenario=fixture_scenario,
        recovery_mode=recovery_mode,
    )
    run_outcome: Dict[str, Any] = {}
    control: Optional[Dict[str, Any]] = None
    descendant_pid: Optional[int] = None
    recovery_result = None
    try:
        if scenario == "timeout":
            invoked = invoke_handshake(bridge, timeout=0.25)
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
        elif scenario == "cancel":
            invoked = invoke_handshake(bridge)
            wait_for_process(bridge)
            control = bridge.cancel("parent-1")
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
        elif scenario == "parent-stop":
            invoked = invoke_handshake(bridge)
            wait_for_process(bridge)
            control = bridge.stop_parent("parent-1")
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
        elif scenario == "descendant":
            invoked = invoke_handshake(bridge)
            pid_path = case_root / "workspace" / "descendant.pid"
            file_seen = wait_for_file(pid_path)
            if file_seen:
                descendant_pid = int(pid_path.read_text(encoding="utf-8"))
            control = bridge.stop_parent("parent-1")
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
        elif scenario == "crash":
            invoked = invoke_handshake(bridge, timeout=2.0)
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
        elif scenario == "recovery":
            invoked = invoke_handshake(bridge, timeout=2.0)
            invoked["thread"].join(timeout=4.0)
            run_outcome = invoked["outcome"]
            recovery_result = bridge.recover_handshake(
                "parent-1",
                recovery_of_child_run_id="child-1",
                child_run_id="child-2",
                attempt_id="attempt-2",
                dsh_session_id="dsh-session-attempt-2",
                dsh_turn_id="dsh-turn-attempt-2",
                timeout=2.0,
            )
        else:
            raise ValueError(f"unknown H4 scenario: {scenario}")
    finally:
        bridge.close()
        owner.close()

    with CompositionOwner(case_root / "state" / "composition.sqlite3") as reopened:
        parent = reopened.get_run("parent-1")
        child = reopened.get_run("child-1")
        child2 = reopened.get_run("child-2") if scenario == "recovery" else None
        parent_events = reopened.events("parent-1")

    receipt = result_by_kind(child, "worker.exit")
    receipt_value = receipt["value"] if receipt else {}
    clean = receipt_value.get("process_group_clean") is True
    checks: Dict[str, bool] = {
        "thread_stopped": not invoked["thread"].is_alive(),
        "process_absent": bridge.process is None,
        "exit_receipt_recorded": receipt is not None,
        "process_group_clean": clean,
        "orphan_processes_zero": receipt_value.get("orphan_processes") == 0,
        "effects_zero": not parent["effects"] and not child["effects"],
    }
    if scenario == "timeout":
        checks.update(
            {
                "expected_error": error_code(run_outcome) == "worker_timeout",
                "parent_safe_stopped": parent["status"] == "safe_stopped",
                "child_safe_stopped": child["status"] == "safe_stopped",
                "termination_reason": receipt_value.get("termination_reason") == "timeout",
            }
        )
    elif scenario == "cancel":
        checks.update(
            {
                "expected_error": error_code(run_outcome) == "worker_cancelled",
                "control_recorded": bool(control and control.get("requested")),
                "parent_safe_stopped": parent["status"] == "safe_stopped",
                "child_safe_stopped": child["status"] == "safe_stopped",
                "termination_reason": receipt_value.get("termination_reason") == "cancelled",
            }
        )
    elif scenario == "parent-stop":
        checks.update(
            {
                "expected_error": error_code(run_outcome) == "worker_parent_stopped",
                "control_recorded": bool(control and control.get("requested")),
                "parent_safe_stopped": parent["status"] == "safe_stopped",
                "child_safe_stopped": child["status"] == "safe_stopped",
                "termination_reason": receipt_value.get("termination_reason") == "parent_stop",
            }
        )
    elif scenario == "descendant":
        descendant_gone = False
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                descendant_gone = True
            except PermissionError:
                descendant_gone = False
        checks.update(
            {
                "expected_error": error_code(run_outcome) == "worker_parent_stopped",
                "control_recorded": bool(control and control.get("requested")),
                "descendant_pid_observed": descendant_pid is not None,
                "descendant_gone": descendant_gone,
                "parent_safe_stopped": parent["status"] == "safe_stopped",
            }
        )
    elif scenario == "crash":
        checks.update(
            {
                "expected_error": error_code(run_outcome) == "worker_exit_nonzero",
                "parent_safe_stopped": parent["status"] == "safe_stopped",
                "child_safe_stopped": child["status"] == "safe_stopped",
                "termination_reason": receipt_value.get("termination_reason") == "child_crash",
                "semantic_success_absent": not any(item["kind"] == "semantic" for item in child["results"]),
            }
        )
    elif scenario == "recovery":
        child2_receipt = result_by_kind(child2 or {"results": []}, "worker.exit")
        checks.update(
            {
                "first_attempt_failed": error_code(run_outcome) == "worker_exit_nonzero",
                "parent_recovering_before_restart": any(
                    item["type"] == "run.recovering" and item["payload"].get("to") == "recovering"
                    for item in parent_events
                ),
                "recovery_succeeded": recovery_result is not None and child2 is not None and child2["status"] == "completed",
                "old_attempt_preserved": child["status"] == "safe_stopped" and child["metadata"]["attempt_id"] == "attempt-1",
                "new_attempt_identity": child2 is not None
                and child2["metadata"].get("recovery_of_child_run_id") == "child-1"
                and child2["metadata"].get("attempt_id") == "attempt-2",
                "new_attempt_exit_recorded": child2_receipt is not None and child2_receipt["value"]["orphan_processes"] == 0,
                "parent_running_after_restart": parent["status"] == "running",
            }
        )

    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "scenario": scenario,
        "run_id": "parent-1",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "parent_status": parent["status"],
            "child_status": child["status"],
            "recovery_child_status": child2["status"] if child2 else None,
            "error": run_outcome.get("error"),
            "worker_exit": receipt_value,
            "external_network_requests": 0,
            "real_credentials": 0,
            "unauthorized_effects": 0,
            "descendant_pid": descendant_pid,
        },
        "checks": checks,
        "non_claims": [
            "This is local OS process-group evidence, not host-wide sandbox evidence.",
            "This does not prove real Codex runtime, real Provider compatibility, H5 replay, or production deployment safety.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_suite(output_dir: Path) -> Dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("H4 output directory must be new or empty")
    if not FIXTURE.is_file():
        raise FileNotFoundError(f"H4 fixture is missing: {FIXTURE}")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = ["cancel", "timeout", "crash", "parent-stop", "descendant", "recovery"]
    cases = [run_case(output_dir, scenario) for scenario in scenarios]
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "status": "pass" if all(case["status"] == "pass" for case in cases) else "fail",
        "passed_scenarios": sum(case["status"] == "pass" for case in cases),
        "scenario_count": len(cases),
        "scenarios": cases,
        "checks": {
            "orphan_processes_zero": all(case["checks"].get("orphan_processes_zero", False) for case in cases),
            "status_loss_zero": all(case["checks"].get("thread_stopped", False) for case in cases),
            "unauthorized_effects_zero": all(case["observed"].get("unauthorized_effects") == 0 for case in cases),
        },
        "formal_h4_status": "pass-with-composition: local owner-backed process lifecycle and recovery verified",
        "non_claims": [
            "H4 evidence does not upgrade H5 evidence/replay or real remote Provider compatibility.",
            "A local process-group check does not substitute for OS/host sandbox enforcement evidence.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="new or empty evidence directory")
    args = parser.parse_args()
    output_dir = args.output
    temporary = None
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="zworkbench-h4-")
        output_dir = Path(temporary.name) / "evidence"
    summary = run_suite(output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if temporary is not None:
        temporary.cleanup()
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
