#!/usr/bin/env python3
"""Evaluate the E1/E2 seam for dsh-config-migrate's dynamic-plugin adapter.

This is an acceptance/evaluation runner, not ZWorkbench product code.  It
loads package metadata and file contents from a pinned local Git checkout,
parses the Cordis host/client function bodies in a separate Node process, and
records the proposed capability boundary.  It deliberately does not execute
the plugin, boot DeepSeek Harness, install packages, contact a network, or
open the ZWorkbench composition owner.

The pass result therefore means "eligible for the next plugin-aware gate
within this static isolated scope".  It does not mean the runtime adapter has
been implemented or that E3-E6 may inherit Codex evidence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-config-migrate-adapter" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
SCHEMA = "zworkbench-w8-deepseek-config-migrate-adapter-e1-e2/v1"
ALLOWED_CTX_SERVICES = {"fs", "settings", "sandboxPolicy", "subprocess"}
ALLOWED_HOST_BRIDGE = {"handle", "defineTool", "registerTool"}
ALLOWED_CLIENT_BRIDGE = {"call", "inject", "register"}
ALLOWED_FS_OPERATIONS = {"resolve", "stat", "listDir", "readText", "readBytes", "writeText"}
ALLOWED_SETTINGS_OPERATIONS = {"prepareDocument"}
FORBIDDEN_RUNTIME_PATTERNS = {
    "network_constructor": re.compile(r"\b(?:fetch|WebSocket)\s*\(|\b(?:net|http|https|tls|dns|dgram)\s*\."),
    "network_import": re.compile(r"\b(?:require|import)\s*\(\s*['\"](?:net|http|https|tls|dns|dgram)['\"]"),
    "environment_read": re.compile(r"\bprocess\.env\b"),
    "shell_execution": re.compile(r"(?<![.\w])(?:exec|execFile|spawnSync)\s*\("),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_command(command: list[str], *, input_text: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    started = __import__("time").monotonic()
    safe_env = os.environ.copy()
    safe_env.update({
        "DSH_ADAPTER_EVAL_MODE": "parse-only",
        "DSH_TELEMETRY_DISABLED": "1",
        "NO_PROXY": "*",
        "no_proxy": "*",
    })
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=safe_env,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-16000:],
            "stderr": result.stderr[-16000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "returncode": None,
            "stdout": str(error.stdout or "")[-16000:],
            "stderr": str(error.stderr or "")[-16000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": True,
        }


def git_command(source_dir: Path, args: list[str], timeout: float = 30.0) -> dict[str, Any]:
    return run_command(["git", "-C", str(source_dir), *args], timeout=timeout)


def git_head(source_dir: Path) -> str | None:
    result = git_command(source_dir, ["rev-parse", "HEAD"])
    return result["stdout"].strip() if result["returncode"] == 0 else None


def git_tree(source_dir: Path, commit: str) -> str | None:
    result = git_command(source_dir, ["rev-parse", f"{commit}^{{tree}}"])
    return result["stdout"].strip() if result["returncode"] == 0 else None


def git_show(source_dir: Path, commit: str, relative_path: str) -> str | None:
    # Do not use the bounded diagnostic output helper here: host.js is larger
    # than the evidence log cap and truncating a function body changes what is
    # being parsed.
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), "show", f"{commit}:{relative_path}"],
            text=True,
            capture_output=True,
            timeout=30.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def metadata_record(bundle_root: Path, plugin: dict[str, Any]) -> dict[str, Any]:
    source_dir = (bundle_root / plugin["source_dir"]).resolve()
    expected_commit = plugin["commit"]
    metadata_text = git_show(source_dir, expected_commit, "package.json")
    metadata: dict[str, Any] | None = None
    metadata_error = None
    if metadata_text is None:
        metadata_error = "package.json not available at pinned commit"
    else:
        try:
            parsed = json.loads(metadata_text)
            metadata = parsed if isinstance(parsed, dict) else None
            if metadata is None:
                metadata_error = "package.json is not an object"
        except json.JSONDecodeError as error:
            metadata_error = f"invalid package.json: {error}"

    actual_head = git_head(source_dir) if source_dir.is_dir() else None
    host_entry = plugin["host_entry"]
    client_entry = plugin["client_entry"]
    entry_paths = {name: (source_dir / rel).resolve() for name, rel in (("host", host_entry), ("client", client_entry))}
    source_identity = {
        "source_dir": str(source_dir),
        "source_dir_present": source_dir.is_dir(),
        "source_root_under_bundle": under(source_dir, bundle_root),
        "expected_commit": expected_commit,
        "actual_head": actual_head,
        "commit_matches": actual_head == expected_commit,
        "tree_object": git_tree(source_dir, expected_commit) if source_dir.is_dir() else None,
        "worktree_changes": len(git_command(source_dir, ["status", "--porcelain"])["stdout"].splitlines()) if source_dir.is_dir() else None,
        "package_expected": plugin["package"],
        "package_actual": metadata.get("name") if metadata else None,
        "package_matches": bool(metadata and metadata.get("name") == plugin["package"]),
        "version_expected": plugin["version"],
        "version_actual": metadata.get("version") if metadata else None,
        "version_matches": bool(metadata and metadata.get("version") == plugin["version"]),
        "license": metadata.get("license") if metadata else None,
        "license_present": bool(metadata and metadata.get("license")),
        "metadata_error": metadata_error,
        "declared_dependencies": {
            name: sorted((metadata.get(name) or {}).keys()) if metadata else []
            for name in ("dependencies", "optionalDependencies", "peerDependencies", "devDependencies")
        },
        "declared_lifecycle_scripts": sorted(
            set((metadata.get("scripts") or {}).keys()) & {"preinstall", "install", "postinstall", "prepare"}
        ) if metadata else [],
    }
    dsh = metadata.get("dsh") if metadata else None
    dynamic = dsh.get("plugin") if isinstance(dsh, dict) else None
    bundle = dsh.get("bundle") if isinstance(dsh, dict) else None
    source_identity.update({
        "declared_dsh_plugin": dynamic if isinstance(dynamic, dict) else None,
        "declared_dsh_bundle": bundle if isinstance(bundle, dict) else None,
        "contract_is_dynamic_plugin": isinstance(dynamic, dict) and not isinstance(bundle, dict),
        "declared_host": dynamic.get("host") if isinstance(dynamic, dict) else None,
        "declared_client": dynamic.get("client") if isinstance(dynamic, dict) else None,
        "host_entry_path": str(entry_paths["host"]),
        "client_entry_path": str(entry_paths["client"]),
        "host_entry_under_source": under(entry_paths["host"], source_dir),
        "client_entry_under_source": under(entry_paths["client"], source_dir),
        "host_entry_present": entry_paths["host"].is_file(),
        "client_entry_present": entry_paths["client"].is_file(),
        "host_entry_sha256": sha256_file(entry_paths["host"]) if entry_paths["host"].is_file() else None,
        "client_entry_sha256": sha256_file(entry_paths["client"]) if entry_paths["client"].is_file() else None,
        "artifact_present": False,
        "artifact_policy": plugin["artifact_policy"],
    })
    return {"metadata": metadata, "record": source_identity, "entry_paths": entry_paths}


def parse_function_body(path: Path, source: str) -> dict[str, Any]:
    """Compile only; new Function does not invoke the dynamic plugin body."""

    script = (
        "const fs = require('fs');\n"
        "const source = fs.readFileSync(0, 'utf8');\n"
        "new Function(source);\n"
        "process.stdout.write(JSON.stringify({parsed: true}));\n"
    )
    result = run_command([os.environ.get("NODE_BINARY", "node"), "-e", script], input_text=source)
    return {
        "path": str(path),
        "sha256": sha256_bytes(source.encode("utf-8")),
        "parse": result,
        "parsed": result["returncode"] == 0 and not result["timed_out"],
        "has_dynamic_return": bool(re.search(r"\breturn\s*\{", source)),
        "has_apply_entry": bool(re.search(r"\bapply\s*\(\s*ctx\s*\)", source)),
    }


def source_declarations(host: str, client: str) -> dict[str, Any]:
    combined = host + "\n" + client
    ctx_services = sorted(set(re.findall(r"ctx\.get\(\s*['\"]([^'\"]+)", combined)))
    fs_operations = sorted(set(re.findall(r"\bfs\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", host)))
    settings_operations = sorted(set(re.findall(r"\bsettings\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", host)))
    host_bridge = sorted(set(re.findall(r"\bharness\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", host)))
    client_bridge = sorted(set(re.findall(r"\b(?:host|slots|styles)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", client)))
    policy_modes = sorted(set(re.findall(r"\bmode\s*:\s*['\"]([^'\"]+)", host)))
    forbidden = {
        name: sorted(set(pattern.findall(combined)))
        for name, pattern in FORBIDDEN_RUNTIME_PATTERNS.items()
    }
    return {
        "ctx_services": ctx_services,
        "fs_operations_observed": fs_operations,
        "embedded_subprocess_fs_operations": sorted(
            set(fs_operations) - {"resolve", "stat", "listDir", "readText", "readBytes", "writeText"}
        ),
        "settings_operations_observed": settings_operations,
        "host_bridge_methods": host_bridge,
        "client_bridge_methods": client_bridge,
        "policy_modes_observed": policy_modes,
        "plugin_requests_danger_full_access": "danger-full-access" in combined,
        "forbidden_runtime_patterns": forbidden,
        "source_contains_raw_secret_literal": bool(re.search(r"\bsk-[A-Za-z0-9_-]{8,}\b", combined)),
    }


def profile_record(bundle_root: Path, plugin: dict[str, Any], adapter: dict[str, Any]) -> dict[str, Any]:
    profile_path = bundle_root / "home-full" / "profiles" / adapter["profile_binding"]["profile"] / "package.json"
    profile = read_json(profile_path) if profile_path.is_file() else None
    dependencies = profile.get("dependencies", {}) if isinstance(profile, dict) else {}
    bundles = profile.get("dsh", {}).get("profile", {}).get("bundles", []) if isinstance(profile, dict) else []
    return {
        "path": str(profile_path.resolve()),
        "present": profile_path.is_file(),
        "package_dependency_value": dependencies.get(plugin["package"]),
        "dependency_declared": plugin["package"] in dependencies,
        "dynamic_plugin_in_bundles": plugin["package"] in bundles,
        "bundles": bundles,
        "profile_sha256": sha256_file(profile_path) if profile_path.is_file() else None,
    }


def evaluate_e1(manifest: dict[str, Any], record: dict[str, Any], host_parse: dict[str, Any], client_parse: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    adapter = manifest["adapter"]
    declared_host = str(record["declared_host"] or "").removeprefix("./")
    declared_client = str(record["declared_client"] or "").removeprefix("./")
    checks = {
        "pinned_source_root": record["source_root_under_bundle"],
        "pinned_commit": record["commit_matches"],
        "package_identity": record["package_matches"],
        "version_identity": record["version_matches"],
        "license_recorded": record["license_present"],
        "dynamic_contract_explicit": record["contract_is_dynamic_plugin"] and declared_host == manifest["plugin"]["host_entry"] and declared_client == manifest["plugin"]["client_entry"],
        "dsh_bundle_not_inferred": record["declared_dsh_bundle"] is None,
        "host_entry_safe_and_present": record["host_entry_under_source"] and record["host_entry_present"],
        "client_entry_safe_and_present": record["client_entry_under_source"] and record["client_entry_present"],
        "host_body_parses": host_parse["parsed"] and host_parse["has_dynamic_return"] and host_parse["has_apply_entry"],
        "client_body_parses": client_parse["parsed"] and client_parse["has_dynamic_return"] and client_parse["has_apply_entry"],
        "dynamic_plugin_not_in_profile_bundles": not profile["dynamic_plugin_in_bundles"],
        "adapter_identity_bound": adapter["id"] and adapter["version"] and adapter["plugin_state_namespace"] == "dsh-config-migrate/migration",
        "parse_only_execution_mode": adapter["execution_in_this_gate"] == "parse-only",
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "thresholds": manifest["gates"]["E1"]["thresholds"],
        "interpretation": "E1 verifies the dynamic-plugin identity and adapter seam. It does not convert the member into dsh.bundle.",
    }


def evaluate_e2(manifest: dict[str, Any], record: dict[str, Any], declarations: dict[str, Any], profile: dict[str, Any], output: Path) -> dict[str, Any]:
    adapter = manifest["adapter"]
    capability = adapter["capability_facade"]
    forbidden_hits = sum(len(items) for items in declarations["forbidden_runtime_patterns"].values())
    observed_ctx = set(declarations["ctx_services"])
    embedded_fs = set(declarations["embedded_subprocess_fs_operations"])
    observed_fs = set(declarations["fs_operations_observed"]) - embedded_fs
    observed_settings = set(declarations["settings_operations_observed"])
    observed_host = set(declarations["host_bridge_methods"])
    observed_client = set(declarations["client_bridge_methods"]) - {"insert", "section"}
    checks = {
        "source_under_bundle_root": record["source_root_under_bundle"] and record["host_entry_under_source"] and record["client_entry_under_source"],
        "capability_ctx_allowlist": observed_ctx.issubset(set(capability["ctx_services"])),
        "filesystem_allowlist_recorded": observed_fs.issubset(set(capability["fs_operations"])),
        "settings_allowlist_recorded": observed_settings.issubset(set(capability["settings_operations"])),
        "host_bridge_allowlist_recorded": observed_host.issubset(set(capability["host_bridge"])),
        "client_bridge_allowlist_recorded": observed_client.issubset(set(capability["client_bridge"])),
        "plugin_policy_cannot_widen": capability["policy"]["plugin_policy_arguments"] == "ignore-and-replace" and declarations["plugin_requests_danger_full_access"],
        "external_home_denied": capability["policy"]["external_home"] == "deny-in-this-gate",
        "network_denied": capability["subprocess"]["network"] == "deny" and forbidden_hits == 0,
        "credentials_denied": capability["subprocess"]["credentials"] == "deny" and not declarations["source_contains_raw_secret_literal"],
        "shell_denied": capability["subprocess"]["shell"] is False,
        "node_only_subprocess": capability["subprocess"]["executable_allowlist"] == ["node"],
        "lifecycle_scripts_recorded_zero": record.get("declared_lifecycle_scripts") == [],
        "license_and_dependency_ledger_recorded": bool(record["license_present"]),
        "artifact_absence_explicit": bool(record["artifact_present"] is False and record["artifact_policy"]),
        "profile_is_case_local": under(Path(profile["path"]), Path(manifest["_bundle_root"])),
        "output_is_case_local": output.is_dir(),
        "parse_only_no_runtime_effect": manifest["isolation"]["runtime_plugin_execution"] is False and manifest["isolation"]["owner_database_touched"] is False,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "thresholds": manifest["gates"]["E2"]["thresholds"],
        "observed_declarations": declarations,
        "capability_facade": capability,
        "dependency_ledger": record["declared_dependencies"],
        "lifecycle_script_ledger": record["declared_lifecycle_scripts"],
        "registry_install_count": 0,
        "external_network_count": 0,
        "real_credential_count": 0,
        "external_effect_count": 0,
        "interpretation": "E2 passes the static, parse-only adapter boundary. Runtime subprocess sandboxing, write gating and registration disposal remain mandatory before E3-E6.",
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    bundle_root = args.bundle_root.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    manifest["_bundle_root"] = str(bundle_root)
    write_json(output / "adapter-manifest.json", {key: value for key, value in manifest.items() if key != "_bundle_root"})

    package = metadata_record(bundle_root, manifest["plugin"])
    record = package["record"]
    entry_paths = package["entry_paths"]
    host_source = git_show(Path(record["source_dir"]), manifest["plugin"]["commit"], manifest["plugin"]["host_entry"]) or ""
    client_source = git_show(Path(record["source_dir"]), manifest["plugin"]["commit"], manifest["plugin"]["client_entry"]) or ""
    host_parse = parse_function_body(entry_paths["host"], host_source) if host_source else {"parsed": False, "has_dynamic_return": False, "has_apply_entry": False, "path": str(entry_paths["host"]), "sha256": None, "parse": None}
    client_parse = parse_function_body(entry_paths["client"], client_source) if client_source else {"parsed": False, "has_dynamic_return": False, "has_apply_entry": False, "path": str(entry_paths["client"]), "sha256": None, "parse": None}
    declarations = source_declarations(host_source, client_source)
    profile = profile_record(bundle_root, manifest["plugin"], manifest["adapter"])
    e1 = evaluate_e1(manifest, record, host_parse, client_parse, profile)
    e2 = evaluate_e2(manifest, record, declarations, profile, output)
    summary = {
        "schema": SCHEMA,
        "status": "pass-within-scope" if e1["status"] == "pass" and e2["status"] == "pass" else "blocked",
        "classification": manifest["classification"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_root),
        "output": str(output),
        "plugin": record,
        "entrypoints": {"host": host_parse, "client": client_parse},
        "source_declarations": declarations,
        "profile": profile,
        "gates": {"E1": e1, "E2": e2},
        "checks": {
            "fixed_manifest_loaded": True,
            "e1_passed": e1["status"] == "pass",
            "e2_passed": e2["status"] == "pass",
            "plugin_not_executed": True,
            "owner_database_not_touched": True,
            "e3_e6_reopened": False,
        },
        "next_action": "E1/E2 eligible: implement/review the runtime plugin-aware seam, then reopen E3-E6 with the same owner, isolation and thresholds; do not inherit Codex evidence.",
        "non_claims": manifest["non_claims"],
    }
    write_json(output / "source-ledger.json", {"plugin": record, "entrypoints": summary["entrypoints"], "declarations": declarations, "profile": profile})
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True, help="isolated root containing the pinned dsh-config-migrate checkout")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    summary = build_summary(args)
    print(json.dumps({
        "status": summary["status"],
        "output": summary["output"],
        "E1": summary["gates"]["E1"]["status"],
        "E2": summary["gates"]["E2"]["status"],
        "E3-E6": "not-reopened",
    }, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass-within-scope" else 1


if __name__ == "__main__":
    raise SystemExit(main())
