#!/usr/bin/env python3
"""Run the W6-0.1 C3 schedule/idempotency acceptance evaluation.

The external deterministic trigger is intentional: it tests the shared
schedule/idempotency contract without claiming that a candidate Harness has
an adequate native scheduler.  Candidate C3 evidence remains unknown until a
candidate-specific fixed-source adapter is available.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, REPO_ROOT, RUNS, digest, execute


C3_VERSION = "w6-c3-runner/v1"
STATE_MACHINE = FIXTURE / "c3-idempotency.py"
SINK = FIXTURE / "fake-sink.py"
SCENARIOS = {
    "first_trigger": [("trigger", "first", None)],
    "same_key_duplicate": [("trigger", "first", None), ("trigger", "duplicate", None)],
    "delayed_trigger": [("trigger", "first", None), ("trigger", "delayed", None)],
    "interrupted_retry": [
        ("trigger", "interrupted", "process_interrupt"),
        ("resume", "resume-after-interrupt", None),
        ("trigger", "duplicate-after-resume", None),
    ],
    "missed_trigger": [("trigger", "missed", None)],
}
REPEATS = 3


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def start_sink(case_dir: Path):
    output = case_dir / "fake-sink.jsonl"
    ready = case_dir / "fake-sink.ready.json"
    process = subprocess.Popen(
        [sys.executable, str(SINK), "--host", "127.0.0.1", "--port", "0", "--output", str(output), "--ready-file", str(ready)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if ready.exists():
            port = json.loads(ready.read_text(encoding="utf-8"))["port"]
            return process, output, f"http://127.0.0.1:{port}/ingest"
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=3)
    raise RuntimeError("fake sink did not become ready")


def stop_sink(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def sink_records(path: Path):
    return read_jsonl(path)


def verify_case(case_dir: Path, scenario: str, invocation_results):
    state = json.loads((case_dir / "state.json").read_text(encoding="utf-8")) if (case_dir / "state.json").exists() else {}
    events = read_jsonl(case_dir / "events.jsonl")
    schedule = read_jsonl(case_dir / "schedule.jsonl")
    attempts = read_jsonl(case_dir / "attempts.jsonl")
    faults = read_jsonl(case_dir / "faults.jsonl")
    effects = read_jsonl(case_dir / "effects.jsonl")
    results = read_jsonl(case_dir / "results.jsonl")
    sink = sink_records(case_dir / "fake-sink.jsonl")
    key_values = {item.get("idempotency_key") for item in schedule + attempts + sink + effects + results if item.get("idempotency_key")}
    terminal_attempts = [item for item in attempts if item.get("phase") == "terminal"]
    started_attempts = [item for item in attempts if item.get("phase") == "started"]
    duplicate_events = [item for item in events if item.get("type") == "idempotency.duplicate"]
    reconcile_events = [item for item in events if item.get("type") == "side_effect.reconciled"]
    expected_invocations = len(SCENARIOS[scenario])
    expected_faults = 1 if scenario == "interrupted_retry" else 0
    expected_initial = -15 if scenario == "interrupted_retry" else 0
    returncodes_ok = invocation_results[0]["returncode"] == expected_initial and all(item["returncode"] == 0 for item in invocation_results[1:])
    attempt_history_ok = len(started_attempts) == expected_invocations and len(terminal_attempts) == expected_invocations
    duplicate_ok = len(duplicate_events) == expected_invocations - 1
    if scenario == "interrupted_retry":
        duplicate_ok = len(duplicate_events) == 1
    sink_ok = len(sink) == 1 and all(item.get("idempotency_key") == "daily-summary-v1:2026-08-30T00:00:00Z" for item in sink)
    effect_ok = len(effects) == 1 and len(results) == 1 and state.get("sink_delivery_count") == 1
    state_ok = all(state.get(key) for key in ("schedule_id", "idempotency_key", "result_version", "status", "effect_status")) and state.get("status") == "completed"
    key_ok = key_values == {"daily-summary-v1:2026-08-30T00:00:00Z"}
    fault_ok = len(faults) == expected_faults
    missed_ok = scenario != "missed_trigger" or any(item.get("missed") is True and item.get("delivery_semantics") == "run-once-late" for item in schedule)
    reconcile_ok = scenario != "interrupted_retry" or len(reconcile_events) == 1
    passed = all([returncodes_ok, attempt_history_ok, duplicate_ok, sink_ok, effect_ok, state_ok, key_ok, fault_ok, missed_ok, reconcile_ok])
    return {
        "scenario": scenario,
        "status": "pass" if passed else "fail",
        "expected": {
            "invocations": expected_invocations,
            "initial_returncode": expected_initial,
            "effective_side_effects": 1,
            "result_records": 1,
            "fault_records": expected_faults,
        },
        "observed": {
            "invocations": len(invocation_results),
            "returncodes": [item["returncode"] for item in invocation_results],
            "schedule_records": len(schedule),
            "attempt_started": len(started_attempts),
            "attempt_terminal": len(terminal_attempts),
            "idempotency_keys": sorted(key_values),
            "duplicate_events": len(duplicate_events),
            "reconcile_events": len(reconcile_events),
            "sink_deliveries": len(sink),
            "effect_records": len(effects),
            "result_records": len(results),
            "final_status": state.get("status"),
            "final_effect_status": state.get("effect_status"),
            "fault_records": len(faults),
        },
        "checks": {
            "trigger_returncodes": returncodes_ok,
            "attempt_history_complete": attempt_history_ok,
            "duplicate_trigger_deduplicated": duplicate_ok,
            "one_sink_delivery": sink_ok,
            "one_effect_and_one_result": effect_ok,
            "durable_state_completed": state_ok,
            "one_idempotency_key": key_ok,
            "fault_recording": fault_ok,
            "missed_trigger_semantics": missed_ok,
            "interrupted_run_reconciled": reconcile_ok,
        },
        "evidence_dir": str(case_dir),
    }


def run_case(output_dir: Path, scenario: str, repeat: int):
    case_dir = output_dir / "cases" / scenario / f"repeat-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=False)
    process, sink_output, sink_url = start_sink(case_dir)
    run_id = f"w6-c3-{scenario}-{repeat:02d}"
    write_json(
        case_dir / "case-manifest.json",
        {
            "schema": "zworkbench-w6-c3-case/v1",
            "run_id": run_id,
            "scenario": scenario,
            "repeat": repeat,
            "fixture_version": "W6-0.1",
            "schedule_id": "daily-summary-v1",
            "logical_trigger_time": "2026-08-30T00:00:00Z",
            "idempotency_key": "daily-summary-v1:2026-08-30T00:00:00Z",
            "trigger_sequence": SCENARIOS[scenario],
            "scheduler_mode": "external-deterministic-trigger",
        },
    )
    base = [
        sys.executable,
        str(STATE_MACHINE),
        "--run-dir",
        str(case_dir),
        "--run-id",
        run_id,
        "--sink-url",
        sink_url,
        "--sink-output",
        str(sink_output),
    ]
    invocation_results = []
    try:
        for index, (mode, trigger_kind, fault) in enumerate(SCENARIOS[scenario], start=1):
            command = base + ["--mode", mode]
            if mode == "trigger":
                command.extend(["--trigger-kind", trigger_kind])
            if fault:
                command.extend(["--fault", fault])
            result = execute(command, cwd=REPO_ROOT, timeout=20, output_limit=12000)
            invocation_results.append(result)
            write_json(case_dir / f"invocation-{index:02d}-result.json", result)
    finally:
        stop_sink(process)
    result = verify_case(case_dir, scenario, invocation_results)
    result["case_id"] = f"{scenario}-repeat-{repeat:02d}"
    return result


def candidate_unknowns():
    return {
        name: {
            "status": "unknown",
            "source_ref": ref,
            "tested_scenarios": [],
            "reason": "no candidate-specific fixed-source C3 adapter; measured scheduler is an external composition fixture",
        }
        for name, ref in CANDIDATE_REFS.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats != REPEATS:
        raise SystemExit(f"W6-0.1 C3 requires exactly {REPEATS} repeats per scenario")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-c3-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    case_results = []
    for scenario in SCENARIOS:
        for repeat in range(1, args.repeats + 1):
            case_results.append(run_case(output_dir, scenario, repeat))
    passed_cases = sum(item["status"] == "pass" for item in case_results)
    checks = {
        "all_cases_pass": passed_cases == len(case_results),
        "each_scenario_repeated_three_times": all(sum(item["scenario"] == scenario for item in case_results) == REPEATS for scenario in SCENARIOS),
        "one_effect_per_key": all(item["checks"]["one_effect_and_one_result"] and item["checks"]["one_sink_delivery"] for item in case_results),
        "all_attempts_recorded": all(item["checks"]["attempt_history_complete"] for item in case_results),
        "interrupted_case_reconciled": all(item["checks"]["interrupted_run_reconciled"] for item in case_results),
        "missed_trigger_recorded": all(item["checks"]["missed_trigger_semantics"] for item in case_results),
    }
    summary = {
        "schema": "zworkbench-w6-c3/v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "classification": "acceptance/evaluation",
        "fixture": {
            "manifest": json.loads(MANIFEST.read_text(encoding="utf-8")),
            "manifest_sha256": digest(MANIFEST),
            "source_sha256": digest(FIXTURE),
            "state_machine": str(STATE_MACHINE),
            "state_machine_sha256": digest(STATE_MACHINE),
        },
        "threshold": {
            "scenario_types": list(SCENARIOS),
            "repeats_per_scenario": REPEATS,
            "total_cases": len(case_results),
            "same_key_effective_side_effects": 1,
            "duplicate_or_retry_extra_effects": 0,
            "attempt_record_completeness": 1.0,
            "scheduler": "external deterministic trigger; native candidate scheduler not measured",
        },
        "fixture_contract": {
            "status": "pass-with-composition" if all(checks.values()) else "fail",
            "cases_passed": passed_cases,
            "cases_total": len(case_results),
            "checks": checks,
            "case_results": case_results,
        },
        "candidate_baseline": candidate_unknowns(),
        "interpretation": {
            "external_scheduler_is_composition": True,
            "fixture_contract_is_not_candidate_pass": True,
            "candidate_c3_requires_fixed_source_adapter": True,
            "missing_candidate_evidence_remains_unknown": True,
            "no_real_provider_or_external_message": True,
        },
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "summary": str(summary_path),
                "fixture_contract": summary["fixture_contract"]["status"],
                "cases": f"{passed_cases}/{len(case_results)} pass",
                "candidate_statuses": {name: data["status"] for name, data in summary["candidate_baseline"].items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if summary["fixture_contract"]["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
