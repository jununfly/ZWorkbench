#!/usr/bin/env python3
"""Probe owner state across an isolated Codex upgrade and rollback.

This is an acceptance/evaluation runner, not a product upgrade command.  It
installs the pinned Codex versions into a temporary npm prefix, while one
SQLite composition owner remains the durable source of truth across the old,
current, and rolled-back executable.  It also injects one bounded app-server
startup failure between upgrade and rollback to prove that a failed adapter
run is persisted without destroying the earlier ledger.

The runner never mutates the user's global npm prefix, global CODEX_HOME,
credentials, production data, or remote resources.  Human stopwatch time and
legal/commercial sign-off remain separate C7 gates.
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
import tempfile
import time
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_PROVIDER = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c5-c6" / "fake-provider.py"
RUNS = REPO_ROOT / "evaluation" / "runs"
OLD_VERSION = "0.138.0"
CURRENT_VERSION = "0.139.0"
SCHEMA = "zworkbench-w7-codex-owner-upgrade/v1"
OWNER_SCHEMA = "zworkbench-composition-owner/v1"
ADAPTER_SCHEMA = "zworkbench-codex-app-server-adapter/v1"
PROVIDER_ID = "w7-owner-upgrade-loopback"

sys.path.insert(0, str(REPO_ROOT / "src"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def digest_json(value) -> str:
    return sha256_bytes(encode(value).encode("utf-8"))


def run_capture(command: list[str], cwd: Path, env: dict[str, str], output_dir: Path, name: str) -> dict:
    started = time.monotonic()
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    elapsed = round(time.monotonic() - started, 6)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output_dir / f"{name}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    return {
        "command": command,
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(completed.stderr.encode("utf-8")),
    }


def wait_ready(path: Path, process: subprocess.Popen, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"fake Provider exited before readiness: {process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"fake Provider readiness timed out: {path}")


def stop_process(process: subprocess.Popen | None, stream=None) -> None:
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
    if stream is not None:
        stream.close()


def start_provider(root: Path) -> dict:
    ready = root / "provider.ready.json"
    request_log = root / "provider-requests.jsonl"
    stderr_path = root / "provider-stderr.log"
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(FAKE_PROVIDER),
            "--host",
            "127.0.0.1",
            "--port",
            "11434",
            "--provider-id",
            PROVIDER_ID,
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
        "provider_id": info["provider_id"],
        "endpoint": f"http://127.0.0.1:{info['port']}",
        "request_log": request_log,
    }


def package_paths(prefix: Path) -> dict[str, Path]:
    root_package = prefix / "lib" / "node_modules" / "@openai" / "codex"
    platform_package = root_package / "node_modules" / "@openai" / "codex-darwin-arm64"
    return {
        "wrapper": prefix / "bin" / "codex",
        "root_package": root_package / "package.json",
        "platform_package": platform_package / "package.json",
        "vendor_binary": platform_package / "vendor" / "aarch64-apple-darwin" / "bin" / "codex",
    }


def install_version(version: str, prefix: Path, root: Path, output_dir: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ"}}
    env.update(
        {
            "HOME": str(root),
            "npm_config_prefix": str(prefix),
            "npm_config_cache": str(root / "npm-cache"),
            "npm_config_userconfig": str(root / "npmrc"),
            "npm_config_registry": "https://registry.npmjs.org",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
        }
    )
    result = run_capture(
        ["npm", "install", "--global", f"@openai/codex@{version}"],
        root,
        env,
        output_dir,
        f"install-{version}",
    )
    paths = package_paths(prefix)
    package = {}
    platform = {}
    if paths["root_package"].is_file():
        package = json.loads(paths["root_package"].read_text(encoding="utf-8"))
    if paths["platform_package"].is_file():
        platform = json.loads(paths["platform_package"].read_text(encoding="utf-8"))
    result.update(
        {
            "version": version,
            "prefix": str(prefix),
            "executable": str(paths["wrapper"]),
            "package_version": package.get("version"),
            "platform_package_version": platform.get("version"),
            "artifacts": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()},
        }
    )
    return result


def inspect_version(version: str, executable: Path, output_dir: Path, env: dict[str, str]) -> dict:
    Path(env["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
    version_result = run_capture([str(executable), "--version"], REPO_ROOT, env, output_dir, f"{version}-version")
    help_result = run_capture([str(executable), "app-server", "--help"], REPO_ROOT, env, output_dir, f"{version}-app-server-help")
    combined_help = help_result["stdout"] + help_result["stderr"]
    return {
        "version": version,
        "version_check": version_result,
        "help_check": help_result,
        "version_pass": version_result["returncode"] == 0 and f"{version}" in version_result["stdout"],
        "app_server_help_pass": help_result["returncode"] == 0 and "generate-json-schema" in combined_help,
    }


def config_identity(provider: dict) -> dict:
    return {
        "adapter_schema": ADAPTER_SCHEMA,
        "model": "fake-model",
        "model_provider": "ollama",
        "sandbox": "read-only",
        "approval_policy": "never",
        "config_overrides": ["oss_provider=\"ollama\"", "model_provider=\"ollama\"", "model=\"fake-model\""],
        "disabled_features": ["plugins", "apps"],
        "provider": {"provider": provider["provider_id"], "model": "fake-model", "endpoint": provider["endpoint"], "transport": "loopback-only"},
    }


def checkpoint(owner, stage: str, run_id: str, before_run_ids: set[str]) -> dict:
    snapshot = owner.snapshot()
    run_ids = {item["run_id"] for item in snapshot["runs"]}
    return {
        "stage": stage,
        "run_id": run_id,
        "schema": snapshot["schema"],
        "schema_version": snapshot["schema_version"],
        "state_digest": owner.state_digest(),
        "run_count": len(snapshot["runs"]),
        "event_count": len(snapshot["events"]),
        "run_ids": sorted(run_ids),
        "prior_runs_preserved": before_run_ids.issubset(run_ids),
    }


def execute_stage(owner, stage: str, version: str, executable: Path, root: Path, provider: dict, case_dir: Path, config: dict) -> dict:
    from zworkbench.codex_adapter import CodexAppServerAdapter

    run_id = f"w7-owner-upgrade-{stage}"
    before_run_ids = {item["run_id"] for item in owner.snapshot()["runs"]}
    code_home = root / "codex-home" / stage
    task_cwd = root / "task" / stage
    event_log = case_dir / "adapter-events" / f"{stage}.jsonl"
    metadata = {"stage": stage, "codex_version": version, "config_identity_sha256": digest_json(config)}
    provider_identity = config["provider"]
    started = time.monotonic()
    with CodexAppServerAdapter(
        owner,
        executable,
        code_home,
        task_cwd,
        model="fake-model",
        model_provider="ollama",
        provider_identity=provider_identity,
        sandbox="read-only",
        approval_policy="never",
        event_log=event_log,
    ) as adapter:
        execution = adapter.execute(
            run_id,
            f"W7 owner upgrade compatibility {stage}: return the exact text fixture-ok and do not call tools.",
            task_type="c7.owner-upgrade-compatibility",
            metadata=metadata,
            timeout=45,
        )
    result = {
        "stage": stage,
        "version": version,
        "run_id": run_id,
        "thread_id": execution.thread_id,
        "turn_id": execution.turn_id,
        "text": execution.text,
        "status": execution.status,
        "event_digest": execution.event_digest,
        "environment_digest": execution.environment_digest,
        "config_identity_sha256": digest_json(config),
        "machine_elapsed_seconds": round(time.monotonic() - started, 6),
        "checkpoint": checkpoint(owner, stage, run_id, before_run_ids),
    }
    write_json(case_dir / "stages" / f"{stage}.json", result)
    return result


def create_failure_wrapper(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'code': -32099, 'message': 'controlled startup fault'}}), flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def failure_probe(owner, root: Path, case_dir: Path, provider: dict, config: dict) -> dict:
    from zworkbench.codex_adapter import CodexAppServerAdapter

    executable = case_dir / "controlled-startup-failure.py"
    create_failure_wrapper(executable)
    run_id = "w7-owner-upgrade-controlled-failure"
    before = owner.snapshot()
    before_ids = {item["run_id"] for item in before["runs"]}
    error = None
    started = time.monotonic()
    try:
        with CodexAppServerAdapter(
            owner,
            executable,
            root / "codex-home" / "controlled-failure",
            root / "task" / "controlled-failure",
            model="fake-model",
            model_provider="ollama",
            provider_identity=config["provider"],
            sandbox="read-only",
            approval_policy="never",
            event_log=case_dir / "adapter-events" / "controlled-failure.jsonl",
        ) as adapter:
            adapter.execute(
                run_id,
                "controlled startup failure; no tool call",
                task_type="c7.owner-upgrade-failure-probe",
                metadata={"stage": "controlled-failure", "config_identity_sha256": digest_json(config)},
                timeout=5,
            )
    except Exception as exc:  # expected: the wrapper returns a JSON-RPC error
        error = {"type": type(exc).__name__, "message": str(exc)}
    run = owner.get_run(run_id)
    after = owner.snapshot()
    result = {
        "run_id": run_id,
        "expected_failure": True,
        "error": error,
        "persisted_status": run["status"],
        "machine_elapsed_seconds": round(time.monotonic() - started, 6),
        "prior_runs_preserved": before_ids.issubset({item["run_id"] for item in after["runs"]}),
        "owner_schema": after["schema"],
        "failure_is_terminal": run["status"] in {"failed", "safe_stopped"},
        "no_physical_effects": len(after["effects"]) == len(before["effects"]),
    }
    write_json(case_dir / "controlled-failure.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("w7-codex-owner-upgrade-%Y%m%dT%H%M%S") + f"-{started_at.microsecond:06d}Z"
    output = (args.output or (RUNS / run_id)).resolve()
    output.mkdir(parents=True, exist_ok=False)
    temp_root = Path(tempfile.mkdtemp(prefix="zworkbench-c7-upgrade-"))
    prefix = temp_root / "npm-prefix"
    owner_db = output / "composition.sqlite3"
    provider = None
    stages = []
    checks = {}
    result = {
        "schema": SCHEMA,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "classification": "acceptance/evaluation",
        "versions": {"old": OLD_VERSION, "current": CURRENT_VERSION, "rollback": OLD_VERSION},
        "temporary_root": str(temp_root),
        "temporary_prefix": str(prefix),
        "owner_database": str(owner_db),
        "network": "npm registry only for isolated package install; provider is loopback-only",
        "real_credentials": False,
        "production_data": False,
    }
    try:
        prefix.mkdir(parents=True, exist_ok=True)
        provider = start_provider(output)
        config = config_identity(provider)
        write_json(output / "config-identity.json", {"value": config, "sha256": digest_json(config)})
        install_records = {}
        observations = {}
        from zworkbench.composition import CompositionOwner

        with CompositionOwner(owner_db) as owner:
            install_records["before"] = install_version(OLD_VERSION, prefix, temp_root, output / "npm" / "before")
            old_env = {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(temp_root / "codex-home" / "before")}
            observations["before"] = inspect_version(OLD_VERSION, Path(install_records["before"]["executable"]), output / "identity" / "before", old_env)
            stages.append(execute_stage(owner, "before", OLD_VERSION, Path(install_records["before"]["executable"]), temp_root, provider, output, config))

            install_records["after_upgrade"] = install_version(CURRENT_VERSION, prefix, temp_root, output / "npm" / "after-upgrade")
            current_env = {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(temp_root / "codex-home" / "after-upgrade")}
            observations["after_upgrade"] = inspect_version(CURRENT_VERSION, Path(install_records["after_upgrade"]["executable"]), output / "identity" / "after-upgrade", current_env)
            stages.append(execute_stage(owner, "after-upgrade", CURRENT_VERSION, Path(install_records["after_upgrade"]["executable"]), temp_root, provider, output, config))

            failure = failure_probe(owner, temp_root, output, provider, config)

            install_records["after_rollback"] = install_version(OLD_VERSION, prefix, temp_root, output / "npm" / "after-rollback")
            rollback_env = {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(temp_root / "codex-home" / "after-rollback")}
            observations["after_rollback"] = inspect_version(OLD_VERSION, Path(install_records["after_rollback"]["executable"]), output / "identity" / "after-rollback", rollback_env)
            stages.append(execute_stage(owner, "after-rollback", OLD_VERSION, Path(install_records["after_rollback"]["executable"]), temp_root, provider, output, config))

            final_digest = owner.state_digest()
            final_snapshot = owner.snapshot()
        with CompositionOwner(owner_db) as reopened:
            reopened_digest = reopened.state_digest()
            reopened_snapshot = reopened.snapshot()

        stage_run_ids = {item["run_id"] for item in stages}
        expected_run_ids = stage_run_ids | {failure["run_id"]}
        checks = {
            "all_install_commands_pass": all(item["returncode"] == 0 for item in install_records.values()),
            "all_expected_package_versions": all(item["package_version"] == item["version"] for item in install_records.values()),
            "all_platform_package_versions": all(item["platform_package_version"] == f"{item['version']}-darwin-arm64" for item in install_records.values()),
            "all_version_and_help_checks_pass": all(item["version_pass"] and item["app_server_help_pass"] for item in observations.values()),
            "same_owner_schema_across_stages": all(item["checkpoint"]["schema"] == OWNER_SCHEMA and item["checkpoint"]["schema_version"] == 1 for item in stages) and failure["owner_schema"] == OWNER_SCHEMA,
            "same_config_identity_across_stages": len({item["config_identity_sha256"] for item in stages}) == 1 and all(item["config_identity_sha256"] == digest_json(config) for item in stages),
            "prior_ledger_preserved_after_upgrade": stages[1]["checkpoint"]["prior_runs_preserved"],
            "prior_ledger_preserved_after_rollback": stages[2]["checkpoint"]["prior_runs_preserved"] and failure["prior_runs_preserved"],
            "controlled_failure_persisted_fail_closed": failure["expected_failure"] and failure["error"] is not None and failure["failure_is_terminal"] and failure["no_physical_effects"],
            "rollback_run_completed": stages[2]["status"] == "completed" and stages[2]["text"] == "fixture-ok",
            "all_expected_runs_present": expected_run_ids.issubset({item["run_id"] for item in final_snapshot["runs"]}),
            "state_survives_owner_reopen": final_digest == reopened_digest and final_snapshot == reopened_snapshot,
            "network_boundary_is_loopback_for_provider": provider["endpoint"].startswith("http://127.0.0.1:"),
            "real_credentials_false": True,
            "production_data_false": True,
        }
        result.update(
            {
                "status": "machine-pass / human-unknown" if all(checks.values()) else "machine-fail",
                "temporary_install": {"npm_prefix": str(prefix), "deleted_after_run": True, "versions": install_records},
                "observations": observations,
                "config_identity": {"value": config, "sha256": digest_json(config)},
                "stages": stages,
                "controlled_failure": failure,
                "owner_final": {"schema": final_snapshot["schema"], "schema_version": final_snapshot["schema_version"], "state_digest": final_digest, "run_count": len(final_snapshot["runs"]), "event_count": len(final_snapshot["events"]), "effect_count": len(final_snapshot["effects"])},
                "owner_reopen": {"state_digest": reopened_digest, "run_count": len(reopened_snapshot["runs"]), "event_count": len(reopened_snapshot["events"])},
                "checks": checks,
                "human_timing": {"status": "unknown", "note": "Runner wall clock is not a single-operator stopwatch."},
                "interpretation": "The same SQLite composition owner retained schema, configuration identity, prior ledger entries, and a failed adapter run across isolated old/current/rollback Codex installs. This is machine evidence only; it does not close human timing, legal/NOTICE, commercial, remote-exit, or independent-rebuild C7 gates.",
            }
        )
    except Exception as exc:
        result.update({"status": "machine-fail", "error": {"type": type(exc).__name__, "message": str(exc)}, "checks": checks})
    finally:
        if provider is not None:
            stop_process(provider["process"], provider["stderr"])
        shutil.rmtree(temp_root, ignore_errors=True)
    result["finished_at"] = now()
    write_json(output / "summary.json", result)
    print(json.dumps({"run_id": run_id, "summary": str(output / "summary.json"), "status": result["status"]}, ensure_ascii=False, indent=2))
    if result["status"] == "machine-fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
