#!/usr/bin/env python3
"""Exercise the W6 continuous-evaluation control-plane contract.

This runner deliberately does not invoke a candidate Harness.  It runs the
isolated W6 fixture self-test for every control cycle, then feeds sealed,
synthetic candidate summaries through the read-only regression gate.  The
purpose is to prove the evidence chain for drift detection, pause, rollback,
and rerun before W7 binds a real candidate adapter.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from check_regression import CANDIDATES, make_gate_result
from run_baseline import CANDIDATE_REFS, FIXTURE, MANIFEST, RUNS, digest, run_fixture_self_test


RUNNER_VERSION = "w6-continuous-evaluator/v1"
CONTROL_SOURCE = "synthetic-control-fixture-only"
IDENTITY_MUTATIONS = (
    ("harness", ("harness",), "control-harness-v2"),
    ("scheduler", ("components", "scheduler"), "external-trigger-v2"),
    ("provider_model", ("provider", "model"), "fake-model-v2"),
    ("provider_endpoint", ("provider", "endpoint"), "http://127.0.0.1:11435"),
    ("prompt", ("prompt_sha256",), "prompt-sha256-v2"),
    ("tool_schema", ("tool_schema_sha256",), "tool-schema-sha256-v2"),
    ("permission_policy", ("permission_policy_sha256",), "policy-sha256-v2"),
    ("fixture_source", ("fixture", "source_sha256"), "fixture-source-sha256-v2"),
    ("evaluator", ("evaluator_version",), "w6-continuous-evaluator-v2"),
    ("sandbox", ("sandbox", "mode"), "fixture-local-v2"),
    ("replay_cassette", ("replay_cassette_sha256",), "cassette-sha256-v2"),
    ("dependencies", ("dependencies_sha256",), "dependencies-sha256-v2"),
    ("config", ("config_sha256",), "config-sha256-v2"),
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def set_path(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def fixture_payload():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        "manifest": manifest,
        "manifest_sha256": digest(MANIFEST),
        "source_sha256": digest(FIXTURE),
    }


def base_evaluation_identity(fixture):
    return {
        "harness": "control-harness-v1",
        "components": {
            "scheduler": "external-trigger-v1",
            "state": "durable-ledger-v1",
            "replay": "cassette-contract-v1",
        },
        "provider": {
            "provider": "fake-a",
            "model": "fake-model",
            "endpoint": "http://127.0.0.1:11434",
            "wire_api": "openai-compatible-loopback-v1",
        },
        "prompt_sha256": "prompt-sha256-v1",
        "tool_schema_sha256": "tool-schema-sha256-v1",
        "permission_policy_sha256": "policy-sha256-v1",
        "fixture": {
            "version": fixture["manifest"]["version"],
            "fixture_id": fixture["manifest"]["fixture_id"],
            "manifest_sha256": fixture["manifest_sha256"],
            "source_sha256": fixture["source_sha256"],
        },
        "evaluator_version": RUNNER_VERSION,
        "sandbox": {"mode": "fixture-local-v1", "network": "loopback-only"},
        "replay_cassette_sha256": "cassette-sha256-v1",
        "dependencies_sha256": "dependencies-sha256-v1",
        "config_sha256": "config-sha256-v1",
    }


def provider_result():
    samples = [
        {
            "sample": number,
            "status": "pass",
            "test_returncode": 0,
            "modified_outside_allowed": [],
            "event_completeness": 1.0,
            "forbidden_command_observed": False,
        }
        for number in range(1, 6)
    ]
    return {
        "status": "pass",
        "sample_count": 5,
        "passed_count": 5,
        "success_test_pass_rate": 1.0,
        "out_of_scope_modifications": 0,
        "samples": samples,
    }


def control_summary(run_id, fixture, identity, self_test, scenario_overrides=None, fixture_overrides=None):
    scenario_overrides = scenario_overrides or {}
    fixture_overrides = fixture_overrides or {}
    summary_fixture = copy.deepcopy(fixture)
    summary_fixture.update(fixture_overrides)
    identity = copy.deepcopy(identity)
    identity["fixture"] = {
        "version": summary_fixture["manifest"]["version"],
        "fixture_id": summary_fixture["manifest"]["fixture_id"],
        "manifest_sha256": summary_fixture["manifest_sha256"],
        "source_sha256": summary_fixture["source_sha256"],
    }

    candidate_preflight = {}
    candidate_baseline = {}
    for candidate in CANDIDATES:
        source_ref = {"repository": "fixture://control", "commit": "control-v1"}
        candidate_preflight[candidate] = {
            "adapter": "control-fixture-adapter-v1",
            "source_ref": source_ref,
            "preflight": {
                "version": {"stdout": f"control-{candidate.lower().replace(' ', '-')}-v1"},
            },
        }
        scenarios = {scenario: "pass" for scenario in ("C1", "C2", "C3", "C4", "C5", "C6", "C7")}
        scenarios.update(scenario_overrides.get(candidate, {}))
        candidate_baseline[candidate] = {
            "adapter": "control-fixture-adapter-v1",
            "source_ref": source_ref,
            "scenarios": scenarios,
            "provider_results": {"fake-a": provider_result(), "fake-b": provider_result()},
            "evidence_origin": CONTROL_SOURCE,
        }

    return {
        "schema": "zworkbench-w6-baseline/v1",
        "run_id": run_id,
        "started_at": "2026-08-30T00:00:00+00:00",
        "finished_at": "2026-08-30T00:00:01+00:00",
        "classification": "acceptance/evaluation",
        "fixture": summary_fixture,
        "fixture_self_test": self_test,
        "evaluation_identity": identity,
        "candidate_preflight": candidate_preflight,
        "candidate_baseline": candidate_baseline,
        "interpretation": {
            "synthetic_control_only": True,
            "candidate_invoked": False,
            "source": CONTROL_SOURCE,
        },
    }


def run_gate(output_dir, label, baseline, current, expect_status):
    cycle_dir = output_dir / "cycles" / label
    baseline_path = cycle_dir / "baseline-summary.json"
    current_path = cycle_dir / "current-summary.json"
    gate_path = cycle_dir / "regression-gate.json"
    write_json(baseline_path, baseline)
    write_json(current_path, current)
    result = make_gate_result(baseline_path, current_path, baseline, current)
    result["cycle"] = label
    result["expected_status"] = expect_status
    result["expectation_met"] = result["status"] == expect_status
    result["regression_executed"] = all(item.get("status") == "pass" for item in current.get("fixture_self_test", []))
    result["candidate_invoked"] = False
    write_json(gate_path, result)
    if result["status"] != expect_status or not result["regression_executed"]:
        raise RuntimeError(f"control cycle {label} did not meet expectation: {result['status']} / {expect_status}")
    if result["status"] != "pass":
        write_json(cycle_dir / "pause-decision.json", {
            "schema": "zworkbench-w6-pause-decision/v1",
            "cycle": label,
            "action": "pause-upgrade-and-composition",
            "reason": "regression gate is not pass",
            "gate_status": result["status"],
            "drift_reasons": result["drift_reasons"],
            "hard_failures": result["hard_failures"],
            "unknowns": result["unknowns"],
            "rollback_required": True,
            "rollback_target": "control-harness-v1",
        })
    return result


def make_mutated_identity(identity, path, replacement):
    mutated = copy.deepcopy(identity)
    set_path(mutated, path, replacement)
    return mutated


def build_control_run(output_dir):
    fixture = fixture_payload()
    self_test = run_fixture_self_test()
    if any(item.get("status") != "pass" for item in self_test):
        raise RuntimeError("W6 fixture self-test failed before continuous-evaluation controls ran")
    identity = base_evaluation_identity(fixture)
    base = control_summary("control-baseline-v1", fixture, identity, self_test)

    cycles = []
    stable = run_gate(
        output_dir,
        "stable-no-drift",
        base,
        copy.deepcopy(base),
        "pass",
    )
    cycles.append(stable)

    drift_cases = []
    for name, path, replacement in IDENTITY_MUTATIONS:
        mutated_fixture = {}
        if name == "fixture_source":
            mutated_fixture["source_sha256"] = replacement
        current = control_summary(
            f"control-drift-{name}",
            fixture,
            make_mutated_identity(identity, path, replacement),
            self_test,
            fixture_overrides=mutated_fixture,
        )
        expected_status = "fail" if name == "fixture_source" else "pass"
        gate = run_gate(output_dir, f"drift-{name}", base, current, expected_status)
        drift_cases.append({
            "dimension": name,
            "path": ".".join(path),
            "replacement": replacement,
            "status": gate["status"],
            "expected_status": expected_status,
            "drift_triggered": gate["drift_triggered"],
            "drift_reasons": gate["drift_reasons"],
            "regression_executed": gate["regression_executed"],
            "upgrade_decision": gate["upgrade_decision"],
            "expectation_met": gate["expectation_met"],
        })

    v2_identity = make_mutated_identity(identity, ("harness",), "control-harness-v2")
    upgraded = control_summary("control-upgraded-v2", fixture, v2_identity, self_test)
    failed = control_summary(
        "control-failed-v2",
        fixture,
        v2_identity,
        self_test,
        scenario_overrides={"Codex Harness": {"C2": "fail"}},
    )
    failure_gate = run_gate(output_dir, "hard-failure-pauses", upgraded, failed, "fail")
    pending = control_summary(
        "control-pending-v2",
        fixture,
        v2_identity,
        self_test,
        scenario_overrides={"Codex Harness": {"C7": "unknown"}},
    )
    pending_gate = run_gate(output_dir, "unknown-pauses", upgraded, pending, "pending")

    rollback = control_summary("control-rollback-v1", fixture, identity, self_test)
    rollback_gate = run_gate(output_dir, "rollback-rerun-v1", failed, rollback, "pass")
    rollback_dir = output_dir / "cycles" / "rollback-rerun-v1"
    write_json(rollback_dir / "rollback-decision.json", {
        "schema": "zworkbench-w6-rollback-decision/v1",
        "action": "rollback-and-rerun",
        "from_identity": v2_identity,
        "to_identity": identity,
        "target": "control-harness-v1",
        "reason": "hard-failure-pauses gate before retrying the upgraded identity",
        "source_of_target": str(output_dir / "cycles" / "stable-no-drift" / "baseline-summary.json"),
        "new_gate": str(rollback_dir / "regression-gate.json"),
        "candidate_invoked": False,
    })

    assertions = [
        {"name": "stable cycle allows upgrade", "passed": stable["status"] == "pass" and stable["allow_upgrade"]},
        {"name": "every identity dimension triggers drift", "passed": all(item["drift_triggered"] and item["regression_executed"] for item in drift_cases)},
        {"name": "fixture drift is fail-closed", "passed": next(item for item in drift_cases if item["dimension"] == "fixture_source")["status"] == "fail"},
        {"name": "hard failure pauses", "passed": failure_gate["status"] == "fail" and failure_gate["upgrade_decision"] == "pause"},
        {"name": "unknown pauses", "passed": pending_gate["status"] == "pending" and pending_gate["upgrade_decision"] == "pause"},
        {"name": "rollback rerun is independently gated", "passed": rollback_gate["status"] == "pass" and rollback_gate["drift_triggered"]},
        {"name": "no candidate or external side effect", "passed": all(not item.get("candidate_invoked", True) for item in [stable, failure_gate, pending_gate, rollback_gate])},
    ]
    result = {
        "schema": "zworkbench-w6-continuous-evaluation/v1",
        "run_id": output_dir.name,
        "runner_version": RUNNER_VERSION,
        "classification": "acceptance/evaluation",
        "source": CONTROL_SOURCE,
        "fixture": {
            "version": fixture["manifest"]["version"],
            "fixture_id": fixture["manifest"]["fixture_id"],
            "manifest_sha256": fixture["manifest_sha256"],
            "source_sha256": fixture["source_sha256"],
        },
        "contract": {
            "drift_dimensions": [item[0] for item in IDENTITY_MUTATIONS],
            "hard_failure_action": "pause-upgrade-and-composition",
            "unknown_action": "pause-upgrade-and-composition",
            "rollback_action": "rollback-to-last-known-good-identity-and-rerun",
            "candidate_invoked": False,
            "external_network": False,
        },
        "stable_cycle": {
            "status": stable["status"],
            "drift_triggered": stable["drift_triggered"],
            "upgrade_decision": stable["upgrade_decision"],
        },
        "drift_matrix": drift_cases,
        "failure_cycle": {"status": failure_gate["status"], "pause": True},
        "unknown_cycle": {"status": pending_gate["status"], "pause": True},
        "rollback_cycle": {
            "status": rollback_gate["status"],
            "drift_triggered": rollback_gate["drift_triggered"],
            "rerun": True,
        },
        "assertions": assertions,
        "status": "pass" if all(item["passed"] for item in assertions) else "fail",
    }
    write_json(output_dir / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w6-0.1-continuous-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        result = build_control_run(output_dir)
    except Exception as exc:
        write_json(output_dir / "summary.json", {
            "schema": "zworkbench-w6-continuous-evaluation/v1",
            "run_id": output_dir.name,
            "runner_version": RUNNER_VERSION,
            "classification": "acceptance/evaluation",
            "source": CONTROL_SOURCE,
            "status": "fail",
            "error": str(exc),
        })
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
