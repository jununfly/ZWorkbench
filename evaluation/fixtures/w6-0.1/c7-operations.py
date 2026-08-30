#!/usr/bin/env python3
"""Candidate-independent C7 lifecycle-operation fixture.

This is acceptance infrastructure, not ZWorkbench product code.  It executes
only inside a runner-created temporary workspace and models the operator-facing
parts of install, upgrade, backup/restore and diagnosis.  It deliberately does
not install packages, start daemons, access credentials, or use the network.
Machine wall-clock time is emitted as evidence, but is never presented as a
human operation time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "zworkbench-w6-c7-operations/v1"
FIXTURE_VERSION = "W6-0.1"
VERSIONS = {"initial": "0.1", "current": "0.2"}
MANAGED_SERVICES = ("scheduler", "evidence-ledger")
EXCLUDED_SERVICES = ("provider", "host-os")
REQUIRED_EVENT_TYPES = (
    "operation.started",
    "environment.checked",
    "precondition.prepared",
    "operation.step",
    "verification.completed",
    "operation.completed",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")


def tree_digest(root: Path):
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            entries.append(f"{path.relative_to(root).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def write_version(workspace: Path, version: str, marker: str):
    write_json(workspace / "app" / "version.json", {"schema": "fixture-app-version/v1", "version": version, "marker": marker})


def read_version(workspace: Path):
    return json.loads((workspace / "app" / "version.json").read_text(encoding="utf-8"))


def prepare_initial(workspace: Path, run_id: str):
    workspace.mkdir(parents=True, exist_ok=True)
    write_version(workspace, VERSIONS["initial"], "initial-install")
    write_json(workspace / "config" / "workbench.json", {
        "schema": "fixture-workbench-config/v1",
        "fixture_version": FIXTURE_VERSION,
        "run_id": run_id,
        "provider": "fake-provider-not-started",
    })
    write_json(workspace / "state" / "state.json", {
        "schema": "fixture-workbench-state/v1",
        "run_id": run_id,
        "status": "healthy",
        "counter": 1,
    })


def service_manifest():
    return {
        "schema": "zworkbench-w6-c7-service-manifest/v1",
        "managed_services": [
            {"name": name, "maintenance_required": True, "counted": True}
            for name in MANAGED_SERVICES
        ],
        "excluded_services": [
            {"name": name, "reason": "excluded_by_C7_threshold"}
            for name in EXCLUDED_SERVICES
        ],
        "maintained_service_count": len(MANAGED_SERVICES),
        "provider_and_host_os_counted": False,
        "basis": "reference fixture composition; not candidate-native evidence",
    }


def run_operation(args):
    workspace = args.workspace.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "operation-events.jsonl"
    run_id = args.run_id
    started = time.monotonic()

    def event(event_type, **fields):
        append_jsonl(events_path, {
            "schema": SCHEMA,
            "event_id": f"{run_id}-{len(read_events()) + 1:03d}",
            "run_id": run_id,
            "at": now(),
            "type": event_type,
            **fields,
        })

    def read_events():
        if not events_path.exists():
            return []
        return [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    human_steps = {
        "install": [
            "创建隔离工作区并准备运行时目录",
            "写入最小配置与版本标记",
            "执行健康检查并保存安装 manifest",
        ],
        "upgrade": [
            "确认当前版本与备份目录可用",
            "保存升级前快照并写入新版本",
            "执行 schema/健康检查并确认版本切换",
        ],
        "backup_restore": [
            "生成状态备份并记录内容摘要",
            "模拟状态损坏或升级失败",
            "恢复备份并校验状态摘要与版本",
        ],
        "fault_diagnosis": [
            "读取预制故障的健康状态与错误日志",
            "按 run_id 关联故障原因和最近状态",
            "写出诊断结论与下一步操作",
        ],
    }
    event("operation.started", scenario=args.scenario, workspace=str(workspace), human_timing="not-provided")
    event("environment.checked", network="not-used", real_credentials=False, production_data=False, workspace_isolated=True)
    checks = {}

    if args.scenario == "install":
        workspace.mkdir(parents=True, exist_ok=True)
        event("precondition.prepared", source="clean_workspace")
        write_version(workspace, VERSIONS["initial"], "install")
        write_json(workspace / "config" / "workbench.json", {"schema": "fixture-workbench-config/v1", "fixture_version": FIXTURE_VERSION, "mode": "isolated"})
        write_json(workspace / "state" / "state.json", {"schema": "fixture-workbench-state/v1", "status": "healthy", "counter": 0})
        event("operation.step", step="create_minimal_layout", side_effect_class="reversible")
        event("operation.step", step="write_config_and_version", side_effect_class="reversible")
        checks = {
            "version_marker_present": (workspace / "app" / "version.json").exists(),
            "config_present": (workspace / "config" / "workbench.json").exists(),
            "state_present": (workspace / "state" / "state.json").exists(),
        }
        precondition = {"prepared": False, "reason": "clean_workspace"}
    elif args.scenario == "upgrade":
        prepare_initial(workspace, run_id)
        event("precondition.prepared", source_version=VERSIONS["initial"])
        snapshot = workspace / "backups" / "before-upgrade"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace / "app", snapshot)
        write_version(workspace, VERSIONS["current"], "upgrade")
        event("operation.step", step="snapshot_before_upgrade", snapshot=str(snapshot.relative_to(workspace)), side_effect_class="reversible")
        event("operation.step", step="write_current_version", target_version=VERSIONS["current"], side_effect_class="reversible")
        checks = {
            "source_version_was_initial": json.loads((snapshot / "version.json").read_text(encoding="utf-8"))["version"] == VERSIONS["initial"],
            "current_version_is_upgraded": read_version(workspace)["version"] == VERSIONS["current"],
            "upgrade_snapshot_present": snapshot.exists(),
        }
        precondition = {"prepared": True, "source_version": VERSIONS["initial"]}
    elif args.scenario == "backup_restore":
        prepare_initial(workspace, run_id)
        event("precondition.prepared", state_status="healthy")
        state_path = workspace / "state" / "state.json"
        before_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
        backup_path = workspace / "backups" / "state.json"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, backup_path)
        state_path.write_text(json.dumps({"schema": "fixture-workbench-state/v1", "status": "corrupted", "counter": "unknown"}) + "\n", encoding="utf-8")
        event("operation.step", step="create_backup", backup=str(backup_path.relative_to(workspace)), side_effect_class="reversible")
        event("operation.step", step="inject_corrupted_state", side_effect_class="reversible")
        shutil.copy2(backup_path, state_path)
        after_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
        event("operation.step", step="restore_backup_and_verify", side_effect_class="reversible")
        checks = {
            "backup_present": backup_path.exists(),
            "restored_digest_matches": before_digest == after_digest,
            "restored_state_healthy": json.loads(state_path.read_text(encoding="utf-8"))["status"] == "healthy",
        }
        precondition = {"prepared": True, "state_status": "healthy", "corruption_injected": True}
    elif args.scenario == "fault_diagnosis":
        prepare_initial(workspace, run_id)
        event("precondition.prepared", fault_id="provider-timeout-001")
        log_path = workspace / "logs" / "worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"{run_id} ERROR provider_timeout provider=fake-b attempt=1\n", encoding="utf-8")
        write_json(workspace / "state" / "health.json", {"status": "degraded", "run_id": run_id, "fault_id": "provider-timeout-001"})
        event("operation.step", step="read_health_and_error_log", fault_id="provider-timeout-001", side_effect_class="read-only")
        diagnosis = {
            "schema": "fixture-diagnosis/v1",
            "fault_id": "provider-timeout-001",
            "category": "provider_timeout",
            "run_id": run_id,
            "recommended_action": "retry_or_failover_with_ledger",
        }
        write_json(output_dir / "diagnosis.json", diagnosis)
        event("operation.step", step="write_diagnosis", category=diagnosis["category"], side_effect_class="reversible")
        checks = {
            "fault_log_present": log_path.exists(),
            "fault_id_correlated": diagnosis["fault_id"] in log_path.read_text(encoding="utf-8") or diagnosis["run_id"] in log_path.read_text(encoding="utf-8"),
            "diagnosis_category_present": diagnosis["category"] == "provider_timeout",
            "recommended_action_present": bool(diagnosis["recommended_action"]),
        }
        precondition = {"prepared": True, "fault_id": "provider-timeout-001"}
    else:
        raise ValueError(f"unsupported scenario: {args.scenario}")

    event("verification.completed", checks=checks)
    elapsed = round(time.monotonic() - started, 6)
    operation_ok = all(checks.values())
    result = {
        "schema": SCHEMA,
        "run_id": run_id,
        "scenario": args.scenario,
        "status": "completed" if operation_ok else "failed",
        "machine_elapsed_seconds": elapsed,
        "machine_elapsed_source": "fixture subprocess monotonic wall clock; not human operation time",
        "human_timed": False,
        "human_elapsed_minutes": None,
        "human_timing_status": "unknown",
        "human_timing_source": "not-provided",
        "human_steps": human_steps[args.scenario],
        "human_step_count": len(human_steps[args.scenario]),
        "precondition": precondition,
        "checks": checks,
        "machine_side_effect_scope": "case-local reversible files only",
        "network_calls": 0,
        "real_credentials": False,
        "production_data": False,
        "workspace": str(workspace),
    }
    write_json(output_dir / "service-manifest.json", service_manifest())
    write_json(output_dir / "dependency-manifest.json", {
        "schema": "zworkbench-w6-c7-dependency-manifest/v1",
        "required_runtime": ["python3"],
        "additional_packages": [],
        "operator_expert_required": False,
        "host_os_and_provider": "not counted as maintained services",
    })
    write_json(output_dir / "operation-result.json", result)
    event("operation.completed", status=result["status"], machine_elapsed_seconds=elapsed)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("install", "upgrade", "backup_restore", "fault_diagnosis"), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        result = run_operation(args)
    except Exception as exc:
        print(encode({"status": "failed", "error": f"fixture-error-{type(exc).__name__}"}))
        raise SystemExit(23)
    print(encode({
        "scenario": result["scenario"],
        "status": result["status"],
        "machine_elapsed_seconds": result["machine_elapsed_seconds"],
        "human_timing_status": result["human_timing_status"],
    }))


if __name__ == "__main__":
    main()
