#!/usr/bin/env python3
"""Case-local C7 audit operations for the pinned Codex candidate.

This fixture never installs, upgrades, or removes the user's Codex.  It runs
read-only identity checks against the pinned executable and performs all
backup/restore/export/delete probes below a runner-created workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "zworkbench-w7-codex-c7/v1"
REQUIRED_EVENT_TYPES = (
    "operation.started",
    "environment.checked",
    "precondition.prepared",
    "operation.step",
    "verification.completed",
    "operation.completed",
)
VERSIONS = {"current": "0.139.0", "rollback": "0.139.0"}


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
        handle.flush()


def digest(path: Path):
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hasher = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        hasher.update(str(child.relative_to(path)).encode("utf-8"))
        hasher.update(child.read_bytes())
    return hasher.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(command, cwd: Path, output_dir: Path, name: str, env):
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = None
        timed_out = True
        output = (exc.stdout or "") + (exc.stderr or "")
        (output_dir / f"{name}.txt").write_text(output, encoding="utf-8")
        return {"command": command, "returncode": None, "timed_out": True, "elapsed_seconds": round(time.monotonic() - started, 6)}
    (output_dir / f"{name}.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output_dir / f"{name}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    return {
        "command": command,
        "returncode": completed.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def artifact_record(manifest, key):
    artifact = manifest["artifacts"][key]
    path = Path(artifact["path"])
    exists = path.is_file()
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
    return {
        "key": key,
        "path": str(path),
        "expected_sha256": artifact.get("sha256"),
        "actual_sha256": actual,
        "exists": exists,
        "digest_matches": exists and actual == artifact.get("sha256"),
    }


def service_manifest():
    return {
        "schema": "zworkbench-w7-c7-service-manifest/v1",
        "managed_services": [
            {"name": "codex-cli-0.139.0", "kind": "local-runtime", "counted": True, "maintenance_required": True},
            {"name": "single-composition-adapter", "kind": "external-thin-owner", "counted": True, "maintenance_required": True},
        ],
        "excluded_services": [
            {"name": "host-os", "reason": "excluded_by_C7_threshold"},
            {"name": "node-runtime", "reason": "runtime_dependency_not_daemon"},
            {"name": "fake-provider-and-router", "reason": "case-local_test-only_fixture"},
        ],
        "maintained_service_count": 2,
        "provider_and_host_os_counted": False,
        "basis": "conservative candidate plus one required composition owner; test-only services excluded explicitly",
    }


def dependency_manifest(manifest):
    return {
        "schema": "zworkbench-w7-c7-dependency-manifest/v1",
        "required_runtime": ["node >=16", "@openai/codex 0.139.0"],
        "package_manager_metadata": manifest.get("source", {}).get("package_manager", "pnpm@10.33.0"),
        "additional_packages": [],
        "operator_expert_required": False,
        "host_os_and_provider": "not counted as maintained services",
        "network_required_for_audit": False,
    }


def license_audit(manifest, primary_sources: Path | None):
    package = Path(manifest["artifacts"]["npm_package"]["path"])
    platform = Path(manifest["artifacts"]["platform_package"]["path"])
    package_json = load_json(package) if package.is_file() else {}
    platform_json = load_json(platform) if platform.is_file() else {}
    source_file_exists = bool(primary_sources and primary_sources.is_file())
    return {
        "schema": "zworkbench-w7-c7-license-audit/v1",
        "declared_license": package_json.get("license"),
        "platform_declared_license": platform_json.get("license"),
        "expected_license": "Apache-2.0",
        "package_license_matches": package_json.get("license") == "Apache-2.0",
        "platform_license_matches": platform_json.get("license") == "Apache-2.0",
        "source_primary_findings_path": str(primary_sources) if primary_sources else None,
        "source_primary_findings_present": source_file_exists,
        "commercial_boundary": "unknown",
        "redistribution_notice_review": "unknown",
        "binary_provenance": manifest.get("source", {}).get("binary_build_provenance", "unknown"),
        "source_to_binary_verified": manifest.get("source", {}).get("source_to_binary_verified", False),
        "interpretation": "Package metadata identifies Apache-2.0; commercial, notice, and source-to-binary questions remain explicit audit items.",
    }


def run_operation(args):
    workspace = args.workspace.resolve()
    output_dir = args.output_dir.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "operation-events.jsonl"
    started = time.monotonic()
    sequence = 0

    def event(event_type, **fields):
        nonlocal sequence
        sequence += 1
        append_jsonl(events_path, {
            "schema": SCHEMA,
            "event_id": f"{args.run_id}:event:{sequence:03d}",
            "run_id": args.run_id,
            "at": now(),
            "type": event_type,
            **fields,
        })

    manifest = load_json(args.candidate_manifest)
    case_home = workspace / "codex-home"
    case_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(case_home)
    env["CODEX_CI"] = "1"
    codex = str(Path(args.codex).resolve())
    event("operation.started", scenario=args.scenario, workspace=str(workspace), human_timing="not-provided")
    event("environment.checked", network="not-used", real_credentials=False, production_data=False, workspace_isolated=True, codex_home=str(case_home))
    checks = {}
    operation_details = {}

    artifacts = [artifact_record(manifest, key) for key in ("wrapper", "npm_package", "platform_package", "vendor_binary")]
    version_result = run_command([codex, "--version"], workspace, output_dir, "codex-version", env)
    help_result = run_command([codex, "app-server", "--help"], workspace, output_dir, "codex-app-server-help", env)
    package_json = load_json(Path(manifest["artifacts"]["npm_package"]["path"]))
    license_record = license_audit(manifest, args.primary_sources)
    write_json(output_dir / "license-audit.json", license_record)
    write_json(output_dir / "service-manifest.json", service_manifest())
    write_json(output_dir / "dependency-manifest.json", dependency_manifest(manifest))
    event("precondition.prepared", candidate_version=manifest["runtime"]["cli_version_observed"], release=manifest["source"]["release_tag"])
    event("operation.step", step="verify_pinned_artifacts", artifact_count=len(artifacts), side_effect_class="read-only")
    event("operation.step", step="run_version_and_app_server_help", side_effect_class="read-only")

    checks.update({
        "release_pin_present": manifest.get("source", {}).get("release_tag") == "rust-v0.139.0" and bool(manifest.get("source", {}).get("resolved_commit")),
        "version_check_pass": version_result["returncode"] == 0 and "0.139.0" in version_result.get("stdout", ""),
        "app_server_help_pass": help_result["returncode"] == 0 and "generate-json-schema" in help_result.get("stdout", ""),
        "artifact_digests_match": all(item["digest_matches"] for item in artifacts),
        "package_version_matches": package_json.get("version") == "0.139.0",
        "license_declared_and_matches": license_record["package_license_matches"] and license_record["platform_license_matches"],
    })

    if args.scenario == "identity":
        operation_details = {"operation_kind": "read-only-candidate-identity", "install_executed": False, "upgrade_executed": False}
    elif args.scenario == "install":
        runbook = {
            "candidate": "Codex Harness",
            "release": manifest["source"]["release_tag"],
            "install_command": "npm install -g @openai/codex@0.139.0",
            "network_install_executed": False,
            "global_install_executed": False,
            "reason": "C7 fixture cannot mutate the operator's global installation; only preflight identity was exercised.",
        }
        write_json(output_dir / "install-runbook.json", runbook)
        event("operation.step", step="record_install_runbook_without_mutation", side_effect_class="read-only")
        checks.update({"install_preflight_only": True, "global_install_not_executed": not runbook["global_install_executed"], "network_install_not_executed": not runbook["network_install_executed"]})
        operation_details = {"operation_kind": "install-preflight", "install_executed": False, "candidate_install_status": "not_exercised"}
    elif args.scenario == "upgrade":
        snapshot = workspace / "upgrade-snapshot"
        snapshot.mkdir(parents=True, exist_ok=True)
        write_json(snapshot / "candidate-before.json", {"release": manifest["source"]["release_tag"], "version": "0.139.0", "digest": digest(Path(manifest["artifacts"]["vendor_binary"]["path"]))})
        write_json(snapshot / "rollback-target.json", manifest["rollback_target"])
        write_json(output_dir / "upgrade-plan.json", {"dry_run": True, "upgrade_executed": False, "rollback_exercised": False, "rollback_target": manifest["rollback_target"]})
        event("operation.step", step="snapshot_candidate_identity", side_effect_class="reversible")
        event("operation.step", step="record_upgrade_and_rollback_plan_without_mutation", side_effect_class="read-only")
        checks.update({"upgrade_dry_run": True, "upgrade_not_executed": True, "rollback_target_present": bool(manifest.get("rollback_target", {}).get("identity")), "rollback_not_exercised": True})
        operation_details = {"operation_kind": "upgrade-rollback-dry-run", "upgrade_executed": False, "rollback_exercised": False, "candidate_upgrade_status": "not_exercised"}
    elif args.scenario == "backup_restore":
        state = workspace / "composition-state.json"
        backup = workspace / "backups" / "composition-state.json"
        payload = {"schema": "zworkbench-w7-c7-composition-state/v1", "run_id": args.run_id, "c2_c6_identity": {"codex_version": "0.139.0", "provider_router": "loopback-only", "replay_schema": "zworkbench-w7-codex-c56/v1"}, "status": "healthy"}
        write_json(state, payload)
        before_digest = digest(state)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state, backup)
        state.write_text(encode({**payload, "status": "corrupted"}) + "\n", encoding="utf-8")
        event("operation.step", step="create_case_local_backup", backup=str(backup.relative_to(workspace)), side_effect_class="reversible")
        event("operation.step", step="inject_corrupted_composition_state", side_effect_class="reversible")
        shutil.copy2(backup, state)
        after_digest = digest(state)
        event("operation.step", step="restore_backup_and_verify_identity", side_effect_class="reversible")
        checks.update({"backup_present": backup.exists(), "restored_digest_matches": before_digest == after_digest, "restored_state_healthy": load_json(state)["status"] == "healthy", "c2_c6_identity_present": "c2_c6_identity" in load_json(state)})
        operation_details = {"operation_kind": "case-local-composition-backup-restore", "candidate_data_touched": False, "external_data_touched": False}
    elif args.scenario == "fault_diagnosis":
        fault_id = "w7-c7-build-provenance-unknown"
        fault = {"fault_id": fault_id, "run_id": args.run_id, "category": "candidate_provenance_unknown", "severity": "warning", "evidence": {"source_to_binary_verified": manifest["source"].get("source_to_binary_verified", False), "binary_build_provenance": manifest["source"].get("binary_build_provenance", "unknown")}}
        write_json(output_dir / "fault.json", fault)
        diagnosis = {"schema": "zworkbench-w7-c7-diagnosis/v1", "fault_id": fault_id, "run_id": args.run_id, "category": "candidate_provenance_unknown", "recommended_action": "retain release-level identity; do not claim reproducible source build; repeat audit on upgrade"}
        write_json(output_dir / "diagnosis.json", diagnosis)
        event("operation.step", step="read_provenance_fault_and_correlate_run", fault_id=fault_id, side_effect_class="read-only")
        event("operation.step", step="write_bounded_diagnosis", category=diagnosis["category"], side_effect_class="reversible")
        checks.update({"fault_id_correlated": diagnosis["fault_id"] == fault_id and diagnosis["run_id"] == args.run_id, "diagnosis_category_present": bool(diagnosis["category"]), "recommended_action_present": bool(diagnosis["recommended_action"]), "unknown_not_silently_promoted": manifest["source"].get("source_to_binary_verified", False) is False})
        operation_details = {"operation_kind": "predefined-fault-diagnosis", "fault_id": fault_id, "expert_required": False}
    elif args.scenario == "exit":
        export = workspace / "export"
        imported = workspace / "imported"
        export.mkdir(parents=True, exist_ok=True)
        bundle = {"schema": "zworkbench-w7-c7-exit-bundle/v1", "candidate": "Codex Harness", "release": manifest["source"]["release_tag"], "resolved_commit": manifest["source"]["resolved_commit"], "license": license_record["declared_license"], "c2_c6_identity": {"codex_version": "0.139.0", "replay_schema": "zworkbench-w7-codex-c56/v1"}}
        write_json(export / "manifest.json", bundle)
        write_json(export / "service-manifest.json", service_manifest())
        write_json(export / "dependency-manifest.json", dependency_manifest(manifest))
        shutil.copytree(export, imported)
        imported_ok = all(load_json(path) for path in imported.glob("*.json"))
        event("operation.step", step="export_candidate_and_composition_metadata", export=str(export.relative_to(workspace)), side_effect_class="reversible")
        event("operation.step", step="independent_reimport_validation", imported=str(imported.relative_to(workspace)), side_effect_class="reversible")
        shutil.rmtree(export)
        shutil.rmtree(imported)
        shutil.rmtree(case_home)
        residue = [str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.exists()]
        event("operation.step", step="delete_export_and_verify_no_residue", side_effect_class="reversible")
        checks.update({"export_manifest_created": True, "independent_reimport_valid": imported_ok, "export_deleted": not export.exists(), "import_deleted": not imported.exists(), "exit_residue_zero": residue == []})
        operation_details = {"operation_kind": "case-local-export-reimport-delete", "external_data_deleted": False, "user_data_deleted": False}
    else:
        raise ValueError(f"unsupported scenario: {args.scenario}")

    event("verification.completed", checks=checks)
    elapsed = round(time.monotonic() - started, 6)
    operation_ok = all(checks.values())
    result = {
        "schema": SCHEMA,
        "run_id": args.run_id,
        "scenario": args.scenario,
        "status": "completed" if operation_ok else "failed",
        "machine_elapsed_seconds": elapsed,
        "machine_elapsed_source": "fixture subprocess monotonic wall clock; not human operation time",
        "human_timed": False,
        "human_elapsed_minutes": None,
        "human_timing_status": "unknown",
        "human_timing_source": "not-provided",
        "human_steps": {
            "identity": ["确认固定版本与 digest", "执行 --version", "执行 app-server --help"],
            "install": ["按 runbook 准备安装环境", "安装固定版本", "确认版本与入口"],
            "upgrade": ["备份当前 identity/config", "执行升级", "验证兼容并保留回滚"],
            "backup_restore": ["备份 composition ledger", "模拟损坏", "恢复并核对 C2-C6 identity"],
            "fault_diagnosis": ["读取 fault/run 关联", "分类故障", "执行 bounded next action"],
            "exit": ["导出 metadata/ledger", "独立读取导出物", "删除并确认无残留"],
        }[args.scenario],
        "human_step_count": len({
            "identity": [1, 2, 3], "install": [1, 2, 3], "upgrade": [1, 2, 3], "backup_restore": [1, 2, 3], "fault_diagnosis": [1, 2, 3], "exit": [1, 2, 3]
        }[args.scenario]),
        "operation_details": operation_details,
        "checks": checks,
        "machine_side_effect_scope": "case-local reversible files only",
        "network_calls": 0,
        "real_credentials": False,
        "production_data": False,
        "workspace": str(workspace),
        "codex_home": str(case_home),
    }
    write_json(output_dir / "operation-result.json", result)
    event("operation.completed", status=result["status"], machine_elapsed_seconds=elapsed)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("identity", "install", "upgrade", "backup_restore", "fault_diagnosis", "exit"), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--primary-sources", type=Path)
    args = parser.parse_args()
    try:
        result = run_operation(args)
    except Exception as exc:
        print(encode({"status": "failed", "error": f"fixture-error-{type(exc).__name__}", "detail": repr(exc)}))
        raise SystemExit(23)
    print(encode({"scenario": result["scenario"], "status": result["status"], "machine_elapsed_seconds": result["machine_elapsed_seconds"], "human_timing_status": result["human_timing_status"]}))


if __name__ == "__main__":
    main()
