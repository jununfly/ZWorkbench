#!/usr/bin/env python3
"""Run the isolated runtime seam probe for dsh-config-migrate.

The probe executes the pinned dynamic host/client function bodies in a Node
process with an adapter-owned facade. The real ZWorkbench CompositionOwner is
used by this Python runner for durable request/result correlation. Plugin
writes are denied before touching disk, and E3-E6 are not evaluated here.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-config-migrate-adapter" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
NODE_PROBE = FIXTURE_ROOT / "runtime-seam-host.mjs"
SCHEMA = "zworkbench-w8-deepseek-config-migrate-runtime-seam/v1"
RUN_ID = "w8-dsh-config-migrate-runtime-seam-repeat-01"
EXPECTED_PLUGIN_COMMIT = "24aa64188386181bdaf21f4b46fea02bddf77e71"
SCRIPT_NAMES = ("CRED_SCRIPT", "BIN_SCRIPT", "LINK_SCRIPT")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from evaluation.runner.run_deepseek_config_migrate_adapter import git_head, git_show, read_json, sha256_bytes, write_json  # noqa: E402
from zworkbench import CompositionOwner  # noqa: E402


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def prepare_case(case_dir: Path) -> dict[str, Path]:
    case_dir.mkdir(parents=True, exist_ok=False)
    home = case_dir / "dsh-home"
    workspace = case_dir / "workspace"
    state = case_dir / "state"
    inputs = case_dir / "inputs"
    for path in (home, workspace, state, inputs):
        path.mkdir(parents=True)
    (home / "profiles" / "headless").mkdir(parents=True)
    (home / "external-plugins" / "demo").mkdir(parents=True)
    (home / ".agent-presets").mkdir(parents=True)
    (home / "settings.yaml").write_text("profile: headless\ntelemetry: disabled\n", encoding="utf-8")
    (home / ".credentials.yaml").write_text("provider: fixture-only\ncredential: redacted\n", encoding="utf-8")
    (home / ".anonymous-user-id").write_text("fixture-user\n", encoding="utf-8")
    (home / "profiles" / "headless" / "package.json").write_text(
        json.dumps({"name": "dsh-profile-headless", "dependencies": {"dsh-config-migrate": "file:../external-plugins/dsh-config-migrate"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (home / "external-plugins" / "demo" / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": {"fixture-dependency": "1.0.0"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (home / ".agent-presets" / "default.txt").write_text("fixture preset\n", encoding="utf-8")
    (workspace / "import-bundle.json").write_text(
        json.dumps({
            "format": "dsh-config-migration",
            "version": 3,
            "files": {
                "settings.yaml": {"encoding": "utf8", "content": "profile: changed-by-fixture\n"},
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "case_root": case_dir,
        "home": home,
        "workspace": workspace,
        "database": state / "composition.sqlite3",
        "inputs": inputs,
    }


def generated_script_hashes(source: str) -> list[str]:
    """Recover hashes for the three pinned scripts without executing source."""

    hashes: list[str] = []
    for name in SCRIPT_NAMES:
        match = __import__("re").search(
            rf"const {name}\s*=\s*\[\n(.*?)\n\s*\]\.join\('\\n'\)",
            source,
            __import__("re").DOTALL,
        )
        if not match:
            continue
        lines: list[str] = []
        for literal in __import__("re").findall(r"^\s*('(?:\\.|[^'])*')\s*,?\s*$", match.group(1), __import__("re").MULTILINE):
            lines.append(ast.literal_eval(literal))
        hashes.append(sha256_bytes("\n".join(lines).encode("utf-8")))
    return hashes


def run_node_probe(paths: dict[str, Path], host_path: Path, client_path: Path, allowed_script_hashes: list[str]) -> dict[str, Any]:
    node = os.environ.get("NODE_BINARY") or shutil.which("node") or "node"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(paths["case_root"]),
        "DSH_HOME": str(paths["home"]),
        "NO_PROXY": "*",
        "no_proxy": "*",
        "DSH_TELEMETRY_DISABLED": "1",
    }
    command = [
        node,
        str(NODE_PROBE),
        f"--case-root={paths['case_root']}",
        f"--host={host_path}",
        f"--client={client_path}",
        f"--home={paths['home']}",
        f"--workspace={paths['workspace']}",
        f"--allowed-scripts-json={json.dumps(allowed_script_hashes, separators=(',', ':'))}",
    ]
    completed = subprocess.run(
        command,
        cwd=paths["case_root"],
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    (paths["case_root"] / "node-probe.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (paths["case_root"] / "node-probe.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    parsed = None
    parse_error = None
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        parse_error = str(error)
    return {
        "command": command,
        "returncode": completed.returncode,
        "timed_out": False,
        "stdout_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(completed.stderr.encode("utf-8")),
        "parsed": parsed,
        "parse_error": parse_error,
    }


def record_owner_observation(paths: dict[str, Path], runtime: dict[str, Any]) -> dict[str, Any]:
    runtime_data = runtime.get("parsed") if isinstance(runtime.get("parsed"), dict) else {}
    operations = runtime_data.get("operations") if isinstance(runtime_data.get("operations"), list) else []
    with CompositionOwner(paths["database"]) as owner:
        owner.create_run(
            RUN_ID,
            "dynamic_plugin_runtime_seam",
            {"plugin": "dsh-config-migrate", "mode": "case-local"},
            {
                "adapter_schema": SCHEMA,
                "plugin_commit": EXPECTED_PLUGIN_COMMIT,
                "provider": {"provider": "fixture-loopback", "model": "fixture-model", "endpoint": "http://127.0.0.1:11434"},
            },
        )
        owner.start_run(RUN_ID)
        if runtime.get("returncode") != 0 or not isinstance(runtime.get("parsed"), dict):
            owner.safe_stop_run(RUN_ID, "runtime seam probe failed before owner correlation")
            snapshot = owner.snapshot()
            return {
                "run": owner.get_run(RUN_ID),
                "snapshot": snapshot,
                "checks": {
                    "run_completed": False,
                    "all_operation_request_ids_recorded": False,
                    "owner_effect_count_zero": True,
                    "owner_events_bound_to_run": all(item.get("run_id") == RUN_ID for item in snapshot.get("events", [])),
                    "owner_results_bound_to_run": True,
                },
            }
        for operation in operations:
            request_id = operation.get("request_id")
            owner.record_result(
                RUN_ID,
                f"adapter.dynamic_plugin.{operation.get('kind', 'unknown')}",
                {
                    "request_id": request_id,
                    "operation": operation.get("operation"),
                    "status": operation.get("status"),
                    "error_code": (operation.get("error") or {}).get("code"),
                    "plugin": "dsh-config-migrate",
                    "external_effects": 0,
                },
                request_id,
            )
        owner.complete_run(
            RUN_ID,
            {
                "status": "runtime-seam-verified",
                "plugin": "dsh-config-migrate",
                "external_effects": 0,
                "provider_requests": 0,
            },
        )
        snapshot = owner.snapshot()
        run = owner.get_run(RUN_ID)
        result_ids = {item.get("source_id") for item in run.get("results", [])}
        operation_ids = {item.get("request_id") for item in operations}
        return {
            "run": run,
            "snapshot": snapshot,
            "checks": {
                "run_completed": run.get("status") == "completed",
                "all_operation_request_ids_recorded": operation_ids.issubset(result_ids),
                "owner_effect_count_zero": len(run.get("effects", [])) == 0,
                "owner_events_bound_to_run": all(item.get("run_id") == RUN_ID for item in snapshot.get("events", [])),
                "owner_results_bound_to_run": all(item.get("run_id") == RUN_ID for item in snapshot.get("results", [])),
            },
        }


def verify(paths: dict[str, Path], package: dict[str, Any], runtime: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
    data = runtime.get("parsed") if isinstance(runtime.get("parsed"), dict) else {}
    operations = data.get("operations") if isinstance(data.get("operations"), list) else []
    by_id = {item.get("request_id"): item for item in operations}
    registrations = data.get("registrations") if isinstance(data.get("registrations"), dict) else {}
    subprocess_data = data.get("subprocess") if isinstance(data.get("subprocess"), dict) else {}
    write_attempts = data.get("write_attempts") if isinstance(data.get("write_attempts"), list) else []
    paths_data = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    checks = {
        "node_probe_completed": runtime.get("returncode") == 0 and isinstance(runtime.get("parsed"), dict),
        "plugin_commit_pinned": git_head(Path(package["source_dir"])) == EXPECTED_PLUGIN_COMMIT,
        "host_client_runtime_contract": data.get("plugin_contract") == "dsh.plugin.host/client",
        "status_rpc_completed": by_id.get("rpc-status-1", {}).get("status") == "completed",
        "export_write_denied": by_id.get("rpc-export-deny-1", {}).get("status") == "denied" and (by_id.get("rpc-export-deny-1", {}).get("error") or {}).get("code") == "ADAPTER_WRITE_DENY",
        "import_path_escape_denied": by_id.get("rpc-import-escape-1", {}).get("status") == "denied" and (by_id.get("rpc-import-escape-1", {}).get("error") or {}).get("code") == "ADAPTER_PATH_DENY",
        "import_write_denied": by_id.get("rpc-import-write-deny-1", {}).get("status") == "completed" and any("备份失败" in item for item in (by_id.get("rpc-import-write-deny-1", {}).get("value") or {}).get("skipped", [])),
        "tool_write_denied": by_id.get("tool-export-deny-1", {}).get("status") == "denied" and (by_id.get("tool-export-deny-1", {}).get("error") or {}).get("code") == "ADAPTER_WRITE_DENY",
        "unknown_rpc_denied": by_id.get("rpc-unknown-1", {}).get("status") == "denied" and (by_id.get("rpc-unknown-1", {}).get("error") or {}).get("code") == "ADAPTER_UNKNOWN_RPC",
        "write_attempts_all_denied": bool(write_attempts) and all(item.get("decision") == "deny" for item in write_attempts),
        "plugin_full_access_did_not_widen": bool([item for item in write_attempts if item.get("requested_policy")]) and all(item.get("requested_policy", {}).get("mode") == "danger-full-access" and item.get("effective_policy") == "adapter-controlled-deny" for item in write_attempts if item.get("requested_policy")),
        "subprocess_allowlist_used": int(subprocess_data.get("accepted_count", 0)) >= 1 and all(item.get("decision") == "allow" and item.get("source_hash_allowlisted") is True and item.get("argv", [])[:2] == ["node", "-e"] and inside(paths["case_root"], Path(item.get("cwd", "/"))) for item in subprocess_data.get("requests", []) if item.get("decision") == "allow"),
        "subprocess_negative_probe_denied": (subprocess_data.get("negative_probe") or {}).get("code") == "ADAPTER_SUBPROCESS_DENY" and int(subprocess_data.get("denied_count", 0)) >= 1,
        "registrations_created": all(int(registrations.get("before_dispose", {}).get(key, 0)) > 0 for key in ("rpc", "tools", "ui", "styles")),
        "registrations_disposed": registrations.get("after_dispose") == {"rpc": 0, "tools": 0, "ui": 0, "styles": 0},
        "migration_state_separate_from_owner": paths_data.get("migration_state") != str(paths["database"]) and inside(paths["case_root"], Path(paths_data.get("migration_state", paths["case_root"]))),
        "case_paths_inside_case_root": all(inside(paths["case_root"], path) for path in paths.values()),
        "node_reported_paths_inside_case_root": all(inside(paths["case_root"], Path(value)) for value in paths_data.values() if isinstance(value, str)),
        "no_external_effects": all(item.get("value", {}).get("external_effects", 0) == 0 for item in owner["run"].get("results", []) if item.get("kind", "").startswith("adapter.dynamic_plugin.")),
        **owner["checks"],
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observed": {
            "operation_count": len(operations),
            "operation_statuses": {key: value.get("status") for key, value in by_id.items()},
            "write_attempt_count": len(write_attempts),
            "subprocess_request_count": len(subprocess_data.get("requests", [])),
            "registrations": registrations,
            "owner_run_status": owner["run"].get("status"),
            "owner_result_count": len(owner["run"].get("results", [])),
            "owner_event_count": len(owner["snapshot"].get("events", [])),
            "owner_database": str(paths["database"]),
            "migration_state": paths_data.get("migration_state"),
        },
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    bundle_root = args.bundle_root.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("runtime seam output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    plugin = manifest["plugin"]
    source_dir = (bundle_root / plugin["source_dir"]).resolve()
    host_source = git_show(source_dir, plugin["commit"], plugin["host_entry"]) or ""
    client_source = git_show(source_dir, plugin["commit"], plugin["client_entry"]) or ""
    allowed_script_hashes = generated_script_hashes(host_source)
    package = {
        "source_dir": str(source_dir),
        "expected_commit": plugin["commit"],
        "actual_commit": git_head(source_dir),
        "package": plugin["package"],
        "version": plugin["version"],
        "host_sha256": sha256_bytes(host_source.encode("utf-8")),
        "client_sha256": sha256_bytes(client_source.encode("utf-8")),
    }
    case_dir = output / "cases" / "runtime-seam" / "repeat-01"
    paths = prepare_case(case_dir)
    copied_host = paths["inputs"] / "host.js"
    copied_client = paths["inputs"] / "client.js"
    copied_host.write_text(host_source, encoding="utf-8")
    copied_client.write_text(client_source, encoding="utf-8")
    runtime = run_node_probe(paths, copied_host, copied_client, allowed_script_hashes)
    owner = record_owner_observation(paths, runtime)
    result = verify(paths, package, runtime, owner)
    summary = {
        "schema": SCHEMA,
        "status": result["status"],
        "classification": manifest["classification"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_root),
        "output": str(output),
        "plugin": package,
        "runtime_probe": runtime,
        "owner_observation": {
            "run": owner["run"],
            "snapshot": owner["snapshot"],
            "checks": owner["checks"],
        },
        "observed": result["observed"],
        "checks": result["checks"],
        "e3_e6_reopen": {
            "status": "eligible-for-independent-reopen" if result["status"] == "pass" else "blocked-by-runtime-seam",
            "executed_by_this_runner": False,
            "reason": "The runtime seam is a prerequisite; E3-E6 require a separate plugin-aware evidence run.",
        },
        "non_claims": [
            "This is an evaluation-only runtime seam result, not ZWorkbench product integration approval.",
            "All plugin writes were denied; successful real configuration migration was not evaluated.",
            "The probe does not prove host-level OS sandbox inheritance or arbitrary future subprocess safety.",
            "E3-E6 remain unopened until this seam is reviewed and the same gates are run with independent evidence.",
        ],
        "next_action": "If Human accepts the runtime seam boundary, reopen E3-E6 with a new plugin-aware adapter runner; do not inherit Codex or standard-bundle evidence.",
    }
    write_json(output / "runtime-manifest.json", {"schema": SCHEMA, "plugin": plugin, "probe": str(NODE_PROBE), "policy": manifest["adapter"]["capability_facade"], "allowed_script_hashes": allowed_script_hashes})
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True, help="isolated root containing the pinned plugin checkout")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    summary = build_summary(args)
    print(json.dumps({
        "status": summary["status"],
        "output": summary["output"],
        "runtime_seam": "pass" if summary["status"] == "pass" else "fail",
        "E3-E6": summary["e3_e6_reopen"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
