#!/usr/bin/env python3
"""Run the W6-0.1 C7 lifecycle and operability acceptance evaluation.

The runner executes only a deterministic local fixture in fresh case
directories.  It records machine wall-clock time and operator steps separately.
Without a human-timing input file, the operational time gates remain
``unknown`` by design; the runner never converts subprocess duration into a
human estimate.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, REPO_ROOT, RUNS, digest, execute


C7_VERSION = "w6-c7-runner/v1"
OPERATIONS = FIXTURE / "c7-operations.py"
SCENARIOS = ("install", "upgrade", "backup_restore", "fault_diagnosis")
REPEATS = 3
THRESHOLDS_MINUTES = {
    "install": 90,
    "upgrade": 30,
    "backup_restore": 30,
    "fault_diagnosis": 30,
}
REQUIRED_EVENT_TYPES = (
    "operation.started",
    "environment.checked",
    "precondition.prepared",
    "operation.step",
    "verification.completed",
    "operation.completed",
)
MAX_MAINTAINED_SERVICES = 3


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_human_timings(path: Path | None):
    if path is None:
        return {}
    values = read_json(path)
    if not isinstance(values, dict):
        raise SystemExit("--human-timings-json must contain an object keyed by scenario")
    timings = {}
    for scenario, value in values.items():
        if scenario not in SCENARIOS:
            raise SystemExit(f"unknown human timing scenario: {scenario}")
        if isinstance(value, dict):
            value = value.get("minutes")
        if value is None:
            continue
        if not isinstance(value, (int, float)) or value < 0:
            raise SystemExit(f"human timing for {scenario} must be a non-negative number of minutes")
        timings[scenario] = float(value)
    return timings


def candidate_unknowns():
    return {
        name: {
            "status": "unknown",
            "source_ref": ref,
            "tested_scenarios": [],
            "reason": "no candidate-specific fixed-source C7 runbook and human operator timing; fixture contract is not candidate evidence",
        }
        for name, ref in CANDIDATE_REFS.items()
    }


def verify_case(case_dir: Path, scenario: str, process_result, human_timings):
    operation_dir = case_dir / "operation"
    result = read_json(operation_dir / "operation-result.json") if (operation_dir / "operation-result.json").exists() else {}
    services = read_json(operation_dir / "service-manifest.json") if (operation_dir / "service-manifest.json").exists() else {}
    dependencies = read_json(operation_dir / "dependency-manifest.json") if (operation_dir / "dependency-manifest.json").exists() else {}
    events = read_jsonl(operation_dir / "operation-events.jsonl")
    human_minutes = human_timings.get(scenario)
    threshold = THRESHOLDS_MINUTES[scenario]
    operation_checks = result.get("checks", {})
    event_types = {event.get("type") for event in events}
    workspace = Path(result["workspace"]).resolve() if result.get("workspace") else None
    case_root = case_dir.resolve()
    workspace_isolated = bool(workspace and (workspace == case_root or case_root in workspace.parents))
    required_event_fields = all(all(key in event for key in ("event_id", "run_id", "at", "type")) for event in events)
    human_timing_status = "unknown" if human_minutes is None else ("pass" if human_minutes <= threshold else "fail")
    service_count = services.get("maintained_service_count")
    service_count_ok = isinstance(service_count, int) and service_count <= MAX_MAINTAINED_SERVICES and services.get("provider_and_host_os_counted") is False
    process_passed = process_result.get("returncode") == 0 and not process_result.get("timed_out")
    checks = {
        "process_passed": process_passed,
        "scenario_correct": result.get("scenario") == scenario,
        "operation_completed": result.get("status") == "completed",
        "operation_checks_pass": bool(operation_checks) and all(operation_checks.values()),
        "required_event_types_complete": set(REQUIRED_EVENT_TYPES).issubset(event_types),
        "required_event_fields_complete": required_event_fields,
        "workspace_isolated": workspace_isolated,
        "network_calls_zero": result.get("network_calls") == 0,
        "real_credentials_false": result.get("real_credentials") is False,
        "production_data_false": result.get("production_data") is False,
        "service_count_within_threshold": service_count_ok,
        "no_extra_expert_declared": dependencies.get("operator_expert_required") is False,
        "human_time_semantics_explicit": result.get("human_timed") is False and result.get("human_elapsed_minutes") is None and result.get("human_timing_status") == "unknown",
    }
    passed = all(checks.values())
    return {
        "scenario": scenario,
        "repeat": int(case_dir.name.split("-")[-1]),
        "status": "pass" if passed else "fail",
        "human_timing_status": human_timing_status,
        "threshold_minutes": threshold,
        "observed": {
            "process_returncode": process_result.get("returncode"),
            "machine_elapsed_seconds": result.get("machine_elapsed_seconds"),
            "machine_elapsed_source": result.get("machine_elapsed_source"),
            "human_elapsed_minutes": human_minutes,
            "human_timed": human_minutes is not None,
            "human_step_count": result.get("human_step_count"),
            "maintained_service_count": service_count,
            "managed_services": [item.get("name") for item in services.get("managed_services", [])],
            "extra_expert_required": dependencies.get("operator_expert_required"),
            "event_count": len(events),
        },
        "checks": checks,
        "evidence_dir": str(case_dir),
    }


def run_case(output_dir: Path, scenario: str, repeat: int, human_timings):
    case_dir = output_dir / "cases" / scenario / f"repeat-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=False)
    operation_dir = case_dir / "operation"
    workspace = case_dir / "workspace"
    run_id = f"w6-c7-{scenario}-repeat-{repeat:02d}"
    command = [
        sys.executable,
        str(OPERATIONS),
        "--scenario",
        scenario,
        "--workspace",
        str(workspace),
        "--output-dir",
        str(operation_dir),
        "--run-id",
        run_id,
    ]
    process_result = execute(command, cwd=REPO_ROOT, timeout=15, output_limit=12000)
    write_json(case_dir / "process-result.json", process_result)
    return verify_case(case_dir, scenario, process_result, human_timings)


def machine_elapsed_summary(case_results):
    values = [item["observed"]["machine_elapsed_seconds"] for item in case_results if isinstance(item["observed"].get("machine_elapsed_seconds"), (int, float))]
    if not values:
        return {"count": 0, "min_seconds": None, "max_seconds": None, "mean_seconds": None, "p50_seconds": None}
    values = sorted(values)
    return {
        "count": len(values),
        "min_seconds": min(values),
        "max_seconds": max(values),
        "mean_seconds": round(statistics.mean(values), 6),
        "p50_seconds": statistics.median(values),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--human-timings-json", type=Path, help="Optional manually measured minutes keyed by C7 scenario")
    args = parser.parse_args()
    if args.repeats != REPEATS:
        raise SystemExit(f"W6-0.1 C7 requires exactly {REPEATS} repeats per scenario")
    human_timings = load_human_timings(args.human_timings_json)
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-c7-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    human_template = {
        scenario: {
            "minutes": human_timings.get(scenario),
            "status": "measured" if scenario in human_timings else "unknown",
            "threshold_minutes": THRESHOLDS_MINUTES[scenario],
            "note": "Fill with a real single-operator stopwatch measurement; do not use runner machine_elapsed_seconds.",
        }
        for scenario in SCENARIOS
    }
    write_json(output_dir / "human-timing-template.json", human_template)

    case_results = [
        run_case(output_dir, scenario, repeat, human_timings)
        for scenario in SCENARIOS
        for repeat in range(1, REPEATS + 1)
    ]
    passed_cases = sum(item["status"] == "pass" for item in case_results)
    human_statuses = [item["human_timing_status"] for item in case_results]
    if any(status == "fail" for status in human_statuses):
        human_gate_status = "fail"
    elif any(status == "unknown" for status in human_statuses):
        human_gate_status = "unknown"
    else:
        human_gate_status = "pass"
    machine_status = "pass" if passed_cases == len(case_results) else "fail"
    if machine_status == "fail" or human_gate_status == "fail":
        contract_status = "fail"
    elif human_gate_status == "unknown":
        contract_status = "pass-with-unknown-human-timing"
    else:
        contract_status = "pass"
    metrics = {
        "cases_passed": passed_cases,
        "cases_total": len(case_results),
        "machine_process_pass_rate": round(passed_cases / len(case_results), 6),
        "machine_elapsed": machine_elapsed_summary(case_results),
        "human_timed_cases": sum(item["observed"]["human_timed"] for item in case_results),
        "human_timing_unknown_cases": sum(status == "unknown" for status in human_statuses),
        "human_timing_failures": sum(status == "fail" for status in human_statuses),
        "maintained_service_count_max": max((item["observed"]["maintained_service_count"] for item in case_results if isinstance(item["observed"].get("maintained_service_count"), int)), default=None),
        "extra_expert_required_cases": sum(item["observed"]["extra_expert_required"] is True for item in case_results),
    }
    checks = {
        "all_operations_pass": machine_status == "pass",
        "all_required_events_complete": all(item["checks"]["required_event_types_complete"] and item["checks"]["required_event_fields_complete"] for item in case_results),
        "all_cases_isolated": all(item["checks"]["workspace_isolated"] for item in case_results),
        "no_network_or_real_data": all(item["checks"]["network_calls_zero"] and item["checks"]["real_credentials_false"] and item["checks"]["production_data_false"] for item in case_results),
        "maintained_services_at_most_three": metrics["maintained_service_count_max"] is not None and metrics["maintained_service_count_max"] <= MAX_MAINTAINED_SERVICES,
        "no_extra_expert_in_reference_runbook": metrics["extra_expert_required_cases"] == 0,
        "human_time_gate": human_gate_status,
    }
    summary = {
        "schema": "zworkbench-w6-c7/v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "classification": "acceptance/evaluation",
        "fixture": {
            "manifest": read_json(MANIFEST),
            "manifest_sha256": digest(MANIFEST),
            "source_sha256": digest(FIXTURE),
            "operations_fixture": str(OPERATIONS),
            "operations_fixture_sha256": digest(OPERATIONS),
        },
        "runner": {
            "version": C7_VERSION,
            "path": str(Path(__file__).resolve()),
            "sha256": digest(Path(__file__).resolve()),
        },
        "threshold": {
            "human_minutes": THRESHOLDS_MINUTES,
            "maintained_services_max": MAX_MAINTAINED_SERVICES,
            "extra_expert_required": False,
            "human_timing_required_for_signoff": True,
            "machine_elapsed_is_not_human_time": True,
            "required_event_types": list(REQUIRED_EVENT_TYPES),
            "repeats_per_scenario": REPEATS,
            "total_cases": len(case_results),
        },
        "fixture_contract": {
            "status": contract_status,
            "machine_process_status": machine_status,
            "human_timing_status": human_gate_status,
            "cases_passed": passed_cases,
            "cases_total": len(case_results),
            "checks": checks,
            "metrics": metrics,
            "case_results": case_results,
        },
        "candidate_baseline": candidate_unknowns(),
        "interpretation": {
            "fixture_contract_is_not_candidate_pass": True,
            "candidate_c7_requires_fixed_source_runbook_and_real_operator_timing": True,
            "machine_elapsed_is_lower_bound_only": True,
            "missing_human_timing_remains_unknown": True,
            "provider_and_host_os_excluded_from_service_count": True,
            "no_package_install_or_daemon_start": True,
            "no_real_provider_or_external_side_effect": True,
        },
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    print(json.dumps({
        "run_id": run_id,
        "summary": str(summary_path),
        "fixture_contract": contract_status,
        "machine_process": f"{passed_cases}/{len(case_results)} pass",
        "human_timing": human_gate_status,
        "human_timing_unknown_cases": metrics["human_timing_unknown_cases"],
        "candidate_statuses": {name: data["status"] for name, data in summary["candidate_baseline"].items()},
    }, ensure_ascii=False, indent=2))
    if contract_status == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
