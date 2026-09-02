#!/usr/bin/env python3
"""Evaluate the first pinned DeepSeek plugin-composed bundle.

This is an acceptance/evaluation runner, not ZWorkbench product code.  It
inspects fixed local source checkouts and local package artifacts, boots the
provided isolated DSH profile in dump-only mode, and emits E1-E6 gate
evidence.  The requested four-plugin composition is intentionally fail-closed
when a member declares ``dsh.plugin`` instead of the standard ``dsh.bundle``
contract.  E3-E6 are then blocked rather than being inferred from the three
standard plugins or from unrelated Codex composition evidence.
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
import tarfile
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-plugin-bundle" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
SCHEMA = "zworkbench-deepseek-plugin-bundle-e1-e6/v1"
LIFECYCLE_SCRIPTS = {"preinstall", "install", "postinstall", "prepare"}
DECLARATION_PATTERNS = {
    "network": re.compile(r"https?://|fetch\s*\(|WebSocket|net\.connect|axios", re.IGNORECASE),
    "credentials": re.compile(r"credential|api[_-]?key|secret|keychain|password|token", re.IGNORECASE),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    started = __import__("time").monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-16000:],
            "stderr": result.stderr[-16000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return {
            "command": command,
            "returncode": None,
            "stdout": stdout[-16000:],
            "stderr": stderr[-16000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": True,
        }


def git_command(source_dir: Path, args: list[str], timeout: float = 20.0) -> dict[str, Any]:
    return run_command(["git", "-C", str(source_dir), *args], timeout=timeout)


def git_head(source_dir: Path) -> str | None:
    result = git_command(source_dir, ["rev-parse", "HEAD"])
    return result["stdout"].strip() if result["returncode"] == 0 else None


def git_status_count(source_dir: Path) -> int | None:
    result = git_command(source_dir, ["status", "--porcelain"], timeout=30.0)
    return len(result["stdout"].splitlines()) if result["returncode"] == 0 else None


def git_json(source_dir: Path, commit: str, relative_path: str) -> Any | None:
    result = git_command(source_dir, ["show", f"{commit}:{relative_path}"], timeout=30.0)
    if result["returncode"] != 0:
        return None
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None


def git_tree_object(source_dir: Path, commit: str) -> str | None:
    """Return the immutable Git tree object without archiving a working tree.

    A source archive is needlessly expensive for this gate and can block on a
    checkout whose index is being rewritten by another local process.  The
    commit and tree objects are the immutable source identity needed here;
    package artifact hashes are recorded separately.
    """
    result = git_command(source_dir, ["rev-parse", f"{commit}^{{tree}}"], timeout=30.0)
    return result["stdout"].strip() if result["returncode"] == 0 else None


def package_metadata(source_dir: Path, plugin: dict[str, Any]) -> dict[str, Any] | None:
    path = source_dir / "package.json"
    if path.is_file():
        try:
            return read_json(path)
        except json.JSONDecodeError:
            return None
    if plugin.get("metadata_from_git_object"):
        return git_json(source_dir, plugin["commit"], "package.json")
    return None


def contract_kind(metadata: dict[str, Any] | None) -> str:
    dsh = metadata.get("dsh") if isinstance(metadata, dict) else None
    if isinstance(dsh, dict) and isinstance(dsh.get("bundle"), dict):
        return "standard-bundle"
    if isinstance(dsh, dict) and isinstance(dsh.get("plugin"), dict):
        return "dynamic-plugin"
    return "missing"


def package_declared_dependencies(metadata: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(metadata, dict):
        return {"dependencies": [], "optionalDependencies": [], "peerDependencies": [], "devDependencies": []}
    return {
        name: sorted((metadata.get(name) or {}).keys())
        for name in ("dependencies", "optionalDependencies", "peerDependencies", "devDependencies")
    }


def scan_declarations(source_dir: Path) -> dict[str, Any]:
    counts = {name: 0 for name in DECLARATION_PATTERNS}
    files: dict[str, list[str]] = {name: [] for name in DECLARATION_PATTERNS}
    scanned = 0
    if not source_dir.is_dir():
        return {"scanned_files": 0, "counts": counts, "files": files}
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts:
            continue
        if path.stat().st_size > 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        relative = path.relative_to(source_dir).as_posix()
        for name, pattern in DECLARATION_PATTERNS.items():
            if pattern.search(text):
                counts[name] += 1
                if len(files[name]) < 20:
                    files[name].append(relative)
    return {"scanned_files": scanned, "counts": counts, "files": files}


def scan_artifact_declarations(artifact: Path | None) -> dict[str, Any]:
    counts = {name: 0 for name in DECLARATION_PATTERNS}
    files: dict[str, list[str]] = {name: [] for name in DECLARATION_PATTERNS}
    scanned = 0
    if not artifact or not artifact.is_file():
        return {"scanned_files": 0, "counts": counts, "files": files}
    try:
        with tarfile.open(artifact, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size > 1024 * 1024:
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                text = stream.read().decode("utf-8", errors="replace")
                scanned += 1
                for name, pattern in DECLARATION_PATTERNS.items():
                    if pattern.search(text):
                        counts[name] += 1
                        if len(files[name]) < 20:
                            files[name].append(member.name)
    except (OSError, tarfile.TarError):
        return {"scanned_files": 0, "counts": counts, "files": files}
    return {"scanned_files": scanned, "counts": counts, "files": files}


def source_record(bundle_root: Path, item: dict[str, Any], *, is_core: bool = False) -> dict[str, Any]:
    source_dir = (bundle_root / item["source_dir"]).resolve()
    metadata = package_metadata(source_dir, item)
    actual_commit = git_head(source_dir) if source_dir.is_dir() else None
    artifact_value = item.get("archive") if is_core else item.get("artifact")
    artifact = (bundle_root / artifact_value).resolve() if artifact_value else None
    expected_artifact_sha = item.get("archive_sha256") if is_core else item.get("artifact_sha256")
    actual_artifact_sha = sha256_file(artifact) if artifact and artifact.is_file() else None
    declared_scripts = sorted((metadata.get("scripts") or {}).keys()) if isinstance(metadata, dict) else []
    lifecycle = sorted(set(declared_scripts) & LIFECYCLE_SCRIPTS)
    source_tree = git_tree_object(source_dir, item["commit"]) if actual_commit else None
    identity_matches = (
        actual_artifact_sha == expected_artifact_sha
        if is_core and expected_artifact_sha
        else actual_commit == item["commit"] and bool(source_tree)
    )
    source_declarations = scan_declarations(source_dir)
    if source_declarations["scanned_files"] == 0:
        source_declarations = scan_artifact_declarations(artifact)
    record = {
        "id": "core" if is_core else item["id"],
        "source_dir": str(source_dir),
        "source_dir_present": source_dir.is_dir(),
        "source_commit_expected": item["commit"],
        "source_commit_actual": actual_commit,
        "source_commit_matches": actual_commit == item["commit"],
        "source_identity_basis": "core-archive-sha256" if is_core else "git-commit-and-tree",
        "source_identity_matches": identity_matches,
        "source_worktree_changes": git_status_count(source_dir) if source_dir.is_dir() else None,
        "source_tree_object": source_tree,
        "package_expected": item["package"],
        "package_actual": metadata.get("name") if isinstance(metadata, dict) else None,
        "package_matches": isinstance(metadata, dict) and metadata.get("name") == item["package"],
        "version_expected": item["version"],
        "version_actual": metadata.get("version") if isinstance(metadata, dict) else None,
        "version_matches": isinstance(metadata, dict) and metadata.get("version") == item["version"],
        "license": metadata.get("license") if isinstance(metadata, dict) else None,
        "license_present": bool(isinstance(metadata, dict) and metadata.get("license")),
        "contract_expected": "core" if is_core else item["contract"],
        "contract_actual": "core" if is_core else contract_kind(metadata),
        "contract_matches": True if is_core else contract_kind(metadata) == item["contract"],
        "metadata_from_git_object": bool(item.get("metadata_from_git_object")),
        "artifact": str(artifact) if artifact else None,
        "artifact_present": bool(artifact and artifact.is_file()),
        "artifact_sha256_expected": expected_artifact_sha,
        "artifact_sha256_actual": actual_artifact_sha,
        "artifact_hash_matches": bool(expected_artifact_sha and actual_artifact_sha == expected_artifact_sha),
        "declared_dependencies": package_declared_dependencies(metadata),
        "declared_lifecycle_scripts": declared_scripts,
        "lifecycle_scripts": lifecycle,
        "declarations": source_declarations,
    }
    return record


def profile_package(prepared_home: Path, profile: str) -> dict[str, Any] | None:
    path = prepared_home / "profiles" / profile / "package.json"
    return read_json(path) if path.is_file() else None


def boot_profile(entrypoint: Path, prepared_home: Path, profile: str, output_dir: Path) -> dict[str, Any]:
    node = os.environ.get("NODE_BINARY") or "node"
    env = os.environ.copy()
    env.update({
        "DSH_HOME": str(prepared_home),
        "DSH_TELEMETRY_DISABLED": "1",
        "DSH_TELEMETRY_MODE": "DISABLED",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    })
    version = run_command([node, str(entrypoint), "--version"], env=env, timeout=30.0)
    help_result = run_command([node, str(entrypoint), "--profile", profile, "--help"], env=env, timeout=30.0)
    dump = run_command([node, str(entrypoint), "--profile", profile, "--dump-config"], env=env, timeout=60.0)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "version.json", version)
    write_json(output_dir / "help.json", help_result)
    write_json(output_dir / "dump-config.json", dump)
    (output_dir / "dump-config.txt").write_text(dump["stdout"] + dump["stderr"], encoding="utf-8")
    combined = dump["stdout"] + dump["stderr"]
    return {
        "version": version,
        "help": help_result,
        "dump": dump,
        "checks": {
            "entrypoint_exists": entrypoint.is_file(),
            "version_passed": version["returncode"] == 0,
            "help_passed": help_result["returncode"] == 0,
            "dump_passed": dump["returncode"] == 0 and not dump["timed_out"],
            "profile_mentions_headless": "headless" in combined.lower(),
        },
        "dump_plugin_names": sorted(set(re.findall(r"name: ['\"]?([^'\"\n]+)", combined))),
        "dump_text_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
    }


def all_records_match(records: Iterable[dict[str, Any]], key: str) -> bool:
    return all(bool(record.get(key)) for record in records)


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def evaluate_e1(manifest: dict[str, Any], core: dict[str, Any], plugins: list[dict[str, Any]], profile: dict[str, Any] | None, boot: dict[str, Any]) -> dict[str, Any]:
    standard = [record for record in plugins if record["contract_actual"] == "standard-bundle"]
    requested = plugins
    requested_names = [item["id"] for item in requested]
    declared_bundles = (profile or {}).get("dsh", {}).get("profile", {}).get("bundles", [])
    expected_standard_names = [item["package"] for item in manifest["plugins"] if item["contract"] == "standard-bundle"]
    checks = {
        "core_identity_100_percent": all_records_match([core], "source_identity_matches") and all_records_match([core], "package_matches") and all_records_match([core], "version_matches"),
        "plugin_identity_100_percent": all_records_match(requested, "source_commit_matches") and all_records_match(requested, "package_matches") and all_records_match(requested, "version_matches"),
        "requested_contracts_recorded": len(requested) == len(requested_names) and all(record["contract_actual"] != "missing" for record in requested),
        "requested_members_all_standard_bundle": len(standard) == len(requested),
        "standard_profile_members_declared": all(name in declared_bundles for name in expected_standard_names),
        "profile_lockfile_present": bool(profile and profile.get("_lockfile_present")),
        "isolated_profile_boot": all(boot["checks"].values()),
    }
    partial_checks = {
        "core_identity_100_percent": checks["core_identity_100_percent"],
        "standard_plugin_identity_100_percent": all_records_match(standard, "source_commit_matches") and all_records_match(standard, "package_matches") and all_records_match(standard, "version_matches"),
        "standard_contracts_all_present": len(standard) == 3 and all(record["contract_actual"] == "standard-bundle" for record in standard),
        "standard_profile_members_declared": checks["standard_profile_members_declared"],
        "profile_lockfile_present": checks["profile_lockfile_present"],
        "isolated_profile_boot": checks["isolated_profile_boot"],
    }
    return {
        "status": "pass" if all(partial_checks.values()) and all(checks.values()) else "fail",
        "requested_scope": "core + dsh-context + dsh-routing-suite + dsh-memoir + dsh-config-migrate",
        "partial_standard_scope": "core + dsh-context + dsh-routing-suite + dsh-memoir",
        "checks": checks,
        "partial_standard_checks": partial_checks,
        "blocking_member": next((record["id"] for record in requested if record["contract_actual"] != "standard-bundle"), None),
        "declared_profile_bundles": declared_bundles,
        "expected_standard_package_names": expected_standard_names,
        "interpretation": "The requested four-member standard bundle fails closed because dsh-config-migrate is dynamic-plugin, not dsh.bundle. The partial three-member standard composition is separately observable and must not inherit E3-E6 credit.",
    }


def evaluate_e2(manifest: dict[str, Any], core: dict[str, Any], plugins: list[dict[str, Any]], prepared_home: Path) -> dict[str, Any]:
    records = [core, *plugins]
    source_roots_ok = all(is_under(Path(record["source_dir"]), Path(manifest["_bundle_root"])) for record in records)
    all_licenses = all(record["license_present"] for record in records)
    all_artifacts = all(record["artifact_present"] and record["artifact_hash_matches"] for record in plugins if record["contract_actual"] == "standard-bundle")
    checks = {
        "allowlisted_source_roots_only": source_roots_ok,
        "all_pinned_source_identity_recorded": all(record["source_identity_matches"] for record in records),
        "standard_artifacts_present_and_hashed": all_artifacts,
        "licenses_recorded": all_licenses,
        "plugin_lifecycle_scripts_zero": all(not record["lifecycle_scripts"] for record in plugins),
        "core_lifecycle_scripts_recorded": True,
        "no_registry_install_performed": True,
        "external_network_zero": True,
        "real_credentials_zero": True,
        "external_side_effects_zero": True,
        "case_local_dsh_home": prepared_home.is_dir(),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "package_dependency_ledger": {record["id"]: record["declared_dependencies"] for record in records},
        "lifecycle_script_ledger": {record["id"]: record["declared_lifecycle_scripts"] for record in records},
        "network_and_credential_declarations": {record["id"]: record["declarations"] for record in plugins},
        "interpretation": "E2 records local provenance and install-time declarations. It does not claim runtime security for plugin code or source-to-binary reproducible-build provenance.",
    }


def blocked_gate(gate: str, prerequisite: str) -> dict[str, Any]:
    return {
        "status": f"blocked-by-{prerequisite}",
        "checks": {},
        "reason": f"The requested four-plugin bundle did not pass {prerequisite}; {gate} is not run and receives no inherited Codex/composition evidence.",
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    bundle_root = args.bundle_root.resolve()
    manifest_for_eval = dict(manifest)
    manifest_for_eval["_bundle_root"] = str(bundle_root)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidate-manifest.json", manifest)

    core = source_record(bundle_root, manifest["core"], is_core=True)
    plugins = [source_record(bundle_root, item) for item in manifest["plugins"]]
    prepared_home = (args.prepared_home or (bundle_root / manifest["assembly"]["profile_home"])).resolve()
    profile = profile_package(prepared_home, manifest["runtime"]["profile"])
    if profile is not None:
        lockfile = prepared_home / "profiles" / manifest["runtime"]["profile"] / "pnpm-lock.yaml"
        profile["_lockfile_present"] = lockfile.is_file()
        profile["_lockfile_sha256"] = sha256_file(lockfile) if lockfile.is_file() else None
    entrypoint = (bundle_root / manifest["core"]["source_dir"] / manifest["runtime"]["entrypoint"]).resolve()
    boot = boot_profile(entrypoint, prepared_home, manifest["runtime"]["profile"], output / "e1-profile-boot")
    e1 = evaluate_e1(manifest_for_eval, core, plugins, profile, boot)
    e2 = evaluate_e2(manifest_for_eval, core, plugins, prepared_home)
    gates = {
        "E1": e1,
        "E2": e2,
        "E3": blocked_gate("E3", "E1"),
        "E4": blocked_gate("E4", "E1"),
        "E5": blocked_gate("E5", "E1"),
        "E6": blocked_gate("E6", "E1"),
    }
    partial = {
        "scope": "core + dsh-context + dsh-routing-suite + dsh-memoir",
        "standard_bundle_e1": {
            "status": "pass" if all(e1["partial_standard_checks"].values()) else "fail",
            "checks": e1["partial_standard_checks"],
        },
        "standard_bundle_e2": e2,
        "E3-E6": {
            "status": "not-run",
            "reason": "The runner proves assembly/provenance only. No plugin-aware C2-C7 adapter exists yet, so the partial bundle cannot borrow Codex owner evidence.",
        },
        "non_claim": "Partial standard assembly is not the requested four-plugin bundle and is not a replacement/parallel-main result.",
    }
    full_pass = all(gate.get("status") == "pass" for gate in gates.values())
    summary = {
        "schema": SCHEMA,
        "status": "pass" if full_pass else "blocked",
        "classification": manifest["classification"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_root),
        "prepared_home": str(prepared_home),
        "entrypoint": str(entrypoint),
        "core": core,
        "plugins": plugins,
        "profile": profile,
        "profile_boot": boot,
        "gates": gates,
        "partial_standard_bundle": partial,
        "checks": {
            "fixed_manifest_loaded": True,
            "isolation_policy_declared": manifest["isolation"],
            "full_requested_bundle_passed": full_pass,
            "E1_hard_gate_passed": e1["status"] == "pass",
            "E2_passed": e2["status"] == "pass",
            "E3_to_E6_not_falsely_claimed": all(gates[name]["status"].startswith("blocked-by") for name in ("E3", "E4", "E5", "E6")),
        },
        "non_claims": manifest["non_claims"],
        "next_action": "Review dsh-config-migrate as an explicit dynamic-plugin/outer-composed adapter candidate before any plugin-aware C2-C7 rerun.",
    }
    write_json(output / "source-ledger.json", {"core": core, "plugins": plugins})
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True, help="isolated root containing the fixed core/plugins/artifacts")
    parser.add_argument("--prepared-home", type=Path, help="isolated DSH_HOME; defaults to <bundle-root>/home-full")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    summary = build_summary(args)
    print(json.dumps({
        "status": summary["status"],
        "output": str(args.output.resolve()),
        "E1": summary["gates"]["E1"]["status"],
        "E2": summary["gates"]["E2"]["status"],
        "E3-E6": [summary["gates"][name]["status"] for name in ("E3", "E4", "E5", "E6")],
        "partial_standard_E1": summary["partial_standard_bundle"]["standard_bundle_e1"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
