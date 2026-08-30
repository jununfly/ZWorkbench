#!/usr/bin/env python3
"""Run the W6-0.1 C6 recorded/simulated/live replay boundary evaluation.

This runner creates a deterministic local recording and invokes the
candidate-independent replay fixture.  It never starts a Provider or executes
the recorded tool call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, REPO_ROOT, RUNS, digest, execute


C6_VERSION = "w6-c6-runner/v1"
REPLAY = FIXTURE / "c6-replay.py"
REPEATS = 5
MODES = ("recorded_view", "simulated_replay", "live_replay")
REQUIRED_EVENT_TYPES = (
    "run.started",
    "environment.snapshot",
    "provider.request",
    "provider.response",
    "tool.call",
    "policy.decision",
    "tool.result",
    "state.transition",
    "diff.created",
    "test.output",
    "run.completed",
)
REQUIRED_EVENT_FIELDS = ("event_id", "run_id", "type", "logical_time", "source")
EXPECTED_SEMANTIC = {"answer": "fixture-ok", "task": "replay-contract-v1"}


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_recording(case_dir: Path, case_id: str):
    recording_dir = case_dir / "recording"
    recording_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"w6-c6-{case_id}"
    environment = {
        "schema": "zworkbench-w6-c6-environment/v1",
        "fixture_version": "W6-0.1",
        "network": "loopback-only",
        "real_credentials": False,
        "production_data": False,
        "python": platform.python_version(),
        "platform": platform.system().lower(),
        "timezone": "UTC",
    }
    provider = {
        "provider_id": "fake-a",
        "model": "fake-model",
        "endpoint": "http://127.0.0.1:11434",
        "protocol": "openai-compatible-chat-completions",
    }
    semantic = dict(EXPECTED_SEMANTIC)
    events = []

    def add(event_type, source, **fields):
        event = {
            "event_id": f"event-{len(events) + 1:03d}",
            "run_id": run_id,
            "type": event_type,
            "logical_time": f"2026-08-30T00:00:{len(events):02d}Z",
            "source": source,
        }
        event.update(fields)
        events.append(event)

    add("run.started", "runner")
    add("environment.snapshot", "runner", environment=environment, environment_sha256=hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest())
    add("provider.request", "fake-provider", provider=provider, request={"model": provider["model"], "prompt": "Return fixture answer."}, request_sha256="request-sha256-fixture")
    add("provider.response", "fake-provider", provider=provider, response={"answer": "fixture-ok"}, semantic_result=semantic, response_sha256="response-sha256-fixture")
    add("tool.call", "harness", tool={"name": "read_fixture", "side_effect_class": "read-only", "arguments": {"path": "README.md"}})
    add("policy.decision", "policy", decision="allow", side_effect_class="read-only", approval_required=False)
    add("tool.result", "harness", tool_name="read_fixture", result={"status": "ok", "bytes": 128}, side_effect_count=0)
    add("state.transition", "harness", from_state="provider_succeeded", to_state="tool_completed")
    add("diff.created", "harness", diff="", modified_files=[])
    add("test.output", "harness", command="python3 -m unittest", returncode=0, output="fixture tests: ok")
    add("run.completed", "runner", status="completed", semantic_result=semantic, side_effect_count=0)

    ledger_path = recording_dir / "event-ledger.jsonl"
    ledger_path.write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events), encoding="utf-8")
    cassette = {
        "schema": "zworkbench-w6-c6-cassette/v1",
        "cassette_id": f"cassette-{case_id}",
        "source_run_id": run_id,
        "provider": provider,
        "interactions": [{
            "request": {"model": provider["model"], "prompt": "Return fixture answer."},
            "response": {"answer": "fixture-ok"},
        }],
        "tool_results": [{"tool_name": "read_fixture", "result": {"status": "ok", "bytes": 128}}],
        "expected_semantic_result": semantic,
        "required_event_types": list(REQUIRED_EVENT_TYPES),
    }
    cassette_path = recording_dir / "replay-cassette.json"
    write_json(cassette_path, cassette)
    write_json(recording_dir / "expected-output.json", {"semantic_result": semantic, "side_effect_count": 0})
    write_json(recording_dir / "environment-manifest.json", environment)
    write_json(case_dir / "effect-guard.json", {
        "provider_requests": 0,
        "tool_invocations": 0,
        "external_side_effects": 0,
        "guard_schema": "w6-c6-effect-guard/v1",
    })
    write_json(case_dir / "run-manifest.json", {
        "schema": "zworkbench-w6-c6-run/v1",
        "run_id": run_id,
        "fixture_version": "W6-0.1",
        "fixture_manifest_sha256": digest(MANIFEST),
        "provider": provider,
        "environment": environment,
        "event_ledger_sha256": file_hash(ledger_path),
        "replay_cassette_sha256": file_hash(cassette_path),
        "required_event_types": list(REQUIRED_EVENT_TYPES),
    })
    return ledger_path, cassette_path, events


def verify_mode(mode_dir: Path, mode: str, process_result, before_guard, after_guard, events, expected):
    result_path = mode_dir / "mode-result.json"
    result = read_json(result_path) if result_path.exists() else {}
    mode_events = read_jsonl(mode_dir / "mode-events.jsonl")
    required_fields_ok = all(all(field in event for field in REQUIRED_EVENT_FIELDS) for event in events)
    required_types_ok = set(event.get("type") for event in events) == set(REQUIRED_EVENT_TYPES)
    mode_label_ok = result.get("replay_mode") == mode and all(item.get("mode") == mode for item in mode_events)
    no_execution = (
        result.get("execution_performed") is False
        and result.get("provider_requests") == 0
        and result.get("tool_invocations") == 0
        and result.get("external_calls") == 0
        and result.get("side_effect_count") == 0
    )
    guard_unchanged = before_guard == after_guard == {
        "provider_requests": 0,
        "tool_invocations": 0,
        "external_side_effects": 0,
        "guard_schema": "w6-c6-effect-guard/v1",
    }
    if mode == "recorded_view":
        semantic_ok = result.get("status") == "viewed" and result.get("view_only") is True and result.get("semantic_result") == expected
        policy_ok = True
    elif mode == "simulated_replay":
        semantic_ok = result.get("status") == "simulated" and result.get("cassette_only") is True and result.get("semantic_result") == expected
        policy_ok = True
    else:
        policy = result.get("policy_decision", {})
        semantic_ok = result.get("status") == "denied" and result.get("safe_denial") is True
        policy_ok = (
            policy.get("approval_required") is True
            and policy.get("approval_granted") is False
            and policy.get("decision") == "deny"
            and bool(policy.get("reason"))
        )
    passed = all([
        process_result.get("returncode") == 0,
        mode_label_ok,
        required_fields_ok,
        required_types_ok,
        no_execution,
        guard_unchanged,
        semantic_ok,
        policy_ok,
    ])
    return {
        "mode": mode,
        "status": "pass" if passed else "fail",
        "observed": {
            "process_returncode": process_result.get("returncode"),
            "result_status": result.get("status"),
            "semantic_result": result.get("semantic_result"),
            "event_count": len(events),
            "mode_event_count": len(mode_events),
            "execution_performed": result.get("execution_performed"),
            "provider_requests": result.get("provider_requests"),
            "tool_invocations": result.get("tool_invocations"),
            "side_effect_count": result.get("side_effect_count"),
            "policy_decision": result.get("policy_decision"),
        },
        "checks": {
            "process_passed": process_result.get("returncode") == 0,
            "mode_label_correct": mode_label_ok,
            "required_event_fields_complete": required_fields_ok,
            "required_event_types_complete": required_types_ok,
            "no_execution": no_execution,
            "effect_guard_unchanged": guard_unchanged,
            "semantic_or_safe_denial": semantic_ok,
            "policy_boundary": policy_ok,
        },
        "evidence_dir": str(mode_dir),
    }


def run_case(output_dir: Path, mode: str, repeat: int):
    case_id = f"{mode}-repeat-{repeat:02d}"
    case_dir = output_dir / "cases" / mode / f"repeat-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=False)
    ledger_path, cassette_path, events = build_recording(case_dir, case_id)
    before_guard = read_json(case_dir / "effect-guard.json")
    mode_dir = case_dir / "mode"
    command = [
        sys.executable,
        str(REPLAY),
        "--mode",
        mode,
        "--effect-guard",
        str(case_dir / "effect-guard.json"),
        "--output-dir",
        str(mode_dir),
    ]
    if mode == "recorded_view":
        command.extend(["--ledger", str(ledger_path)])
    else:
        command.extend(["--cassette", str(cassette_path)])
    process_result = execute(command, cwd=REPO_ROOT, timeout=15, output_limit=12000)
    write_json(case_dir / "process-result.json", process_result)
    after_guard = read_json(case_dir / "effect-guard.json")
    return verify_mode(mode_dir, mode, process_result, before_guard, after_guard, events, EXPECTED_SEMANTIC)


def candidate_unknowns():
    return {
        name: {
            "status": "unknown",
            "source_ref": ref,
            "tested_scenarios": [],
            "reason": "no candidate-specific fixed-source C6 adapter; fixture contract is not candidate evidence",
        }
        for name, ref in CANDIDATE_REFS.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats != REPEATS:
        raise SystemExit(f"W6-0.1 C6 requires exactly {REPEATS} repeats per replay mode")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-c6-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    case_results = []
    for mode in MODES:
        for repeat in range(1, REPEATS + 1):
            case_results.append(run_case(output_dir, mode, repeat))
    passed_cases = sum(item["status"] == "pass" for item in case_results)
    metrics = {
        "recorded_view_passed": sum(item["mode"] == "recorded_view" and item["status"] == "pass" for item in case_results),
        "simulated_replay_passed": sum(item["mode"] == "simulated_replay" and item["status"] == "pass" for item in case_results),
        "live_replay_denied": sum(item["mode"] == "live_replay" and item["checks"].get("policy_boundary") is True for item in case_results),
        "required_event_field_failures": sum(not item["checks"].get("required_event_fields_complete") for item in case_results),
        "mode_label_failures": sum(not item["checks"].get("mode_label_correct") for item in case_results),
        "effect_guard_mutations": sum(not item["checks"].get("effect_guard_unchanged") for item in case_results),
    }
    checks = {
        "all_modes_pass": passed_cases == len(case_results),
        "recorded_view_5_of_5_no_execution": metrics["recorded_view_passed"] == REPEATS,
        "simulated_replay_5_of_5_matches_expected": metrics["simulated_replay_passed"] == REPEATS,
        "live_replay_5_of_5_fail_closed": metrics["live_replay_denied"] == REPEATS,
        "required_event_fields_100_percent": metrics["required_event_field_failures"] == 0,
        "mode_labels_100_percent": metrics["mode_label_failures"] == 0,
        "live_and_simulated_side_effects_zero": metrics["effect_guard_mutations"] == 0,
    }
    summary = {
        "schema": "zworkbench-w6-c6/v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "classification": "acceptance/evaluation",
        "fixture": {
            "manifest": read_json(MANIFEST),
            "manifest_sha256": digest(MANIFEST),
            "source_sha256": digest(FIXTURE),
            "replay_fixture": str(REPLAY),
            "replay_fixture_sha256": digest(REPLAY),
        },
        "runner": {
            "version": C6_VERSION,
            "path": str(Path(__file__).resolve()),
            "sha256": digest(Path(__file__).resolve()),
        },
        "threshold": {
            "modes": list(MODES),
            "repeats_per_mode": REPEATS,
            "total_cases": len(case_results),
            "required_event_types": list(REQUIRED_EVENT_TYPES),
            "required_event_fields": list(REQUIRED_EVENT_FIELDS),
            "required_event_field_completeness": "100%",
            "mode_label_correctness": "100%",
            "simulated_replay_expected_match": "5/5",
            "live_replay_side_effects": 0,
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
            "candidate_c6_requires_fixed_source_adapter": True,
            "missing_candidate_evidence_remains_unknown": True,
            "recorded_view_policy": "read-only projection; never re-execute",
            "simulated_replay_policy": "cassette-only; no Provider/tool/network access",
            "live_replay_policy": "default deny without explicit approval; this run never grants approval",
            "no_real_provider_or_external_side_effect": True,
        },
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    print(json.dumps({
        "run_id": run_id,
        "summary": str(summary_path),
        "fixture_contract": summary["fixture_contract"]["status"],
        "cases": f"{passed_cases}/{len(case_results)} pass",
        "candidate_statuses": {name: data["status"] for name, data in summary["candidate_baseline"].items()},
    }, ensure_ascii=False, indent=2))
    if summary["fixture_contract"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
