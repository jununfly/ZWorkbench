#!/usr/bin/env python3
"""Run the W6-0.1 C4 interruption/recovery acceptance evaluation.

The runner executes only the deterministic local C4 state-machine fixture.
It deliberately does not claim candidate support: a candidate needs a
candidate-specific, fixed-source adapter before its C4 status can move from
unknown to measured evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, REPO_ROOT, RUNS, digest, execute


C4_VERSION = "w6-c4-runner/v1"
STATE_MACHINE = FIXTURE / "c4-state-machine.py"
FAULTS = (
    "before_tool",
    "after_tool_before_commit",
    "committed_before_next_step",
    "provider_timeout",
    "tool_timeout",
    "process_interrupt",
)
TOOL_CLASSES = ("read-only", "idempotent", "approval-required")
REPEATS = 3
INJECTED_EXIT = 75


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expected_initial_returncode(fault):
    if fault in {"before_tool", "after_tool_before_commit", "committed_before_next_step"}:
        return INJECTED_EXIT
    if fault == "process_interrupt":
        return -15
    return 0


def expected_outcome(fault, tool_class):
    if fault == "tool_timeout" and tool_class == "approval-required":
        return "safe_stopped"
    return "completed"


def verify_case(case_dir: Path, fault: str, tool_class: str, initial, resume):
    state_path = case_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    events = read_jsonl(case_dir / "events.jsonl")
    transitions = read_jsonl(case_dir / "transitions.jsonl")
    faults = read_jsonl(case_dir / "faults.jsonl")
    attempts = read_jsonl(case_dir / "attempts.jsonl")
    tool_attempts = [item for item in events if item.get("type") == "tool.attempt"]
    effect_applied = [item for item in events if item.get("type") == "side_effect.applied"]
    effect_records = read_jsonl(case_dir / "effects.jsonl")
    result_records = read_jsonl(case_dir / "tool-results.jsonl")
    retries = [item for item in events if item.get("type") == "retry.decided"]
    transition_pairs = [(item.get("from_phase"), item.get("to_phase")) for item in transitions]
    allowed_pairs = {
        ("ready", "provider_succeeded"),
        ("provider_succeeded", "tool_started"),
        ("tool_started", "committed"),
        ("committed", "completed"),
        ("tool_started", "safe_stopped"),
    }
    expected_initial = expected_initial_returncode(fault)
    initial_ok = initial.get("returncode") == expected_initial
    resume_ok = resume.get("returncode") == 0
    expected_status = expected_outcome(fault, tool_class)
    status_ok = state.get("status") == expected_status
    fault_ok = len(faults) == 1
    transition_ok = all(pair in allowed_pairs for pair in transition_pairs)
    state_complete = all(key in state for key in ("run_id", "phase", "status", "provider_attempts", "tool_attempts", "retry_count", "last_checkpoint"))
    max_retries_ok = state.get("retry_count", 99) <= 1
    unique_operation_ids = {item.get("operation_id") for item in effect_records}
    effect_ledger_ok = len(effect_records) == len(unique_operation_ids)
    unsafe_duplicate_count = max(0, len(effect_applied) - 1) if tool_class == "approval-required" else 0
    no_unsafe_duplicate = unsafe_duplicate_count == 0
    if tool_class == "read-only":
        effect_class_ok = len(effect_records) == 0 and len(effect_applied) == 0
    else:
        effect_class_ok = len(effect_records) == 1 and len(effect_applied) == 1
    if fault == "provider_timeout":
        retry_semantics_ok = state.get("provider_attempts") == 2 and len(retries) == 1
    elif fault == "tool_timeout" and tool_class != "approval-required":
        retry_semantics_ok = state.get("tool_attempts") == 2 and len(retries) == 1
    elif fault == "tool_timeout":
        retry_semantics_ok = state.get("tool_attempts") == 1 and len(retries) == 0 and state.get("phase") == "safe_stopped"
    else:
        retry_semantics_ok = True
    reconcile_ok = True
    if fault in {"after_tool_before_commit", "process_interrupt"}:
        # A read-only process interrupt has no effect record to reconcile; it
        # must instead record the bounded replay-safe retry.  Idempotent and
        # approval-required tools must reconcile their durable effect ledger.
        reconcile_ok = any(item.get("type") == "tool.reconciled" for item in events) or (
            tool_class == "read-only"
            and any(item.get("type") == "retry.decided" and item.get("scope") == "tool" for item in events)
        )
    passed = all(
        [
            initial_ok,
            resume_ok,
            status_ok,
            fault_ok,
            transition_ok,
            state_complete,
            max_retries_ok,
            effect_ledger_ok,
            no_unsafe_duplicate,
            effect_class_ok,
            retry_semantics_ok,
            reconcile_ok,
        ]
    )
    return {
        "case_id": case_dir.name,
        "fault": fault,
        "tool_class": tool_class,
        "status": "pass" if passed else "fail",
        "expected": {
            "initial_returncode": expected_initial,
            "final_status": expected_status,
            "max_retries": 1,
        },
        "observed": {
            "initial_returncode": initial.get("returncode"),
            "resume_returncode": resume.get("returncode"),
            "final_phase": state.get("phase"),
            "final_status": state.get("status"),
            "provider_attempts": state.get("provider_attempts"),
            "tool_attempts": state.get("tool_attempts"),
            "retry_count": state.get("retry_count"),
            "transition_pairs": transition_pairs,
            "event_count": len(events),
            "attempt_history_count": len(attempts),
            "fault_records": len(faults),
            "tool_result_records": len(result_records),
            "effect_records": len(effect_records),
            "physical_effects_applied": len(effect_applied),
            "unsafe_duplicate_count": unsafe_duplicate_count,
        },
        "checks": {
            "initial_fault_contract": initial_ok,
            "resume_contract": resume_ok,
            "state_not_lost": state_complete,
            "state_transition_order": transition_ok,
            "fault_recording": fault_ok,
            "retry_bounded": max_retries_ok,
            "retry_semantics": retry_semantics_ok,
            "effect_ledger_deduplicated": effect_ledger_ok,
            "side_effect_class_contract": effect_class_ok,
            "unsafe_side_effect_duplicate_free": no_unsafe_duplicate,
            "durable_reconciliation": reconcile_ok,
        },
        "evidence_dir": str(case_dir),
    }


def run_case(output_dir: Path, fault: str, tool_class: str, repeat: int):
    case_id = f"{fault}-{tool_class.replace('-', '_')}-repeat-{repeat:02d}"
    case_dir = output_dir / "cases" / fault / tool_class / f"repeat-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=False)
    run_id = f"w6-c4-{fault}-{tool_class}-{repeat:02d}"
    write_json(
        case_dir / "case-manifest.json",
        {
            "schema": "zworkbench-w6-c4-case/v1",
            "run_id": run_id,
            "fault": fault,
            "tool_class": tool_class,
            "repeat": repeat,
            "fixture_version": "W6-0.1",
            "approval_granted": tool_class == "approval-required",
        },
    )
    base = [
        sys.executable,
        str(STATE_MACHINE),
        "--run-dir",
        str(case_dir),
        "--run-id",
        run_id,
        "--tool-class",
        tool_class,
        "--fault",
        fault,
    ]
    initial = execute(base + ["--mode", "initial"], cwd=REPO_ROOT, timeout=20, output_limit=12000)
    write_json(case_dir / "initial-result.json", initial)
    resume = execute(base + ["--mode", "resume"], cwd=REPO_ROOT, timeout=20, output_limit=12000)
    write_json(case_dir / "resume-result.json", resume)
    result = verify_case(case_dir, fault, tool_class, initial, resume)
    result["case_id"] = case_id
    return result


def candidate_unknowns():
    return {
        name: {
            "status": "unknown",
            "source_ref": ref,
            "tested_scenarios": [],
            "reason": "no candidate-specific fixed-source C4 adapter; fixture contract is not candidate evidence",
        }
        for name, ref in CANDIDATE_REFS.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats != REPEATS:
        raise SystemExit(f"W6-0.1 C4 requires exactly {REPEATS} repeats per fault/tool class")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-c4-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    case_results = []
    for fault in FAULTS:
        for tool_class in TOOL_CLASSES:
            for repeat in range(1, args.repeats + 1):
                case_results.append(run_case(output_dir, fault, tool_class, repeat))
    passed_cases = sum(item["status"] == "pass" for item in case_results)
    metrics = {
        "critical_state_loss_count": sum(not item["checks"]["state_not_lost"] for item in case_results),
        "unsafe_side_effect_duplicate_count": sum(item["observed"]["unsafe_duplicate_count"] for item in case_results),
        "unbounded_retry_case_count": sum(not item["checks"]["retry_bounded"] for item in case_results),
        "unexplainable_recovery_case_count": sum(not (item["checks"]["retry_semantics"] and item["checks"]["state_transition_order"]) for item in case_results),
    }
    checks = {
        "all_cases_pass": passed_cases == len(case_results),
        "each_fault_repeated_three_times": all(sum(item["fault"] == fault for item in case_results) == 9 for fault in FAULTS),
        "each_tool_class_covered": all(any(item["tool_class"] == tool_class for item in case_results) for tool_class in TOOL_CLASSES),
        "critical_state_loss_zero": metrics["critical_state_loss_count"] == 0,
        "unsafe_side_effect_duplicates_zero": metrics["unsafe_side_effect_duplicate_count"] == 0,
        "unbounded_retries_zero": metrics["unbounded_retry_case_count"] == 0,
        "recovery_reasons_explainable": metrics["unexplainable_recovery_case_count"] == 0,
    }
    summary = {
        "schema": "zworkbench-w6-c4/v1",
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
            "injection_points": list(FAULTS),
            "repeats_per_injection_point": REPEATS,
            "tool_classes": list(TOOL_CLASSES),
            "total_cases": len(case_results),
            "recovered_or_safe_terminated": "100%",
            "critical_state_loss": 0,
            "unsafe_side_effect_duplicate": 0,
            "max_retry_count": 1,
        },
        "fixture_contract": {
            "status": "pass" if all(checks.values()) else "fail",
            "cases_passed": passed_cases,
            "cases_total": len(case_results),
            "checks": checks,
            "metrics": metrics,
            "case_results": case_results,
        },
        "candidate_baseline": candidate_unknowns(),
        "interpretation": {
            "fixture_contract_is_not_candidate_pass": True,
            "candidate_c4_requires_fixed_source_adapter": True,
            "missing_candidate_evidence_remains_unknown": True,
            "no_real_provider_or_external_side_effect": True,
            "approval_required_timeout_policy": "safe-stop and preserve durable state; no automatic retry",
            "process_interrupt_policy": "resume from checkpoint and reconcile effect ledger before any replay",
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
    if summary["fixture_contract"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
