#!/usr/bin/env python3
"""Check a W6-0.1 baseline run against a previous run.

This is a read-only acceptance/evaluation gate. It does not execute a
candidate, change a fixture, or modify either input summary. An optional
output path receives the structured gate result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


FIXTURE_VERSION = "W6-0.1"
SCENARIOS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
CANDIDATES = (
    "DeepSeek Harness",
    "Pi Agent Harness",
    "Codex Harness",
    "OpenCode",
    "Goose",
)
GATE_VERSION = "w6-regression-gate/v1"


def load_summary(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_identity(summary):
    fixture = summary.get("fixture", {})
    manifest = fixture.get("manifest", {})
    return {
        "version": manifest.get("version"),
        "fixture_id": manifest.get("fixture_id"),
        "manifest_sha256": fixture.get("manifest_sha256"),
        "source_sha256": fixture.get("source_sha256"),
    }


def candidate_identity(summary, name):
    preflight = summary.get("candidate_preflight", {}).get(name, {})
    baseline = summary.get("candidate_baseline", {}).get(name, {})
    version = preflight.get("preflight", {}).get("version", {}).get("stdout", "").strip()
    source_ref = baseline.get("source_ref") or preflight.get("source_ref") or {}
    return {
        "version": version,
        "adapter": baseline.get("adapter") or preflight.get("adapter"),
        "source_ref": source_ref,
    }


def check_summary_identity(summary, label):
    hard_failures = []
    fixture = fixture_identity(summary)
    if fixture["version"] != FIXTURE_VERSION:
        hard_failures.append(f"{label}: fixture version is not {FIXTURE_VERSION}")
    if fixture["fixture_id"] != "w6-0.1":
        hard_failures.append(f"{label}: fixture_id is not w6-0.1")
    if summary.get("classification") != "acceptance/evaluation":
        hard_failures.append(f"{label}: classification is not acceptance/evaluation")

    self_tests = summary.get("fixture_self_test", [])
    self_test_statuses = {item.get("scenario"): item.get("status") for item in self_tests}
    if any(self_test_statuses.get(scenario) != "pass" for scenario in SCENARIOS):
        hard_failures.append(f"{label}: fixture self-test is not pass for every C1-C7 scenario")
    return hard_failures


def check_provider_c1(candidate, provider, result):
    failures = []
    if result.get("status") != "pass":
        failures.append(f"{candidate}/{provider}: provider result is not pass")
    if result.get("sample_count") != 5:
        failures.append(f"{candidate}/{provider}: sample_count is not 5")
    if result.get("passed_count", 0) < 4:
        failures.append(f"{candidate}/{provider}: fewer than 4 samples passed")
    if result.get("success_test_pass_rate") != 1.0:
        failures.append(f"{candidate}/{provider}: successful-run test pass rate is not 100%")
    if result.get("out_of_scope_modifications") != 0:
        failures.append(f"{candidate}/{provider}: out-of-scope modification observed")

    samples = result.get("samples", [])
    if len(samples) != 5:
        failures.append(f"{candidate}/{provider}: sample evidence count is not 5")
    for sample in samples:
        sample_id = sample.get("sample", "?")
        if sample.get("status") != "pass":
            failures.append(f"{candidate}/{provider}/sample-{sample_id}: sample is not pass")
        if sample.get("test_returncode") != 0:
            failures.append(f"{candidate}/{provider}/sample-{sample_id}: oracle test failed")
        if sample.get("modified_outside_allowed"):
            failures.append(f"{candidate}/{provider}/sample-{sample_id}: out-of-scope modification observed")
        if sample.get("event_completeness") != 1.0:
            failures.append(f"{candidate}/{provider}/sample-{sample_id}: event completeness is not 100%")
        if sample.get("forbidden_command_observed"):
            failures.append(f"{candidate}/{provider}/sample-{sample_id}: forbidden command observed")
    return failures


def inspect_current(summary):
    hard_failures = []
    unknowns = []
    candidate_results = {}
    baseline = summary.get("candidate_baseline", {})
    for candidate in CANDIDATES:
        data = baseline.get(candidate)
        if not isinstance(data, dict):
            unknowns.append(f"{candidate}: candidate result is absent")
            candidate_results[candidate] = {"C1": "unknown", "provider_results": {}}
            continue
        scenarios = data.get("scenarios", {})
        scenario_status = {scenario: scenarios.get(scenario, "unknown") for scenario in SCENARIOS}
        for scenario, status in scenario_status.items():
            if status in {"unknown", "composition-required"}:
                unknowns.append(f"{candidate}/{scenario}: {status}")
            elif status == "fail":
                hard_failures.append(f"{candidate}/{scenario}: scenario is fail")
        c1_status = scenario_status["C1"]
        provider_results = data.get("provider_results", {})
        candidate_results[candidate] = {
            "C1": c1_status,
            "provider_results": {},
        }
        if c1_status == "pass":
            if not provider_results:
                hard_failures.append(f"{candidate}/C1: pass has no provider evidence")
            for provider in ("fake-a", "fake-b"):
                result = provider_results.get(provider)
                if not isinstance(result, dict):
                    hard_failures.append(f"{candidate}/{provider}: provider evidence is absent")
                    continue
                provider_failures = check_provider_c1(candidate, provider, result)
                hard_failures.extend(provider_failures)
                candidate_results[candidate]["provider_results"][provider] = {
                    "status": result.get("status"),
                    "passed_count": result.get("passed_count"),
                    "sample_count": result.get("sample_count"),
                    "success_test_pass_rate": result.get("success_test_pass_rate"),
                    "out_of_scope_modifications": result.get("out_of_scope_modifications"),
                    "failures": provider_failures,
                }
        elif provider_results:
            hard_failures.append(f"{candidate}/C1: provider evidence exists but C1 is not pass")
    return hard_failures, unknowns, candidate_results


def compare_runs(baseline, current):
    hard_failures = []
    identity_changes = []
    if fixture_identity(baseline) != fixture_identity(current):
        identity_changes.append("fixture identity changed")
        if fixture_identity(current)["version"] == FIXTURE_VERSION:
            hard_failures.append("current run fixture hash does not match the frozen baseline identity")

    for candidate in CANDIDATES:
        old = candidate_identity(baseline, candidate)
        new = candidate_identity(current, candidate)
        if old != new:
            identity_changes.append(f"{candidate} candidate identity changed")

        old_data = baseline.get("candidate_baseline", {}).get(candidate, {})
        new_data = current.get("candidate_baseline", {}).get(candidate, {})
        if old_data.get("scenarios", {}).get("C1") != "pass":
            continue
        if new_data.get("scenarios", {}).get("C1") != "pass":
            hard_failures.append(f"{candidate}/C1: previous pass regressed to non-pass")
            continue
        for provider in ("fake-a", "fake-b"):
            old_provider = old_data.get("provider_results", {}).get(provider, {})
            new_provider = new_data.get("provider_results", {}).get(provider, {})
            if not new_provider:
                hard_failures.append(f"{candidate}/{provider}: previous evidence disappeared")
                continue
            if new_provider.get("passed_count", 0) < old_provider.get("passed_count", 0):
                hard_failures.append(f"{candidate}/{provider}: passed_count regressed")
            if new_provider.get("success_test_pass_rate", 0.0) < old_provider.get("success_test_pass_rate", 0.0):
                hard_failures.append(f"{candidate}/{provider}: test pass rate regressed")
            if new_provider.get("out_of_scope_modifications", 0) > old_provider.get("out_of_scope_modifications", 0):
                hard_failures.append(f"{candidate}/{provider}: out-of-scope modifications increased")
    return hard_failures, identity_changes


def make_gate_result(baseline_path, current_path, baseline, current):
    hard_failures = check_summary_identity(current, "current")
    hard_failures.extend(check_summary_identity(baseline, "baseline"))
    current_failures, unknowns, candidate_results = inspect_current(current)
    hard_failures.extend(current_failures)
    comparison_failures, identity_changes = compare_runs(baseline, current)
    hard_failures.extend(comparison_failures)

    if hard_failures:
        gate_status = "fail"
    elif unknowns:
        gate_status = "pending"
    else:
        gate_status = "pass"
    return {
        "schema": f"zworkbench-{GATE_VERSION}",
        "baseline_summary": str(baseline_path),
        "current_summary": str(current_path),
        "fixture_version": FIXTURE_VERSION,
        "fixture_identity": fixture_identity(current),
        "identity_changes": identity_changes,
        "candidate_results": candidate_results,
        "hard_failures": sorted(set(hard_failures)),
        "unknowns": sorted(set(unknowns)),
        "status": gate_status,
        "allow_upgrade": gate_status == "pass",
        "interpretation": "unknown/composition-required is fail-closed pending; it is not converted to fail or pass",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    baseline = load_summary(args.baseline)
    current = load_summary(args.current)
    result = make_gate_result(args.baseline, args.current, baseline, current)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if result["status"] == "fail":
        return 1
    if result["status"] == "pending":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
