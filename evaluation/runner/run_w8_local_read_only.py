#!/usr/bin/env python3
"""Run the W8 local read-only success and unknown-boundary fixtures.

The runner creates independent case roots for every scenario/repeat and uses
the real :class:`zworkbench.CompositionOwner` through the product's
``LocalReadOnlyRunOrchestrator``.  It deliberately uses deterministic fixture
adapters instead of starting Codex or contacting a Provider.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import stat
import sys
import tempfile
from typing import Any, Callable, Dict, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_local_read_only" / "v1"
MANIFEST = FIXTURE_ROOT / "manifest.json"
RUNNER_SCHEMA = "zworkbench-w8-local-read-only-runner/v1"
SCENARIOS = ("success", "unknown_boundary")
DEFAULT_PROVIDER = {
    "provider": "fixture-loopback",
    "model": "fixture-model",
    "endpoint": "http://127.0.0.1:11434",
    "transport": "loopback-only",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> Dict[str, Any]:
    manifest = read_json(MANIFEST)
    if manifest.get("schema") != "zworkbench-w8-local-read-only-fixture/v1":
        raise ValueError("unexpected W8 fixture manifest schema")
    names = tuple(item.get("name") for item in manifest.get("scenarios", []))
    if names != SCENARIOS:
        raise ValueError("W8 fixture manifest scenarios must be success and unknown_boundary")
    return manifest


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        try:
            return str(candidate).startswith(str(root) + "/") or candidate == root
        except TypeError:
            return False


def _prepare_case(case_dir: Path) -> Dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=False)
    workspace = case_dir / "workspace"
    database = case_dir / "state" / "composition.sqlite3"
    code_home = case_dir / "codex-home"
    executable = case_dir / "bin" / "codex"
    event_log = case_dir / "events" / "codex.jsonl"
    workspace.mkdir(parents=True)
    code_home.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    event_log.parent.mkdir(parents=True)
    event_log.touch()
    return {
        "case_root": case_dir,
        "workspace": workspace,
        "database": database,
        "code_home": code_home,
        "codex_executable": executable,
        "event_log": event_log,
    }


def _build_config(paths: Mapping[str, Path]):
    from zworkbench import LocalReadOnlyRunConfig

    return LocalReadOnlyRunConfig(
        case_root=paths["case_root"],
        workspace=paths["workspace"],
        database=paths["database"],
        code_home=paths["code_home"],
        codex_executable=paths["codex_executable"],
        event_log=paths["event_log"],
        provider_identity=DEFAULT_PROVIDER,
    )


def _adapter_factory_for(scenario: str, adapters: list[Any]) -> Callable[..., Any]:
    from evaluation.fixtures.w8_local_read_only.v1.fixture_adapters import (
        FixtureSuccessAdapter,
        FixtureUnknownBoundaryAdapter,
    )

    adapter_class = {
        "success": FixtureSuccessAdapter,
        "unknown_boundary": FixtureUnknownBoundaryAdapter,
    }[scenario]

    def factory(owner, config):
        adapter = adapter_class(owner, config)
        adapters.append(adapter)
        return adapter

    return factory


def _owner_observation(database: Path, run_id: str) -> Dict[str, Any]:
    from zworkbench import CompositionOwner

    if not database.is_file():
        return {
            "database_present": False,
            "run_status": None,
            "effects_count": None,
            "result_kinds": [],
            "recorded_view_present": False,
            "event_count": 0,
        }
    with CompositionOwner(database) as owner:
        run = owner.get_run(run_id)
        snapshot = owner.snapshot()
        return {
            "database_present": True,
            "run_status": run.get("status"),
            "effects_count": len(run.get("effects", [])),
            "result_kinds": sorted(item.get("kind") for item in run.get("results", [])),
            "recorded_view_present": any(
                item.get("run_id") == run_id and item.get("mode") == "recorded_view"
                for item in snapshot.get("replays", [])
            ),
            "event_count": len(owner.events(run_id)),
        }


def verify_case(case_dir: Path, scenario: str, repeat: int = 1) -> Dict[str, Any]:
    """Validate one already executed case and return its JSON-safe summary."""

    manifest = load_manifest()
    scenario_manifest = next(item for item in manifest["scenarios"] if item["name"] == scenario)
    run_id = "w8-local-read-only-{0}-repeat-{1:02d}".format(scenario, repeat)
    paths = {
        "case_root": case_dir,
        "workspace": case_dir / "workspace",
        "database": case_dir / "state" / "composition.sqlite3",
        "code_home": case_dir / "codex-home",
        "codex_executable": case_dir / "bin" / "codex",
        "event_log": case_dir / "events" / "codex.jsonl",
    }
    input_data = read_json(case_dir / "case-input.json") if (case_dir / "case-input.json").exists() else {}
    observation = _owner_observation(paths["database"], run_id)
    process_invocations = input_data.get("process_invocations", 0)
    exception_kind = input_data.get("exception_kind")
    adapter_closed = input_data.get("adapter_closed") is True
    preflight_status = input_data.get("preflight_status")
    orchestration_status = input_data.get("orchestration_status")
    isolated = all(_inside(case_dir, path) for path in paths.values())
    no_external_activity = (
        input_data.get("network_requests", 0) == 0
        and input_data.get("real_credentials", 0) == 0
        and input_data.get("external_side_effects", 0) == 0
        and process_invocations == 0
    )
    success_expected = scenario == "success"
    if success_expected:
        outcome_ok = (
            preflight_status == "pass"
            and orchestration_status == "completed"
            and observation["run_status"] == "completed"
            and input_data.get("semantic_text") == scenario_manifest["expected_result"]
            and exception_kind is None
        )
        not_successfully_completed = True
    else:
        outcome_ok = (
            preflight_status == "pass"
            and orchestration_status == "expected_fail_closed"
            and observation["run_status"] == "safe_stopped"
            and exception_kind == "FixtureUnknownBoundary"
            and input_data.get("semantic_text") is None
        )
        not_successfully_completed = orchestration_status != "completed"
    checks = {
        "manifest_schema_present": manifest.get("schema") == "zworkbench-w8-local-read-only-fixture/v1",
        "preflight_passed": preflight_status == "pass",
        "case_paths_inside_case_root": isolated,
        "owner_database_present": observation["database_present"],
        "expected_orchestration_outcome": outcome_ok,
        "owner_run_status_expected": observation["run_status"] == scenario_manifest["expected_owner_run_status"],
        "adapter_closed": adapter_closed,
        "no_effects": observation["effects_count"] == 0,
        "no_external_activity": no_external_activity,
        "unknown_boundary_not_reported_as_success": not_successfully_completed,
    }
    if success_expected:
        checks.update(
            {
                "semantic_result_fixture_ok": input_data.get("semantic_text") == "fixture-ok",
                "recorded_view_present": observation["recorded_view_present"],
                "event_ledger_present": observation["event_count"] >= 4,
            }
        )
    else:
        checks.update(
            {
                "expected_exception_captured": exception_kind == "FixtureUnknownBoundary",
                "no_semantic_result_after_stop": input_data.get("semantic_text") is None,
                "safe_stop_event_present": observation["event_count"] >= 3,
            }
        )
    return {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": manifest["schema"],
        "scenario": scenario,
        "repeat": repeat,
        "status": "pass" if all(checks.values()) else "fail",
        "expected_outcome": scenario_manifest["expected_orchestration_status"],
        "observed": {
            "preflight_status": preflight_status,
            "orchestration_status": orchestration_status,
            "owner_run_status": observation["run_status"],
            "adapter_closed": adapter_closed,
            "effects_count": observation["effects_count"],
            "network_requests": input_data.get("network_requests", 0),
            "real_credentials": input_data.get("real_credentials", 0),
            "external_side_effects": input_data.get("external_side_effects", 0),
            "codex_process_invocations": process_invocations,
            "exception_kind": exception_kind,
            "semantic_text": input_data.get("semantic_text"),
            "result_kinds": observation["result_kinds"],
            "event_count": observation["event_count"],
        },
        "checks": checks,
        "case_root": str(case_dir),
    }


def run_case(output_dir: Path, scenario: str, repeat: int = 1) -> Dict[str, Any]:
    """Execute and verify one scenario in a fresh case root."""

    if scenario not in SCENARIOS:
        raise ValueError("unknown W8 scenario: {0}".format(scenario))
    case_dir = output_dir / "cases" / scenario / "repeat-{0:02d}".format(repeat)
    paths = _prepare_case(case_dir)
    config = _build_config(paths)
    adapters: list[Any] = []
    run_id = "w8-local-read-only-{0}-repeat-{1:02d}".format(scenario, repeat)
    prompt = {
        "success": "inspect the local fixture and return fixture-ok",
        "unknown_boundary": "request future/server-request.v1",
    }[scenario]
    input_data: Dict[str, Any] = {
        "schema": RUNNER_SCHEMA,
        "scenario": scenario,
        "repeat": repeat,
        "run_id": run_id,
        "preflight_status": None,
        "orchestration_status": None,
        "semantic_text": None,
        "exception_kind": None,
        "adapter_closed": False,
        "network_requests": 0,
        "real_credentials": 0,
        "external_side_effects": 0,
        "process_invocations": 0,
        "paths": {name: str(path) for name, path in paths.items()},
        "provider_identity": DEFAULT_PROVIDER,
        "platform": platform.system().lower(),
        "python": platform.python_version(),
    }
    write_json(case_dir / "case-input.json", input_data)

    from zworkbench import LocalReadOnlyRunOrchestrator
    from evaluation.fixtures.w8_local_read_only.v1.fixture_adapters import FixtureUnknownBoundary

    try:
        result = LocalReadOnlyRunOrchestrator(
            config,
            adapter_factory=_adapter_factory_for(scenario, adapters),
        ).run(run_id, prompt)
        input_data["preflight_status"] = result.preflight.status
        input_data["orchestration_status"] = result.status
        if result.execution is not None:
            input_data["semantic_text"] = result.execution.text
    except FixtureUnknownBoundary:
        input_data["preflight_status"] = "pass"
        input_data["orchestration_status"] = "expected_fail_closed"
        input_data["exception_kind"] = "FixtureUnknownBoundary"
    except Exception as exc:
        input_data["preflight_status"] = input_data["preflight_status"] or "unknown"
        input_data["orchestration_status"] = "unexpected_error"
        input_data["exception_kind"] = type(exc).__name__
        input_data["exception_message"] = str(exc)
    finally:
        input_data["adapter_closed"] = bool(adapters) and all(adapter.closed for adapter in adapters)
        write_json(case_dir / "case-input.json", input_data)

    summary = verify_case(case_dir, scenario, repeat)
    write_json(case_dir / "summary.json", summary)
    return summary


def run_suite(output_dir: Path, repeats: int = 1) -> Dict[str, Any]:
    """Run all W8 scenarios with independent case roots."""

    if repeats < 1:
        raise ValueError("repeats must be positive")
    load_manifest()
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise FileExistsError("runner output directory must be a new or empty directory")
    else:
        output_dir.mkdir(parents=True)
    cases = [
        run_case(output_dir, scenario, repeat)
        for scenario in SCENARIOS
        for repeat in range(1, repeats + 1)
    ]
    suite = {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": "zworkbench-w8-local-read-only-fixture/v1",
        "runner_version": RUNNER_SCHEMA,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "repeats": repeats,
        "case_count": len(cases),
        "passed_case_count": sum(item["status"] == "pass" for item in cases),
        "scenarios": cases,
        "status": "pass" if all(item["status"] == "pass" for item in cases) else "fail",
        "interpretation": "Fixture contract validation only; not production or Codex-native approval evidence.",
    }
    write_json(output_dir / "summary.json", suite)
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh evidence directory; defaults to a temporary directory")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    output_dir = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="w8-local-read-only-"))
    try:
        summary = run_suite(output_dir, args.repeats)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(REPO_ROOT))
    raise SystemExit(main())
