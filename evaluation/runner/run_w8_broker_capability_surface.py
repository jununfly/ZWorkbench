#!/usr/bin/env python3
"""Run the case-local capability-broker observable-boundary evaluation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_capability_broker" / "v1"
BROKER = FIXTURE / "capability_broker.py"
RUNS = REPO_ROOT / "evaluation" / "runs"
SCHEMA = "zworkbench-w8-capability-broker-evaluation/v1"
BROKER_SCHEMA = "zworkbench-w8-capability-broker/v1"
POLICY_SCHEMA = "zworkbench-w8-capability-broker-policy/v1"
REPEATS = 3
DENIED_EXIT = 23
SCENARIOS = (
    "credential_read_denied",
    "dns_external_denied",
    "network_external_denied",
    "process_unallowlisted_denied",
    "write_outside_denied",
    "dns_loopback_allow",
    "network_loopback_allow",
    "write_inside_allow",
    "unknown_operation_denied",
)

sys.path.insert(0, str(FIXTURE))
from capability_broker import send_request  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def policy_for(workspace: Path) -> Dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "workspace": str(workspace.resolve()),
        "allowed_operations": [
            "dns.resolve",
            "network.connect",
            "credential.read",
            "process.spawn",
            "effect.write",
        ],
        "allowed_dns": {"localhost": ["127.0.0.1"]},
        "allowed_network": [{"host": "127.0.0.1", "port": 11434}],
        "allowed_processes": [],
    }


def setup_case(case_dir: Path, scenario: str, repeat: int) -> Dict[str, Any]:
    workspace = case_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    outside = case_dir / "outside-target.txt"
    outside.write_text("outside-original\n", encoding="utf-8")
    policy = policy_for(workspace)
    policy_path = case_dir / "policy.json"
    write_json(policy_path, policy)
    # macOS limits AF_UNIX socket paths to a small fixed maximum.  Keep the
    # socket outside the evidence tree so a long repository/run/case path
    # cannot make an otherwise valid broker case fail before it starts.
    socket_dir = Path(tempfile.mkdtemp(prefix="zwb-b-", dir="/tmp"))
    return {
        "case_dir": case_dir,
        "workspace": workspace,
        "outside": outside,
        "policy": policy,
        "policy_path": policy_path,
        "socket_dir": socket_dir,
        "socket": socket_dir / "b.sock",
        "audit": case_dir / "broker-audit.jsonl",
        "log": case_dir / "broker.log",
        "scenario": scenario,
        "repeat": repeat,
    }


def scenario_request(case: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    scenario = case["scenario"]
    base = {"schema": BROKER_SCHEMA, "request_id": run_id, "resource_class": "case-local"}
    if scenario == "credential_read_denied":
        return {**base, "operation": "credential.read", "resource_class": "credential", "target": "credential://provider/api-key"}
    if scenario == "dns_external_denied":
        return {**base, "operation": "dns.resolve", "resource_class": "dns", "hostname": "api.example.com"}
    if scenario == "network_external_denied":
        return {**base, "operation": "network.connect", "resource_class": "network", "host": "198.51.100.1", "port": 443}
    if scenario == "process_unallowlisted_denied":
        return {**base, "operation": "process.spawn", "resource_class": "process", "executable": "/usr/bin/curl", "argv": ["https://example.invalid"]}
    if scenario == "write_outside_denied":
        return {**base, "operation": "effect.write", "resource_class": "effect", "target": str(case["outside"]), "content": "must-not-write"}
    if scenario == "dns_loopback_allow":
        return {**base, "operation": "dns.resolve", "resource_class": "dns", "hostname": "localhost"}
    if scenario == "network_loopback_allow":
        return {**base, "operation": "network.connect", "resource_class": "network", "host": "127.0.0.1", "port": 11434}
    if scenario == "write_inside_allow":
        return {**base, "operation": "effect.write", "resource_class": "effect", "target": str(case["workspace"] / "allowed.txt"), "content": "case-local-allowed"}
    if scenario == "unknown_operation_denied":
        return {**base, "operation": "filesystem.delete", "resource_class": "unknown", "target": str(case["outside"])}
    raise ValueError(f"unknown scenario: {scenario}")


def wait_for_socket(path: Path, process: subprocess.Popen, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.02)
    return path.exists()


def start_broker(case: Dict[str, Any]) -> Tuple[subprocess.Popen, Any]:
    log = case["log"].open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(BROKER),
            "server",
            "--socket",
            str(case["socket"]),
            "--policy",
            str(case["policy_path"]),
            "--audit",
            str(case["audit"]),
        ],
        cwd=case["case_dir"],
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if not wait_for_socket(case["socket"], process):
        if process.poll() is None:
            process.terminate()
        log.close()
        raise RuntimeError("capability broker failed readiness")
    return process, log


def stop_broker(process: Optional[subprocess.Popen], log: Any) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    log.close()


def cleanup_socket_dir(path: Path) -> None:
    """Remove only the short, runner-owned temporary IPC directory."""

    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def read_audit(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_case(output_dir: Path, scenario: str, repeat: int) -> Dict[str, Any]:
    case = setup_case(output_dir / "cases" / scenario / f"repeat-{repeat:02d}", scenario, repeat)
    run_id = f"w8-capability-broker-{scenario}-{repeat:02d}"
    request = scenario_request(case, run_id)
    write_json(case["case_dir"] / "request.json", request)
    broker = None
    log = None
    try:
        broker, log = start_broker(case)
        response = send_request(case["socket"], request)
        audit = read_audit(case["audit"])
        outside_content = case["outside"].read_text(encoding="utf-8")
        common = {
            "response_schema": response.get("schema") == BROKER_SCHEMA,
            "request_id_correlated": response.get("request_id") == run_id,
            "policy_digest_present": isinstance(response.get("policy_sha256"), str) and len(response["policy_sha256"]) == 64,
            "external_io_zero": response.get("external_io_count") == 0,
        }
        if scenario in {"credential_read_denied", "dns_external_denied", "network_external_denied", "process_unallowlisted_denied", "write_outside_denied", "unknown_operation_denied"}:
            expected_reasons = {
                "credential_read_denied": "credential_access_not_allowlisted",
                "dns_external_denied": "dns_name_not_allowlisted",
                "network_external_denied": "network_endpoint_not_allowlisted",
                "process_unallowlisted_denied": "process_not_allowlisted",
                "write_outside_denied": "target_outside_workspace",
                "unknown_operation_denied": "unknown_operation",
            }
            checks = {
                **common,
                "decision_deny": response.get("decision") == "deny",
                "reason_exact": response.get("reason") == expected_reasons[scenario],
                "effect_not_performed": response.get("effect_status") == "not-performed",
                "physical_effect_zero": response.get("physical_effect_count") == 0,
                "one_durable_deny_receipt": len(audit) == 1 and audit[0].get("decision") == "deny",
                "outside_target_unchanged": outside_content == "outside-original\n",
            }
        elif scenario == "dns_loopback_allow":
            checks = {
                **common,
                "decision_allow": response.get("decision") == "allow",
                "reason_exact": response.get("reason") == "loopback_dns_static_allowlist",
                "static_loopback_address": response.get("resolved_addresses") == ["127.0.0.1"],
                "system_resolution_not_used": response.get("resolution_mode") == "static-broker-allowlist",
                "physical_effect_zero": response.get("physical_effect_count") == 0,
                "one_durable_receipt": len(audit) == 1 and audit[0].get("decision") == "allow",
            }
        elif scenario == "network_loopback_allow":
            checks = {
                **common,
                "decision_allow": response.get("decision") == "allow",
                "reason_exact": response.get("reason") == "loopback_endpoint_allowlisted",
                "decision_only_no_connect": response.get("execution_mode") == "decision-only-no-connect",
                "physical_effect_zero": response.get("physical_effect_count") == 0,
                "one_durable_receipt": len(audit) == 1 and audit[0].get("decision") == "allow",
            }
        else:
            target = case["workspace"] / "allowed.txt"
            checks = {
                **common,
                "decision_allow": response.get("decision") == "allow",
                "reason_exact": response.get("reason") == "allowlisted_workspace_write",
                "effect_completed": response.get("effect_status") == "completed",
                "physical_effect_once": response.get("physical_effect_count") == 1,
                "target_content_expected": target.exists() and target.read_text(encoding="utf-8") == "case-local-allowed",
                "decision_precedes_complete": len(audit) == 2 and audit[0].get("phase") == "decision" and audit[0].get("effect_status") == "claimed" and audit[1].get("phase") == "complete",
                "claim_has_zero_effect": len(audit) == 2 and audit[0].get("physical_effect_count") == 0,
            }
        result = {
            "schema": SCHEMA,
            "run_id": run_id,
            "scenario": scenario,
            "repeat": repeat,
            "status": "pass" if all(checks.values()) else "unknown",
            "observed": {"response": response, "audit_count": len(audit), "audit": audit, "outside_content": outside_content},
            "checks": checks,
            "evidence_dir": str(case["case_dir"]),
        }
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "run_id": run_id,
            "scenario": scenario,
            "repeat": repeat,
            "status": "unknown",
            "error": {"type": type(exc).__name__},
            "evidence_dir": str(case["case_dir"]),
        }
    finally:
        stop_broker(broker, log) if log is not None else None
        cleanup_socket_dir(case["socket_dir"])
    result.setdefault("observed", {})["broker_socket_cleaned"] = not case["socket_dir"].exists()
    result.setdefault("checks", {})["broker_socket_cleaned"] = not case["socket_dir"].exists()
    if result["status"] == "pass" and not result["checks"]["broker_socket_cleaned"]:
        result["status"] = "unknown"
    write_json(case["case_dir"] / "result.json", result)
    return result


def run_suite(output_dir: Path, repeats: int = REPEATS) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [run_case(output_dir, scenario, repeat) for scenario in SCENARIOS for repeat in range(1, repeats + 1)]
    passed = sum(case["status"] == "pass" for case in cases)
    summary = {
        "schema": SCHEMA,
        "run_id": output_dir.name,
        "started_at": now(),
        "classification": "acceptance/evaluation",
        "status": "candidate-pass" if passed == len(cases) else "unknown/stop",
        "interface": {
            "broker_schema": BROKER_SCHEMA,
            "policy_schema": POLICY_SCHEMA,
            "transport": "case-local Unix socket",
            "canonical_owner": "evaluation case audit JSONL; not ZWorkbench product owner",
            "dns_mode": "static broker allowlist; no system resolver",
        },
        "cases": cases,
        "cases_total": len(cases),
        "cases_passed": passed,
        "cases_unknown": len(cases) - passed,
        "threshold": {"scenarios": list(SCENARIOS), "repeats_per_scenario": repeats, "external_io": 0, "raw_credentials": 0},
        "checks": {
            "all_case_thresholds_pass": passed == len(cases),
            "dns_denial_is_observable_in_broker": all(case.get("checks", {}).get("reason_exact") is True for case in cases if case["scenario"] == "dns_external_denied"),
            "external_io_zero": all(case.get("checks", {}).get("external_io_zero") is True for case in cases),
            "real_provider": False,
            "real_credentials": False,
            "real_project_write": False,
            "default_product_runtime_changed": False,
        },
        "interpretation": "A case-local broker can expose deterministic DNS/network/credential/process/effect decisions and durable receipts. This is acceptance evidence only; it does not prove Codex host-profile inheritance, native approval, or production write safety.",
        "finished_at": now(),
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats < 3:
        raise SystemExit("W8 capability-broker threshold requires at least 3 repeats")
    run_id = datetime.now(timezone.utc).strftime("w8-capability-broker-%Y%m%dT%H%M%S") + "Z"
    output_dir = (args.output or (RUNS / run_id)).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = run_suite(output_dir, repeats=args.repeats)
    print(json.dumps({"summary": str(output_dir / "summary.json"), "status": summary["status"], "cases": f"{summary['cases_passed']}/{summary['cases_total']}"}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "candidate-pass" else 1


if __name__ == "__main__":
    sys.exit(main())
