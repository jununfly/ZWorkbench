#!/usr/bin/env python3
"""Run the W7 Codex candidate C7 operations and lifecycle audit.

The runner deliberately separates machine-verifiable evidence from the human
operator time gate.  It never mutates the global Codex installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c7"
OPERATIONS = FIXTURE / "c7-audit.py"
MANIFEST = REPO_ROOT / "docs" / "plans" / "w7-codex-candidate-manifest.json"
PRIMARY_SOURCES = REPO_ROOT / "docs" / "plans" / "research" / "w7-codex-c7-primary-sources.md"
RUNS = REPO_ROOT / "evaluation" / "runs"
CODEX_DEFAULT = shutil.which("codex")
RUNNER_VERSION = "w7-codex-c7-audit-runner/v1"
SCHEMA = "zworkbench-w7-codex-c7/v1"
SCENARIOS = ("identity", "install", "upgrade", "backup_restore", "fault_diagnosis", "exit")
TIMED_SCENARIOS = ("install", "upgrade", "backup_restore", "fault_diagnosis")
REPEATS = 3
THRESHOLDS_MINUTES = {"install": 90, "upgrade": 30, "backup_restore": 30, "fault_diagnosis": 30}
MAX_MAINTAINED_SERVICES = 3
REQUIRED_EVENT_TYPES = (
    "operation.started",
    "environment.checked",
    "precondition.prepared",
    "operation.step",
    "verification.completed",
    "operation.completed",
)
EVIDENCE_REFERENCES = {
    "c2": REPO_ROOT / "evaluation" / "runs" / "w6-0.1-c2-20260830T144743-847310Z" / "summary.json",
    "c3": REPO_ROOT / "evaluation" / "runs" / "w7-codex-c3-c4-20260830T162343-560708Z" / "summary.json",
    "c4": REPO_ROOT / "evaluation" / "runs" / "w7-codex-c4-approval-20260831T032346-194000Z" / "summary.json",
    "c5": REPO_ROOT / "evaluation" / "runs" / "w7-codex-c5-c6-20260830T165759-141575Z" / "summary.json",
    "c6": REPO_ROOT / "evaluation" / "runs" / "w7-codex-c5-c6-20260830T165822-636804Z" / "summary.json",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path: Path):
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hasher = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        hasher.update(str(child.relative_to(path)).encode("utf-8"))
        hasher.update(child.read_bytes())
    return hasher.hexdigest()


def run_fixture(case_dir: Path, scenario: str, repeat: int, codex: str):
    workspace = case_dir / "workspace"
    output_dir = case_dir / "operation"
    run_id = f"w7-c7-{scenario}-repeat-{repeat:02d}"
    command = [
        sys.executable,
        str(OPERATIONS),
        "--scenario",
        scenario,
        "--workspace",
        str(workspace),
        "--output-dir",
        str(output_dir),
        "--run-id",
        run_id,
        "--codex",
        codex,
        "--candidate-manifest",
        str(MANIFEST),
        "--primary-sources",
        str(PRIMARY_SOURCES),
    ]
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=90, check=False)
        result = {"command": command, "returncode": completed.returncode, "timed_out": False, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as exc:
        result = {"command": command, "returncode": None, "timed_out": True, "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    write_json(case_dir / "process-result.json", result)
    return result


def verify_case(case_dir: Path, scenario: str, repeat: int, process_result, human_timings):
    operation_dir = case_dir / "operation"
    operation = read_json(operation_dir / "operation-result.json") if (operation_dir / "operation-result.json").exists() else {}
    services = read_json(operation_dir / "service-manifest.json") if (operation_dir / "service-manifest.json").exists() else {}
    dependencies = read_json(operation_dir / "dependency-manifest.json") if (operation_dir / "dependency-manifest.json").exists() else {}
    license_record = read_json(operation_dir / "license-audit.json") if (operation_dir / "license-audit.json").exists() else {}
    events = read_jsonl(operation_dir / "operation-events.jsonl")
    workspace = Path(operation["workspace"]).resolve() if operation.get("workspace") else None
    case_root = case_dir.resolve()
    human_minutes = human_timings.get(scenario)
    human_status = "not-applicable" if scenario not in TIMED_SCENARIOS else ("unknown" if human_minutes is None else ("pass" if human_minutes <= THRESHOLDS_MINUTES[scenario] else "fail"))
    event_types = {event.get("type") for event in events}
    event_fields_complete = all(all(field in event for field in ("event_id", "run_id", "at", "type")) for event in events)
    workspace_isolated = bool(workspace and (workspace == case_root or case_root in workspace.parents))
    machine_checks = {
        "process_passed": process_result.get("returncode") == 0 and not process_result.get("timed_out"),
        "scenario_correct": operation.get("scenario") == scenario,
        "operation_completed": operation.get("status") == "completed",
        "operation_checks_pass": bool(operation.get("checks")) and all(operation["checks"].values()),
        "required_event_types_complete": set(REQUIRED_EVENT_TYPES).issubset(event_types),
        "required_event_fields_complete": event_fields_complete,
        "workspace_isolated": workspace_isolated,
        "network_calls_zero": operation.get("network_calls") == 0,
        "real_credentials_false": operation.get("real_credentials") is False,
        "production_data_false": operation.get("production_data") is False,
        "service_count_within_threshold": isinstance(services.get("maintained_service_count"), int) and services["maintained_service_count"] <= MAX_MAINTAINED_SERVICES and services.get("provider_and_host_os_counted") is False,
        "no_extra_expert_declared": dependencies.get("operator_expert_required") is False,
        "license_declared_and_source_recorded": license_record.get("declared_license") == "Apache-2.0" and license_record.get("source_primary_findings_present") is True,
    }
    candidate_action_checks = {
        "candidate_install_exercised": operation.get("operation_details", {}).get("candidate_install_status") == "exercised",
        "candidate_upgrade_and_rollback_exercised": operation.get("operation_details", {}).get("candidate_upgrade_status") == "exercised",
    }
    passed = all(machine_checks.values())
    return {
        "scenario": scenario,
        "repeat": repeat,
        "status": "pass" if passed else "unknown",
        "human_timing_status": human_status,
        "threshold_minutes": THRESHOLDS_MINUTES.get(scenario),
        "observed": {
            "machine_elapsed_seconds": operation.get("machine_elapsed_seconds"),
            "machine_elapsed_source": operation.get("machine_elapsed_source"),
            "human_elapsed_minutes": human_minutes,
            "human_timed": human_minutes is not None,
            "human_step_count": operation.get("human_step_count"),
            "maintained_service_count": services.get("maintained_service_count"),
            "managed_services": [item.get("name") for item in services.get("managed_services", [])],
            "event_count": len(events),
            "operation_kind": operation.get("operation_details", {}).get("operation_kind"),
            "candidate_action_status": {key: operation.get("operation_details", {}).get(key) for key in ("candidate_install_status", "candidate_upgrade_status") if key in operation.get("operation_details", {})},
            "license": license_record.get("declared_license"),
        },
        "checks": machine_checks | {"human_timing_within_threshold": human_status in {"pass", "not-applicable"}} | candidate_action_checks,
        "evidence_dir": str(case_dir),
    }


def load_human_timings(path: Path | None):
    if path is None:
        return {}
    values = read_json(path)
    if not isinstance(values, dict):
        raise SystemExit("--human-timings-json must contain an object keyed by scenario")
    result = {}
    for scenario, value in values.items():
        if scenario not in TIMED_SCENARIOS:
            raise SystemExit(f"unknown human timing scenario: {scenario}")
        minutes = value.get("minutes") if isinstance(value, dict) else value
        if minutes is None:
            continue
        if not isinstance(minutes, (int, float)) or minutes < 0:
            raise SystemExit(f"human timing for {scenario} must be a non-negative number of minutes")
        result[scenario] = float(minutes)
    return result


def evidence_identity():
    records = {}
    for name, path in EVIDENCE_REFERENCES.items():
        record = {"path": str(path), "exists": path.is_file(), "sha256": digest(path) if path.is_file() else None}
        if path.is_file():
            summary = read_json(path)
            record.update({"run_id": summary.get("run_id"), "mode": summary.get("mode"), "status": summary.get("status")})
        records[name] = record
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--human-timings-json", type=Path)
    parser.add_argument("--codex", default=CODEX_DEFAULT)
    args = parser.parse_args()
    if not args.codex:
        raise SystemExit("codex executable is not installed")
    if args.repeats != REPEATS:
        raise SystemExit(f"W7 C7 requires exactly {REPEATS} repeats per scenario")
    human_timings = load_human_timings(args.human_timings_json)
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w7-codex-c7-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "human-timing-template.json", {
        scenario: {"minutes": human_timings.get(scenario), "status": "measured" if scenario in human_timings else "unknown", "threshold_minutes": THRESHOLDS_MINUTES[scenario], "note": "Use a real single-operator stopwatch; never substitute machine_elapsed_seconds."}
        for scenario in TIMED_SCENARIOS
    })
    case_results = []
    for scenario in SCENARIOS:
        for repeat in range(1, REPEATS + 1):
            case_dir = output_dir / "cases" / scenario / f"repeat-{repeat:02d}"
            case_dir.mkdir(parents=True, exist_ok=False)
            process_result = run_fixture(case_dir, scenario, repeat, args.codex)
            case_results.append(verify_case(case_dir, scenario, repeat, process_result, human_timings))
    machine_passed = sum(item["status"] == "pass" for item in case_results)
    human_statuses = [item["human_timing_status"] for item in case_results if item["scenario"] in TIMED_SCENARIOS]
    human_gate = "fail" if "fail" in human_statuses else ("unknown" if "unknown" in human_statuses else "pass")
    references = evidence_identity()
    machine_status = "pass" if machine_passed == len(case_results) else "fail"
    candidate_install_exercised = all(item["checks"]["candidate_install_exercised"] for item in case_results if item["scenario"] == "install")
    candidate_upgrade_exercised = all(item["checks"]["candidate_upgrade_and_rollback_exercised"] for item in case_results if item["scenario"] == "upgrade")
    if machine_status == "fail" or human_gate == "fail":
        overall = "fail"
    elif human_gate == "unknown" or not candidate_install_exercised or not candidate_upgrade_exercised or not references["c2"]["exists"] or not references["c3"]["exists"] or not references["c4"]["exists"] or not references["c5"]["exists"] or not references["c6"]["exists"]:
        overall = "unknown/stop"
    else:
        overall = "pass"
    summary = {
        "schema": SCHEMA,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": now(),
        "classification": "acceptance/evaluation",
        "candidate": {"name": "Codex Harness", "version": "codex-cli 0.139.0", "manifest": str(MANIFEST), "entrypoint": args.codex},
        "runner": {"version": RUNNER_VERSION, "path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).resolve())},
        "fixture": {"path": str(OPERATIONS), "sha256": digest(OPERATIONS)},
        "threshold": {"human_minutes": THRESHOLDS_MINUTES, "maintained_services_max": MAX_MAINTAINED_SERVICES, "extra_expert_required": False, "human_timing_required_for_signoff": True, "machine_elapsed_is_not_human_time": True, "repeats_per_scenario": REPEATS, "scenarios": list(SCENARIOS), "total_cases": len(case_results)},
        "status": overall,
        "machine_contract": {"status": machine_status, "cases_passed": machine_passed, "cases_total": len(case_results)},
        "human_timing": {"status": human_gate, "measured_scenarios": sorted(human_timings), "unknown_case_count": sum(status == "unknown" for status in human_statuses)},
        "candidate_action_boundary": {"install_exercised": candidate_install_exercised, "upgrade_and_rollback_exercised": candidate_upgrade_exercised, "reason": "Global installation and real upgrade are deliberately not mutated by this isolated audit."},
        "license_and_exit": {"primary_sources": str(PRIMARY_SOURCES), "primary_sources_present": PRIMARY_SOURCES.is_file(), "commercial_boundary": "unknown", "redistribution_notice_review": "unknown", "exit_export_delete_cases": sum(item["scenario"] == "exit" and item["status"] == "pass" for item in case_results)},
        "c2_c6_evidence_identity": references,
        "checks": {"all_machine_cases_pass": machine_status == "pass", "all_required_events_complete": all(item["checks"]["required_event_types_complete"] and item["checks"]["required_event_fields_complete"] for item in case_results), "all_cases_isolated": all(item["checks"]["workspace_isolated"] for item in case_results), "no_network_or_real_data": all(item["checks"]["network_calls_zero"] and item["checks"]["real_credentials_false"] and item["checks"]["production_data_false"] for item in case_results), "maintained_services_at_most_three": all(item["checks"]["service_count_within_threshold"] for item in case_results), "license_source_recorded": all(item["checks"]["license_declared_and_source_recorded"] for item in case_results), "human_time_gate": human_gate, "candidate_install_not_overclaimed": not candidate_install_exercised, "candidate_upgrade_not_overclaimed": not candidate_upgrade_exercised, "exit_cases_machine_pass": all(item["status"] == "pass" for item in case_results if item["scenario"] == "exit"), "missing_evidence_stops": True},
        "cases": case_results,
        "interpretation": "Machine C7 audit evidence does not substitute for a real single-operator stopwatch, real candidate installation/upgrade/rollback, or legal review. Unknown remains unknown.",
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps({"run_id": run_id, "summary": str(output_dir / "summary.json"), "mode": "c7", "status": overall, "cases": f"{machine_passed}/{len(case_results)}"}, ensure_ascii=False, indent=2))
    if overall not in {"pass"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
