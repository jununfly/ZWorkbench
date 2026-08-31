#!/usr/bin/env python3
"""Run C7 backup/restore and exit against a real owner-backed Codex flow.

Unlike the earlier C7 fixture, this runner does not manufacture a JSON
composition state.  Every case first runs the product
``CodexAppServerAdapter`` against the fixed local Codex app-server and a
loopback-only fake Provider.  The resulting SQLite state is then the subject
of the backup/restore or exit audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_PROVIDER = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c5-c6" / "fake-provider.py"
RUNS = REPO_ROOT / "evaluation" / "runs"
CODEX_DEFAULT = shutil.which("codex")
SCHEMA = "zworkbench-w7-codex-owner-c7/v1"
RUNNER_VERSION = "w7-codex-owner-c7-runner/v1"
ADAPTER_SCHEMA = "zworkbench-codex-app-server-adapter/v1"
SCENARIOS = ("backup_restore", "exit")
REPEATS = 3
OWNER_C7_PROVIDER_ID = "w7-owner-c7-loopback"
OLLAMA_PORT = 11434
MAX_MAINTAINED_SERVICES = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hasher = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        hasher.update(str(child.relative_to(path)).encode("utf-8"))
        hasher.update(child.read_bytes())
    return hasher.hexdigest()


def wait_ready(path: Path, process: subprocess.Popen, timeout: float = 8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"fake Provider exited before readiness: {process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"fake Provider readiness timed out: {path}")


def start_provider(case_dir: Path):
    ready = case_dir / "provider.ready.json"
    request_log = case_dir / "provider-requests.jsonl"
    stderr_path = case_dir / "provider-stderr.log"
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(FAKE_PROVIDER),
            "--host",
            "127.0.0.1",
            "--port",
            str(OLLAMA_PORT),
            "--provider-id",
            OWNER_C7_PROVIDER_ID,
            "--mode",
            "normal",
            "--capabilities",
            "text,streaming",
            "--command",
            "printf fixture-ok",
            "--request-log",
            str(request_log),
            "--ready-file",
            str(ready),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        start_new_session=True,
    )
    try:
        info = wait_ready(ready, process)
    except Exception:
        stop_process(process, stderr)
        raise
    return {
        "process": process,
        "stderr": stderr,
        "endpoint": f"http://127.0.0.1:{info['port']}",
        "provider_id": info["provider_id"],
        "request_log": request_log,
    }


def stop_process(process, stderr=None) -> None:
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    if stderr is not None:
        stderr.close()


def service_manifest():
    return {
        "schema": "zworkbench-w7-owner-c7-services/v1",
        "managed_services": [
            {"name": "codex-cli-0.139.0-app-server", "kind": "local-runtime", "counted": True},
            {"name": "sqlite-composition-owner", "kind": "local-durable-owner", "counted": True},
        ],
        "excluded_services": [
            {"name": "loopback-fake-provider", "reason": "case-local test-only process"},
            {"name": "host-os", "reason": "excluded by C7 threshold"},
        ],
        "maintained_service_count": 2,
        "provider_and_host_os_counted": False,
    }


def state_evidence(owner, run_id: str, execution) -> dict:
    snapshot = owner.snapshot()
    run = owner.get_run(run_id)
    result_kinds = {item["kind"] for item in run["results"]}
    replay = [item for item in snapshot["replays"] if item["run_id"] == run_id]
    run_metadata = run.get("metadata") or {}
    return {
        "run_id_present": any(item["run_id"] == run_id for item in snapshot["runs"]),
        "run_completed": run.get("status") == "completed",
        "real_owner_database": owner.database.is_file(),
        "owner_schema": snapshot.get("schema"),
        "owner_state_digest": owner.state_digest(),
        "adapter_schema_recorded": run_metadata.get("adapter_schema") == ADAPTER_SCHEMA,
        "thread_id_recorded": execution.thread_id in {item.get("value", {}).get("thread_id") for item in run["results"]},
        "turn_id_recorded": execution.turn_id in {item.get("value", {}).get("turn_id") for item in run["results"]},
        "provider_identity_recorded": any(item.get("provider_identity") == execution.provider_identity for item in replay),
        "recorded_view_present": any(item.get("mode") == "recorded_view" for item in replay),
        "adapter_results_present": {"adapter.initialized", "adapter.thread", "adapter.turn", "semantic"}.issubset(result_kinds),
        "effect_count": len(snapshot["effects"]),
    }


def run_case(case_dir: Path, scenario: str, repeat: int, codex: str) -> dict:
    from zworkbench.codex_adapter import CodexAppServerAdapter
    from zworkbench.composition import CompositionOwner

    case_dir.mkdir(parents=True, exist_ok=False)
    workspace = case_dir / "workspace"
    task_cwd = workspace / "task"
    owner_db = workspace / "composition.sqlite3"
    code_home = workspace / "codex-home"
    adapter_events = case_dir / "codex-adapter-events.jsonl"
    run_id = f"w7-owner-c7-{scenario}-repeat-{repeat:02d}"
    provider = None
    started = time.monotonic()
    result = {
        "schema": SCHEMA,
        "run_id": run_id,
        "scenario": scenario,
        "workspace": str(workspace),
        "owner_database": str(owner_db),
        "code_home": str(code_home),
        "classification": "acceptance/evaluation",
        "real_owner_state_required": True,
    }
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        provider = start_provider(case_dir)
        provider_identity = {
            "provider": provider["provider_id"],
            "model": "fake-model",
            "endpoint": provider["endpoint"],
            "transport": "loopback-only",
        }
        with CompositionOwner(owner_db) as owner:
            with CodexAppServerAdapter(
                owner,
                codex,
                code_home,
                task_cwd,
                model="fake-model",
                model_provider="ollama",
                provider_identity=provider_identity,
                sandbox="read-only",
                approval_policy="never",
                event_log=adapter_events,
            ) as adapter:
                execution = adapter.execute(
                    run_id,
                    "W7_OWNER_C7 Return the exact text fixture-ok and do not call tools.",
                    task_type="c7.owner-backed-turn",
                    metadata={"scenario": scenario, "repeat": repeat},
                    timeout=45,
                )
            evidence = state_evidence(owner, run_id, execution)
            owner_snapshot = owner.snapshot()
            write_json(case_dir / "owner-state-before-operation.json", owner_snapshot)
            checks = {
                **{key: value for key, value in evidence.items() if key.endswith("present") or key.endswith("recorded") or key in {"run_completed", "real_owner_database"}},
                "schema_is_owner_schema": evidence["owner_schema"] == "zworkbench-composition-owner/v1",
                "no_effects_claimed": evidence["effect_count"] == 0,
                "semantic_result_fixture_ok": execution.text == "fixture-ok",
                "provider_is_loopback": execution.provider_identity.get("transport") == "loopback-only" and execution.provider_identity.get("endpoint", "").startswith("http://127.0.0.1:"),
            }
            details = {
                "operation_kind": scenario,
                "thread_id": execution.thread_id,
                "turn_id": execution.turn_id,
                "provider_identity": execution.provider_identity,
                "event_digest": execution.event_digest,
                "environment_digest": execution.environment_digest,
                "raw_event_count": execution.raw_event_count,
                "owner_state_digest_before_operation": owner.state_digest(),
                "real_owner_database": str(owner_db),
            }
            if scenario == "backup_restore":
                backup_dir = workspace / "backup"
                restore_db = workspace / "restored.sqlite3"
                expected_digest = owner.state_digest()
                manifest = owner.backup(backup_dir)
                restore_db.write_bytes(b"intentionally-corrupted-case-local-target")
                corrupted_target_digest = digest(restore_db)
                restored = CompositionOwner.restore(backup_dir, restore_db, replace=True)
                with CompositionOwner(restore_db) as recovered:
                    restored_digest = recovered.state_digest()
                    restored_snapshot = recovered.snapshot()
                shutil.copytree(backup_dir, case_dir / "owner-backup")
                shutil.copy2(restore_db, case_dir / "restored.sqlite3")
                write_json(case_dir / "owner-state-restored.json", restored_snapshot)
                checks.update({
                    "backup_manifest_present": (backup_dir / "manifest.json").is_file(),
                    "backup_database_present": (backup_dir / "composition.sqlite3").is_file(),
                    "backup_state_json_present": (backup_dir / "state.json").is_file(),
                    "backup_integrity_ok": manifest.get("integrity_check", {}).get("ok") is True,
                    "corrupted_target_replaced": digest(restore_db) != corrupted_target_digest,
                    "restore_digest_matches": restored_digest == expected_digest and restored["state_digest"] == expected_digest,
                    "restore_snapshot_matches": restored_snapshot == owner_snapshot,
                })
                details.update({"backup_directory": str(backup_dir), "restore_database": str(restore_db), "restored_state_digest": restored_digest})
            else:
                export_dir = workspace / "export"
                import_dir = workspace / "imported"
                export_dir.mkdir(parents=True, exist_ok=True)
                export_result = owner.export_state(export_dir / "state.json")
                backup_dir = export_dir / "owner-backup"
                owner.backup(backup_dir)
                shutil.copytree(export_dir, import_dir)
                imported_state = json.loads((import_dir / "state.json").read_text(encoding="utf-8"))
                restored_db = import_dir / "restored.sqlite3"
                restored = CompositionOwner.restore(import_dir / "owner-backup", restored_db)
                with CompositionOwner(restored_db) as recovered:
                    imported_digest = recovered.state_digest()
                checks.update({
                    "export_state_present": (export_dir / "state.json").is_file(),
                    "export_digest_matches_owner": export_result["state_digest"] == owner.state_digest(),
                    "independent_import_digest_matches": imported_state["state_digest"] == owner.state_digest(),
                    "independent_backup_restore_matches": restored["state_digest"] == owner.state_digest() == imported_digest,
                })
                details.update({"export_directory": str(export_dir), "import_directory": str(import_dir), "imported_state_digest": imported_digest})
            result.update({"status": "completed", "checks": checks, "operation_details": details, "owner_state_digest": owner.state_digest()})
        if scenario == "exit":
            shutil.rmtree(workspace)
            result["checks"].update({
                "workspace_deleted": not workspace.exists(),
                "owner_database_deleted": not owner_db.exists(),
                "codex_home_deleted": not code_home.exists(),
            })
            result["operation_details"]["external_data_deleted"] = False
            result["operation_details"]["user_data_deleted"] = False
        result["machine_elapsed_seconds"] = round(time.monotonic() - started, 6)
        result["machine_elapsed_source"] = "runner monotonic wall clock; not human operation time"
        result["network_calls"] = 0
        result["loopback_provider_calls_allowed"] = True
        result["real_credentials"] = False
        result["production_data"] = False
        result["service_manifest"] = service_manifest()
        result["evidence"] = {"adapter_event_log": str(adapter_events), "provider_request_log": str(provider["request_log"])}
        result["status"] = "completed" if all(result["checks"].values()) else "failed"
        write_json(case_dir / "operation-result.json", result)
        return result
    except Exception as exc:
        result.update({
            "status": "failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "machine_elapsed_seconds": round(time.monotonic() - started, 6),
            "machine_elapsed_source": "runner monotonic wall clock; not human operation time",
            "network_calls": 0,
            "real_credentials": False,
            "production_data": False,
        })
        write_json(case_dir / "operation-result.json", result)
        return result
    finally:
        if provider is not None:
            stop_process(provider["process"], provider["stderr"])


def verify_case(case_dir: Path, scenario: str, repeat: int) -> dict:
    operation_path = case_dir / "operation-result.json"
    operation = json.loads(operation_path.read_text(encoding="utf-8")) if operation_path.is_file() else {}
    checks = operation.get("checks", {})
    services = operation.get("service_manifest", {})
    case_root = case_dir.resolve()
    workspace = Path(operation.get("workspace", case_dir)).resolve()
    required = {
        "operation_completed": operation.get("status") == "completed",
        "real_owner_state": operation.get("real_owner_state_required") is True and checks.get("real_owner_database") is True,
        "owner_lifecycle_complete": checks.get("run_completed") is True and checks.get("semantic_result_fixture_ok") is True,
        "owner_identity_complete": checks.get("thread_id_recorded") is True and checks.get("turn_id_recorded") is True and checks.get("provider_identity_recorded") is True and checks.get("recorded_view_present") is True,
        "required_owner_adapter_results": checks.get("adapter_results_present") is True,
        "workspace_isolated": case_root in workspace.parents or workspace == case_root,
        "external_network_zero": operation.get("network_calls") == 0 and operation.get("loopback_provider_calls_allowed") is True,
        "real_credentials_false": operation.get("real_credentials") is False,
        "production_data_false": operation.get("production_data") is False,
        "service_count_within_threshold": services.get("maintained_service_count") <= MAX_MAINTAINED_SERVICES and services.get("provider_and_host_os_counted") is False,
    }
    passed = all(required.values()) and all(checks.values())
    return {
        "scenario": scenario,
        "repeat": repeat,
        "status": "pass" if passed else "fail",
        "observed": {
            "machine_elapsed_seconds": operation.get("machine_elapsed_seconds"),
            "owner_state_digest": operation.get("owner_state_digest"),
            "thread_id": operation.get("operation_details", {}).get("thread_id"),
            "turn_id": operation.get("operation_details", {}).get("turn_id"),
            "provider": operation.get("operation_details", {}).get("provider_identity"),
            "checks": checks,
        },
        "checks": required | checks,
        "evidence_dir": str(case_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--codex", default=CODEX_DEFAULT)
    args = parser.parse_args()
    if not args.codex:
        raise SystemExit("codex executable is not installed")
    if args.repeats != REPEATS:
        raise SystemExit(f"owner C7 requires exactly {REPEATS} repeats per scenario")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w7-codex-owner-c7-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for scenario in SCENARIOS:
        for repeat in range(1, REPEATS + 1):
            case_dir = output_dir / "cases" / scenario / f"repeat-{repeat:02d}"
            run_case(case_dir, scenario, repeat, args.codex)
            results.append(verify_case(case_dir, scenario, repeat))
    passed = sum(item["status"] == "pass" for item in results)
    machine_status = "pass" if passed == len(results) else "fail"
    summary = {
        "schema": SCHEMA,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": now(),
        "classification": "acceptance/evaluation",
        "candidate": {"name": "Codex Harness", "version": "codex-cli 0.139.0", "entrypoint": str(Path(args.codex).resolve())},
        "runner": {"version": RUNNER_VERSION, "path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).resolve())},
        "adapter": {"schema": ADAPTER_SCHEMA, "module": str((REPO_ROOT / "src" / "zworkbench" / "codex_adapter.py").resolve())},
        "fixture": {"fake_provider": str(FAKE_PROVIDER), "sha256": digest(FAKE_PROVIDER), "provider_transport": "loopback-only"},
        "scenarios": list(SCENARIOS),
        "repeats_per_scenario": REPEATS,
        "status": "unknown/stop" if machine_status == "pass" else "fail",
        "machine_contract": {"status": machine_status, "cases_passed": passed, "cases_total": len(results), "real_owner_state_required": True},
        "human_timing": {"status": "unknown", "note": "This run does not substitute runner time for a single-operator stopwatch."},
        "license_and_provenance": {"commercial_boundary": "unknown", "redistribution_notice_review": "unknown", "source_to_binary_provenance": "unknown", "reason": "unchanged C7 legal and provenance gates"},
        "exit_boundary": {"external_data_deleted": False, "user_data_deleted": False, "remote_resources_audited": False},
        "checks": {
            "all_machine_cases_pass": machine_status == "pass",
            "all_cases_use_real_owner_state": all(item["checks"].get("real_owner_state") for item in results),
            "all_backup_restore_cases_pass": all(item["status"] == "pass" for item in results if item["scenario"] == "backup_restore"),
            "all_exit_cases_pass": all(item["status"] == "pass" for item in results if item["scenario"] == "exit"),
            "no_external_network": all(item["checks"].get("external_network_zero") for item in results),
            "all_case_workspaces_isolated": all(item["checks"].get("workspace_isolated") for item in results),
            "maintained_services_at_most_three": all(item["checks"].get("service_count_within_threshold") for item in results),
            "missing_human_legal_provenance_evidence_stops": True,
        },
        "cases": results,
        "interpretation": "C7 backup/restore and exit were rerun on real owner state produced by the Codex app-server adapter. This closes the previous nonexistent-state blocker for these machine controls only; human timing, legal/NOTICE review, source-to-binary provenance, real remote-resource exit, and Codex native approval remain outside this run.",
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps({"run_id": run_id, "summary": str(output_dir / "summary.json"), "status": summary["status"], "cases": f"{passed}/{len(results)}"}, ensure_ascii=False, indent=2))
    if summary["status"] != "unknown/stop":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
