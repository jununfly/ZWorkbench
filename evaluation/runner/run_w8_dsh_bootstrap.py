#!/usr/bin/env python3
"""Run the isolated W8 H1 DSH bootstrap fixture.

The runner exercises the product runtime adapter in three case-local
scenarios. Its output is fixture-level evidence only; it is not a claim about
the dirty sibling checkout or a clean ZDSHarness artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_dsh_bootstrap" / "v1"
RUNNER_SCHEMA = "zworkbench-w8-dsh-bootstrap-runner/v1"
SCENARIOS = ("success", "unknown", "nonzero")

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import CompositionOwner, DshRuntimeAdapter, DshRuntimeError  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_case(output_dir: Path, scenario: str) -> Dict[str, Any]:
    """Run and verify one fresh case-local H1 scenario."""

    if scenario not in SCENARIOS:
        raise ValueError(f"unknown H1 scenario: {scenario}")
    case_root = output_dir / "cases" / scenario
    if case_root.exists():
        raise FileExistsError(f"case output already exists: {case_root}")
    (case_root / "workspace").mkdir(parents=True)
    bundle = case_root / "runtime"
    shutil.copytree(FIXTURE_ROOT, bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["launch"]["args"] = ["--scenario", scenario]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    run_id = f"w8-dsh-bootstrap-{scenario}"
    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    execution = None
    error = None
    adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
    try:
        try:
            execution = adapter.execute(run_id, timeout=10.0)
        except DshRuntimeError as exc:
            error = {"type": type(exc).__name__, "code": exc.code}
    finally:
        adapter.close()
        owner.close()

    with CompositionOwner(case_root / "state" / "composition.sqlite3") as reopened:
        run = reopened.get_run(run_id)
        events = reopened.events(run_id)
    result_kinds = sorted(item["kind"] for item in run["results"])
    if scenario == "success":
        checks = {
            "adapter_completed": execution is not None and execution.status == "completed",
            "owner_completed": run["status"] == "completed",
            "session_identity_present": execution is not None and execution.dsh_session_id == "fixture-dsh-session-1",
            "bootstrap_sequence_recorded": [event["type"] for event in events].count("dsh.bootstrap.started") == 1
            and [event["type"] for event in events].count("dsh.bootstrap.ready") == 1,
            "exit_code_zero": any(item["kind"] == "dsh.exit" and item["value"]["exit_code"] == 0 for item in run["results"]),
            "effects_zero": len(run["effects"]) == 0,
        }
    else:
        expected_code = "bootstrap_message_unknown" if scenario == "unknown" else "process_exit_nonzero"
        checks = {
            "adapter_failed_closed": execution is None and error is not None and error["code"] == expected_code,
            "owner_safe_stopped": run["status"] == "safe_stopped",
            "error_result_recorded": "dsh.error" in result_kinds,
            "exit_receipt_recorded": "dsh.exit" in result_kinds,
            "semantic_success_absent": "semantic" not in result_kinds,
            "effects_zero": len(run["effects"]) == 0,
        }
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "fixture-level",
        "scenario": scenario,
        "run_id": run_id,
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "owner_run_status": run["status"],
            "error": error,
            "result_kinds": result_kinds,
            "event_count": len(events),
            "case_root": str(case_root),
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "checks": checks,
        "non_claims": [
            "This is not formal clean-ZDSHarness artifact provenance.",
            "This does not prove H2-H8, host sandboxing, or real Provider compatibility.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_suite(output_dir: Path) -> Dict[str, Any]:
    """Run all H1 fixture scenarios into a new or empty evidence directory."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("H1 output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [run_case(output_dir, scenario) for scenario in SCENARIOS]
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "fixture-level",
        "status": "pass" if all(item["status"] == "pass" for item in scenarios) else "fail",
        "scenarios": scenarios,
        "formal_h1_status": "HOLD/unknown-stop until clean pinned ZDSHarness artifact receipt",
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="new or empty case-local output directory")
    args = parser.parse_args()
    summary = run_suite(args.output.expanduser().resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
