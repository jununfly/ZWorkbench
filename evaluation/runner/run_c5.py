#!/usr/bin/env python3
"""Run the W6-0.1 C5 dual-Provider failover acceptance evaluation.

The runner starts only loopback fake Providers and invokes the independent C5
router.  Candidate Harnesses are deliberately left ``unknown`` until a
candidate-specific adapter is bound to a fixed source/version.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, REPO_ROOT, RUNS, digest, execute, start_fake_provider, stop_fake_provider


C5_VERSION = "w6-c5-runner/v1"
ROUTER = FIXTURE / "c5-provider-router.py"
MODEL = "fake-model"
NORMAL_REPEATS = 5
FAULT_REPEATS = 3
PROVIDERS = {
    "fake-a": FIXTURE / "fake-provider-a.json",
    "fake-b": FIXTURE / "fake-provider-b.json",
}
CASE_SPECS = (
    {"case_type": "normal-a", "primary": "fake-a", "fault": None, "repeats": NORMAL_REPEATS},
    {"case_type": "normal-b", "primary": "fake-b", "fault": None, "repeats": NORMAL_REPEATS},
    {"case_type": "timeout-once", "primary": "fake-b", "fault": "timeout_once", "repeats": FAULT_REPEATS},
    {"case_type": "stream-interrupt-once", "primary": "fake-b", "fault": "stream_interrupt_once", "repeats": FAULT_REPEATS},
    {
        "case_type": "structured-output-unsupported",
        "primary": "fake-b",
        "fault": "structured_output_unsupported",
        "repeats": FAULT_REPEATS,
        "requires_structured_output": True,
    },
)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def expected_semantic(spec):
    if spec.get("requires_structured_output"):
        return {"answer": "fixture-ok", "task": "provider-failover-v1", "schema_version": "v1"}
    return {"answer": "fixture-ok"}


def case_id(spec, repeat):
    return f"{spec['case_type']}-repeat-{repeat:02d}"


def expected_fallback(spec):
    return spec["primary"] == "fake-b" and (spec.get("fault") or spec.get("requires_structured_output"))


def verify_case(case_dir: Path, spec, process_result, provider_servers):
    result_path = case_dir / "result.json"
    result = read_json(result_path) if result_path.exists() else {}
    attempts = result.get("attempt_history", [])
    capability_detection = result.get("capability_detection", [])
    fallback = result.get("fallback_ledger", [])
    degradation = result.get("degradation_ledger", [])
    events = read_jsonl(case_dir / "provider-events.jsonl")
    attempts_file = read_jsonl(case_dir / "attempt-history.jsonl")
    capabilities_file = read_jsonl(case_dir / "capability-detection.jsonl")
    request_logs = {
        provider_id: read_jsonl(server["request_path"])
        for provider_id, server in provider_servers.items()
    }
    expected = expected_semantic(spec)
    expected_fallback_count = 1 if expected_fallback(spec) else 0
    final = result.get("final", {})
    observed_attempt_providers = [item.get("provider_id") for item in attempts]
    required_metadata = all(
        item.get("provider_id") and item.get("model") and item.get("endpoint")
        for item in attempts
    )
    all_local_endpoints = all(
        str(item.get("endpoint", "")).startswith("http://127.0.0.1:")
        for item in attempts + capability_detection
    )
    capability_ids = {item.get("provider_id") for item in capability_detection}
    expected_capability_ids = {spec["primary"]} | ({"fake-a"} if expected_fallback(spec) else set())
    fallback_reason = fallback[0].get("reason") if fallback else None
    reason_ok = (
        (not expected_fallback(spec) and not fallback and not degradation)
        or (
            expected_fallback(spec)
            and len(fallback) == 1
            and fallback[0].get("from_provider") == "fake-b"
            and fallback[0].get("to_provider") == "fake-a"
            and bool(fallback_reason)
        )
    )
    if spec.get("fault") == "timeout_once":
        failure_reason_ok = any(item.get("reason") == "timeout" for item in attempts if item.get("status") == "failed")
        injected_fault_seen = any(item.get("fault_injected") is True for item in request_logs["fake-b"] if item.get("path") == "/v1/chat/completions")
    elif spec.get("fault") == "stream_interrupt_once":
        failure_reason_ok = any(item.get("reason") == "stream_interrupt" for item in attempts if item.get("status") == "failed")
        injected_fault_seen = any(item.get("fault_injected") is True for item in request_logs["fake-b"] if item.get("path") == "/v1/chat/completions")
    elif spec.get("fault") == "structured_output_unsupported":
        failure_reason_ok = fallback_reason == "capability_missing:structured_output"
        injected_fault_seen = any(
            item.get("kind") == "capability_probe" and "structured_output" not in item.get("capabilities", [])
            for item in request_logs["fake-b"]
        )
    else:
        failure_reason_ok = True
        injected_fault_seen = True
    primary_attempt_ok = (
        expected_fallback(spec)
        and spec.get("fault") == "structured_output_unsupported"
        and observed_attempt_providers == ["fake-a"]
    ) or (
        not expected_fallback(spec) and observed_attempt_providers == [spec["primary"]]
    ) or (
        expected_fallback(spec)
        and spec.get("fault") != "structured_output_unsupported"
        and observed_attempt_providers == ["fake-b", "fake-a"]
    )
    final_provider_ok = final.get("provider") == ("fake-a" if expected_fallback(spec) else spec["primary"])
    passed = all([
        process_result.get("returncode") == 0,
        result.get("status") == "completed",
        final_provider_ok,
        final.get("semantic_result") == expected,
        final.get("silent_semantic_change") is False,
        required_metadata,
        all_local_endpoints,
        capability_ids == expected_capability_ids,
        len(capabilities_file) == len(capability_detection),
        len(attempts_file) == len(attempts),
        len(events) >= len(attempts) * 2,
        len(fallback) == expected_fallback_count,
        reason_ok,
        failure_reason_ok,
        injected_fault_seen,
        primary_attempt_ok,
        all(server["process"].poll() is not None for server in provider_servers.values()),
    ])
    return {
        "case_id": case_dir.name,
        "case_type": spec["case_type"],
        "repeat": spec["repeat"],
        "status": "pass" if passed else "fail",
        "expected": {
            "primary_provider": spec["primary"],
            "final_provider": "fake-a" if expected_fallback(spec) else spec["primary"],
            "semantic_result": expected,
            "fallback_count": expected_fallback_count,
        },
        "observed": {
            "process_returncode": process_result.get("returncode"),
            "status": result.get("status"),
            "attempt_providers": observed_attempt_providers,
            "capability_providers": sorted(capability_ids),
            "final_provider": final.get("provider"),
            "final_semantic_result": final.get("semantic_result"),
            "fallback_count": len(fallback),
            "fallback_reason": fallback_reason,
            "request_log_counts": {provider: len(items) for provider, items in request_logs.items()},
        },
        "checks": {
            "router_process_passed": process_result.get("returncode") == 0,
            "completed": result.get("status") == "completed",
            "provider_identity_and_final_target": final_provider_ok,
            "semantic_result_matches_expected": final.get("semantic_result") == expected,
            "silent_semantic_change_zero": final.get("silent_semantic_change") is False,
            "provider_model_endpoint_recorded": required_metadata,
            "loopback_only": all_local_endpoints and result.get("local_only") is True,
            "capability_detection_recorded": capability_ids == expected_capability_ids,
            "fallback_reason_and_target_recorded": reason_ok,
            "injected_fault_observed": injected_fault_seen,
            "failure_reason_explained": failure_reason_ok,
            "attempt_order": primary_attempt_ok,
            "provider_processes_stopped": all(server["process"].poll() is not None for server in provider_servers.values()),
        },
        "evidence_dir": str(case_dir),
    }


def run_case(output_dir: Path, spec, repeat: int):
    spec = {**spec, "repeat": repeat}
    case_dir = output_dir / "cases" / spec["case_type"] / f"repeat-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=False)
    provider_root = case_dir / "provider-runtime"
    provider_root.mkdir()
    task = {
        "schema": "zworkbench-w6-c5-task/v1",
        "task_id": "provider-failover-v1",
        "prompt": "Return the deterministic W6 C5 fixture answer.",
        "requires_structured_output": bool(spec.get("requires_structured_output", False)),
        "expected_semantic_result": expected_semantic(spec),
    }
    write_json(case_dir / "task.json", task)
    write_json(case_dir / "case-manifest.json", {
        "schema": "zworkbench-w6-c5-case-manifest/v1",
        "case_id": case_id(spec, repeat),
        "case_type": spec["case_type"],
        "repeat": repeat,
        "primary_provider": spec["primary"],
        "fallback_provider": "fake-a" if spec["primary"] == "fake-b" else None,
        "fault": spec.get("fault"),
        "fault_scope": "fake-b only" if spec.get("fault") else "none",
        "fixture_version": "W6-0.1",
        "real_credentials": False,
        "network": "loopback-only",
    })
    servers = {}
    process_result = None
    try:
        for provider_id in ("fake-a", "fake-b"):
            server, startup_error = start_fake_provider(
                provider_root,
                provider_id,
                "plain",
                port=0,
                fault=spec.get("fault") if provider_id == "fake-b" else None,
            )
            if startup_error:
                write_json(case_dir / "startup-error.json", startup_error)
                result = {"status": "fail", "case_id": case_dir.name, "case_type": spec["case_type"], "repeat": repeat, "checks": {"provider_startup": False}, "evidence_dir": str(case_dir)}
                return result
            servers[provider_id] = server
        command = [
            sys.executable,
            str(ROUTER),
            "--task",
            str(case_dir / "task.json"),
            "--primary-id",
            spec["primary"],
            "--primary-url",
            servers[spec["primary"]]["base_url"],
            "--model",
            MODEL,
            "--output-dir",
            str(case_dir),
        ]
        if expected_fallback(spec):
            command.extend([
                "--fallback-id",
                "fake-a",
                "--fallback-url",
                servers["fake-a"]["base_url"],
            ])
        process_result = execute(command, cwd=REPO_ROOT, timeout=15, output_limit=12000)
        write_json(case_dir / "router-process-result.json", process_result)
    finally:
        for server in reversed(list(servers.values())):
            stop_fake_provider(server)
    return verify_case(case_dir, spec, process_result or {"returncode": None}, servers)


def candidate_unknowns():
    return {
        name: {
            "status": "unknown",
            "source_ref": ref,
            "tested_scenarios": [],
            "reason": "no candidate-specific fixed-source C5 adapter; fixture contract is not candidate evidence",
        }
        for name, ref in CANDIDATE_REFS.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--normal-repeats", type=int, default=NORMAL_REPEATS)
    parser.add_argument("--fault-repeats", type=int, default=FAULT_REPEATS)
    args = parser.parse_args()
    if args.normal_repeats != NORMAL_REPEATS or args.fault_repeats != FAULT_REPEATS:
        raise SystemExit(f"W6-0.1 C5 requires normal repeats={NORMAL_REPEATS} and fault repeats={FAULT_REPEATS}")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-c5-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    case_results = []
    for base_spec in CASE_SPECS:
        for repeat in range(1, base_spec["repeats"] + 1):
            case_results.append(run_case(output_dir, base_spec, repeat))

    normal_results = [item for item in case_results if item["case_type"] in {"normal-a", "normal-b"}]
    fault_results = [item for item in case_results if item["case_type"] not in {"normal-a", "normal-b"}]
    passed_cases = sum(item["status"] == "pass" for item in case_results)
    fallback_recorded = [
        item["checks"].get("fallback_reason_and_target_recorded") is True
        for item in fault_results
    ]
    structured_results = [item for item in case_results if item["case_type"] == "structured-output-unsupported"]
    metrics = {
        "normal_cases_passed": sum(item["status"] == "pass" for item in normal_results),
        "fault_cases_passed": sum(item["status"] == "pass" for item in fault_results),
        "fallback_reason_missing_count": sum(not value for value in fallback_recorded),
        "capability_missing_not_explicit_count": sum(
            not item["checks"].get("failure_reason_explained", False) for item in structured_results
        ),
        "silent_semantic_change_count": sum(
            not item["checks"].get("silent_semantic_change_zero", False) for item in case_results
        ),
    }
    checks = {
        "all_cases_pass": passed_cases == len(case_results),
        "normal_deterministic_5_of_5_per_provider": all(
            sum(item["case_type"] == case_type and item["status"] == "pass" for item in case_results) == NORMAL_REPEATS
            for case_type in ("normal-a", "normal-b")
        ),
        "each_fault_repeated_three_times": all(
            sum(item["case_type"] == case_type for item in case_results) == FAULT_REPEATS
            for case_type in ("timeout-once", "stream-interrupt-once", "structured-output-unsupported")
        ),
        "fallback_reason_and_target_100_percent": metrics["fallback_reason_missing_count"] == 0,
        "capability_missing_explicit_100_percent": metrics["capability_missing_not_explicit_count"] == 0,
        "silent_semantic_changes_zero": metrics["silent_semantic_change_count"] == 0,
        "loopback_only_and_no_real_provider": all(
            item["checks"].get("loopback_only") is True for item in case_results
        ),
    }
    summary = {
        "schema": "zworkbench-w6-c5/v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "classification": "acceptance/evaluation",
        "fixture": {
            "manifest": read_json(MANIFEST),
            "manifest_sha256": digest(MANIFEST),
            "source_sha256": digest(FIXTURE),
            "router": str(ROUTER),
            "router_sha256": digest(ROUTER),
            "provider_configs": {name: read_json(path) for name, path in PROVIDERS.items()},
        },
        "runner": {
            "version": C5_VERSION,
            "path": str(Path(__file__).resolve()),
            "sha256": digest(Path(__file__).resolve()),
        },
        "threshold": {
            "normal_repeats_per_provider": NORMAL_REPEATS,
            "fault_repeats_per_fault": FAULT_REPEATS,
            "faults": ["timeout_once", "stream_interrupt_once", "structured_output_unsupported"],
            "normal_case_count": NORMAL_REPEATS * 2,
            "fault_case_count": FAULT_REPEATS * 3,
            "total_cases": len(case_results),
            "fallback_reason_and_target_recording": "100%",
            "capability_missing_explicit_degradation_or_safe_failure": "100%",
            "silent_semantic_changes": 0,
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
            "candidate_c5_requires_fixed_source_adapter": True,
            "missing_candidate_evidence_remains_unknown": True,
            "no_real_provider_or_external_side_effect": True,
            "failover_policy": "fallback to fake-a after explicit timeout/stream/capability reason; no silent provider switch",
            "structured_output_policy": "detect capability before request; fallback or safe-fail with explicit reason",
            "same_provider_retry_policy": "disabled in this fixture; switch-provider fallback is the bounded recovery",
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
