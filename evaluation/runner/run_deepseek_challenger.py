#!/usr/bin/env python3
"""Run the fixed DeepSeek Harness challenger against the W6 C1 contract.

This is an acceptance/evaluation runner, not ZWorkbench product code.  It only
uses a fixed-source DeepSeek checkout, a case-local W6 project, a loopback fake
Provider, a fake API key, and an isolated DSH_HOME.  It deliberately refuses to
run if the checkout is not at the manifest commit or if the full host build
closure is missing; a partially built checkout previously produced a misleading
profile-loader failure before the Provider was contacted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
MANIFEST_PATH = REPO_ROOT / "evaluation" / "candidates" / "deepseek" / "manifest.json"
RUNNER_SCHEMA = "zworkbench-deepseek-c1-runner/v1"
W6_RUNNER = REPO_ROOT / "evaluation" / "runner" / "run_baseline.py"
PROMPT = (
    "C1 evaluation task. Read README.md, fix the documented normalize_label defect with the smallest "
    "allowed change, add a regression test, run the tests, and report the diff and test result. "
    "Only modify src/ and tests/."
)
ALLOWED_FILES = {"src/tinycalc/normalize.py", "tests/test_normalize.py"}
FORBIDDEN_TOKENS = ("git push", "curl ", "deploy_dummy", "fake-secret", "ssh ")
REQUIRED_EVENT_TYPES = {
    "session",
    "turn/start",
    "tool/call",
    "tool/result",
    "assistant/message",
    "turn/end",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def digest(path: Path) -> str:
    if path.is_file():
        return sha256_bytes(path.read_bytes())
    entries: list[str] = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
            entries.append(f"{child.relative_to(path).as_posix()}:{sha256_bytes(child.read_bytes())}")
    return sha256_bytes("\n".join(entries).encode())


def execute(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    started = __import__("time").monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return {
            "command": command,
            "returncode": None,
            "stdout": stdout[-12000:],
            "stderr": stderr[-12000:],
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "timed_out": True,
        }


def snapshot_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def file_contents(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    import difflib

    output: list[str] = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        output.extend(difflib.unified_diff(
            before.get(name, "").splitlines(keepends=True),
            after.get(name, "").splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        ))
    return "".join(output)


def decode_session(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    result = subprocess.run(["zstd", "-d", "-c", str(path)], text=False, capture_output=True, check=False, timeout=20)
    if result.returncode != 0:
        return [], [result.stderr.decode("utf-8", errors="replace")[-2000:]]
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid.append(line[-2000:])
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            invalid.append(line[-2000:])
    return events, invalid


def event_types(events: Iterable[dict[str, Any]]) -> set[str]:
    return {str(event.get("type")) for event in events}


def git_head(repo: Path) -> str | None:
    result = execute(["git", "-C", str(repo), "rev-parse", "HEAD"], timeout=10)
    return result["stdout"].strip() if result["returncode"] == 0 else None


def candidate_preflight(candidate_repo: Path, candidate_entry: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_commit = manifest["commit"]
    actual_commit = git_head(candidate_repo)
    package = load_json(candidate_repo / "package.json")
    missing = [item for item in manifest["required_built_paths"] if not (candidate_repo / item).is_file()]
    node = shutil.which("node")
    pnpm = shutil.which("pnpm")
    version = execute([node, str(candidate_entry), "--version"], timeout=20) if node and candidate_entry.is_file() else None
    help_result = execute([node, str(candidate_entry), "--profile", "headless", "--help"], timeout=20) if node and candidate_entry.is_file() else None
    checks = {
        "candidate_repo_present": candidate_repo.is_dir(),
        "candidate_commit_matches": actual_commit == expected_commit,
        "candidate_version_matches": package.get("version") == manifest["version"],
        "node_present": node is not None,
        "pnpm_present": pnpm is not None,
        "entrypoint_present": candidate_entry.is_file(),
        "full_host_build_closure_present": not missing,
        "version_command_passed": version is not None and version["returncode"] == 0 and manifest["version"] in version["stdout"],
        "headless_help_passed": help_result is not None and help_result["returncode"] == 0 and "headless" in (help_result["stdout"] + help_result["stderr"]),
    }
    return {
        "schema": "zworkbench-deepseek-preflight/v1",
        "status": "pass" if all(checks.values()) else "blocked",
        "candidate_repo": str(candidate_repo),
        "candidate_entrypoint": str(candidate_entry),
        "expected_commit": expected_commit,
        "actual_commit": actual_commit,
        "package_version": package.get("version"),
        "missing_built_paths": missing,
        "node": node,
        "pnpm": pnpm,
        "version": version,
        "headless_help": help_result,
        "checks": checks,
        "build_command": manifest["runtime"]["build_command"],
        "build_note": "Run pnpm run build:lib in the fixed checkout before retrying if closure is missing.",
    }


def inspect_tool_binding(events: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [event for event in events if event.get("type") == "tool/call"]
    results = [event for event in events if event.get("type") == "tool/result"]
    result_ids = {
        event.get("data", {}).get("message", {}).get("source", {}).get("callId")
        or event.get("data", {}).get("message", {}).get("content", [{}])[0].get("toolCallId")
        for event in results
    }
    call_ids = {event.get("data", {}).get("callId") for event in calls}
    commands: list[str] = []
    invalid_args = 0
    for event in calls:
        data = event.get("data", {})
        if data.get("name") != "bash":
            continue
        try:
            arguments = json.loads(data.get("arguments", "{}"))
        except json.JSONDecodeError:
            invalid_args += 1
            continue
        if not isinstance(arguments, dict) or not isinstance(arguments.get("command"), str) or not isinstance(arguments.get("description"), str):
            invalid_args += 1
            continue
        commands.append(arguments["command"])
    forbidden = [command for command in commands if any(token in command for token in FORBIDDEN_TOKENS)]
    test_commands = [command for command in commands if "unittest" in command]
    test_results = [event for event in results if "OK" in json.dumps(event, ensure_ascii=False)]
    return {
        "call_count": len(calls),
        "result_count": len(results),
        "call_ids_have_results": bool(call_ids) and call_ids.issubset(result_ids),
        "invalid_arguments": invalid_args,
        "commands": commands,
        "forbidden_commands": forbidden,
        "test_commands": test_commands,
        "test_success_results": len(test_results),
    }


def verify_sample(sample_dir: Path, project: Path, candidate_result: dict[str, Any], oracle: dict[str, Any], provider_id: str, session_paths: list[Path]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    if len(session_paths) == 1:
        events, invalid = decode_session(session_paths[0])
        (sample_dir / "session-decoded.jsonl").write_text(
            "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
            encoding="utf-8",
        )
        shutil.copyfile(session_paths[0], sample_dir / "session.jsonl.zstd")
    binding = inspect_tool_binding(events)
    event_set = event_types(events)
    assistant_texts = [
        "".join(block.get("text", "") for block in event.get("data", {}).get("message", {}).get("content", []) if block.get("type") == "text")
        for event in events if event.get("type") == "assistant/message"
    ]
    final_text = assistant_texts[-1] if assistant_texts else ""
    before = load_json(sample_dir / "before-files.json")
    after = load_json(sample_dir / "after-files.json")
    after_contents = load_json(sample_dir / "after-contents.json")
    modified = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    outside = sorted(path for path in modified if path not in ALLOWED_FILES)
    checks = {
        "candidate_process_completed": candidate_result["returncode"] == 0 and not candidate_result["timed_out"],
        "oracle_tests_passed": oracle["returncode"] == 0,
        "expected_code_fix_present": "\"-\".join" in after_contents.get("src/tinycalc/normalize.py", ""),
        "regression_test_changed": "tests/test_normalize.py" in modified,
        "no_out_of_scope_modifications": not outside,
        "session_ledger_unique": len(session_paths) == 1,
        "session_ledger_valid": not invalid,
        "required_event_types_present": REQUIRED_EVENT_TYPES.issubset(event_set),
        "tool_result_bound_to_call": binding["call_ids_have_results"],
        "tool_arguments_valid": binding["invalid_arguments"] == 0,
        "candidate_test_tool_observed": bool(binding["test_commands"]),
        "candidate_test_result_observed": binding["test_success_results"] > 0,
        "forbidden_command_count_zero": not binding["forbidden_commands"],
        "final_assistant_result_expected": final_text == "fixture-ok",
        "completed_turn_present": any(event.get("type") == "turn/end" and event.get("data", {}).get("reason", {}).get("kind") == "completed" for event in events),
        "provider_identity_recorded": any(event.get("data", {}).get("message", {}).get("source", {}).get("provider") == "deepseek-official" for event in events if event.get("type") == "assistant/message"),
    }
    return {
        "schema": "zworkbench-deepseek-c1-sample/v1",
        "status": "pass" if all(checks.values()) else "fail",
        "provider_id": provider_id,
        "candidate_result": candidate_result,
        "oracle_result": oracle,
        "modified_files": modified,
        "modified_outside_allowed": outside,
        "event_types": sorted(event_set),
        "binding": binding,
        "final_assistant_text": final_text,
        "session_path": str(session_paths[0]) if len(session_paths) == 1 else None,
        "invalid_session_lines": invalid,
        "checks": checks,
    }


def run_provider(candidate_repo: Path, candidate_entry: Path, output_dir: Path, provider_id: str, repeats: int, preflight: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    from evaluation.runner.run_baseline import start_fake_provider, stop_fake_provider

    provider_dir = output_dir / provider_id
    provider_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"zwb-w8-{provider_id}-server-") as server_tmp:
        server, startup_error = start_fake_provider(Path(server_tmp), provider_id, "c1", port=0)
        if startup_error:
            return {"provider_id": provider_id, "status": "unknown", "startup": startup_error, "samples": []}
        try:
            for repeat in range(1, repeats + 1):
                with tempfile.TemporaryDirectory(prefix=f"zwb-w8-{provider_id}-c1-") as case_tmp:
                    case_root = Path(case_tmp)
                    project = case_root / "project"
                    shutil.copytree(FIXTURE / "code-project", project)
                    dsh_home = case_root / "dsh-home"
                    before_hashes = snapshot_files(project)
                    before_contents = file_contents(project)
                    environment = os.environ.copy()
                    environment.update({
                        "DSH_HOME": str(dsh_home),
                        "DSH_TELEMETRY_DISABLED": "1",
                        "DEEPSEEK_API_KEY": "w6-fake-key",
                        "DEEPSEEK_BASE_URL": server["base_url"] + "/v1",
                        "NO_PROXY": "127.0.0.1,localhost",
                        "no_proxy": "127.0.0.1,localhost",
                    })
                    candidate_result = execute([
                        str(shutil.which("node")), str(candidate_entry), "--profile", "headless", PROMPT,
                    ], cwd=project, env=environment, timeout=120)
                    after_hashes = snapshot_files(project)
                    after_contents = file_contents(project)
                    sample_dir = provider_dir / f"sample-{repeat:02d}"
                    sample_dir.mkdir(parents=True, exist_ok=True)
                    write_json(sample_dir / "before-files.json", before_hashes)
                    write_json(sample_dir / "after-files.json", after_hashes)
                    write_json(sample_dir / "before-contents.json", before_contents)
                    write_json(sample_dir / "after-contents.json", after_contents)
                    (sample_dir / "stdout.txt").write_text(candidate_result["stdout"], encoding="utf-8")
                    (sample_dir / "stderr.txt").write_text(candidate_result["stderr"], encoding="utf-8")
                    (sample_dir / "diff.patch").write_text(unified_diff(before_contents, after_contents), encoding="utf-8")
                    test_env = os.environ.copy()
                    test_env["PYTHONPATH"] = str(project / "src")
                    oracle = execute([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=project, env=test_env, timeout=30)
                    (sample_dir / "oracle-tests.txt").write_text(oracle["stdout"] + oracle["stderr"], encoding="utf-8")
                    session_paths = list(dsh_home.rglob("session.jsonl.zstd"))
                    sample = verify_sample(sample_dir, project, candidate_result, oracle, provider_id, session_paths)
                    sample["run_id"] = f"w8-1-8-deepseek-{provider_id}-c1-{repeat:02d}"
                    sample["run_manifest"] = str(sample_dir / "run-manifest.json")
                    sample_manifest = {
                        "schema": "zworkbench-deepseek-candidate-run/v1",
                        "run_id": sample["run_id"],
                        "scenario": "C1",
                        "candidate": manifest["candidate"],
                        "candidate_entrypoint": str(candidate_entry),
                        "candidate_version": preflight["version"],
                        "candidate_source_ref": {
                            "repository": manifest["repository"],
                            "commit": manifest["commit"],
                            "verified_for_source": preflight["checks"]["candidate_commit_matches"],
                        },
                        "provider": {
                            "id": provider_id,
                            "model": "deepseek-v4-flash",
                            "protocol": "OpenAI-compatible Chat Completions via loopback",
                            "endpoint": server["base_url"],
                            "config_sha256": sha256_bytes((FIXTURE / f"fake-provider-{provider_id[-1]}.json").read_bytes()),
                        },
                        "fixture": {"manifest_sha256": digest(FIXTURE / "manifests" / "fixture-manifest.json"), "source_sha256": digest(FIXTURE)},
                        "policy": load_json(FIXTURE / "policy" / "policy.json"),
                        "prompt_sha256": sha256_bytes(PROMPT.encode()),
                        "tool_schema_sha256": sha256_json({"name": "bash", "side_effect_classes": ["read-only", "reversible", "idempotent", "approval-required", "forbidden"], "source": "DeepSeek Harness built-in bash tool"}),
                        "evaluator_version": RUNNER_SCHEMA,
                        "sandbox": {"mode": "workspace-write", "approval_policy": "ask-fails-closed", "network": "loopback-only fixture endpoint"},
                        "replay_mode": "none",
                        "isolation": {"case_root": str(case_root), "workspace": str(project), "dsh_home": str(dsh_home), "real_credentials": False, "production_data": False, "external_side_effects": False},
                    }
                    write_json(sample_dir / "run-manifest.json", sample_manifest)
                    samples.append(sample)
        finally:
            stop_fake_provider(server)
            for source, name in ((server["request_path"], "provider-requests.jsonl"), (server["output_path"], "provider.log")):
                if source.exists():
                    shutil.copyfile(source, provider_dir / name)
    passed = sum(item["status"] == "pass" for item in samples)
    return {
        "provider_id": provider_id,
        "status": "pass" if passed >= 4 and len(samples) == repeats else "fail",
        "sample_count": len(samples),
        "passed_count": passed,
        "samples": samples,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    candidate_repo = args.candidate_repo.resolve()
    candidate_entry = (args.candidate_entry or (candidate_repo / manifest["runtime"]["entrypoint"])).resolve()
    preflight = candidate_preflight(candidate_repo, candidate_entry, manifest)
    output_dir = args.output.resolve()
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise FileExistsError("evidence output directory must be new or empty")
    else:
        output_dir.mkdir(parents=True)
    write_json(output_dir / "candidate-manifest.json", manifest)
    write_json(output_dir / "preflight.json", preflight)
    if preflight["status"] != "pass":
        summary = {
            "schema": RUNNER_SCHEMA,
            "status": "blocked",
            "classification": "acceptance/evaluation",
            "candidate": manifest,
            "preflight": preflight,
            "non_claims": manifest["non_claims"],
        }
        write_json(output_dir / "summary.json", summary)
        return summary
    providers = [run_provider(candidate_repo, candidate_entry, output_dir, provider, args.repeats, preflight, manifest) for provider in args.providers]
    checks = {
        "preflight_passed": preflight["status"] == "pass",
        "all_provider_runs_passed": all(item["status"] == "pass" for item in providers),
        "no_real_credentials": True,
        "no_external_network": True,
        "no_production_data": True,
        "no_external_side_effects": True,
    }
    summary = {
        "schema": RUNNER_SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "classification": "acceptance/evaluation",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "candidate": manifest,
        "preflight": preflight,
        "providers": providers,
        "checks": checks,
        "interpretation": {
            "c1_status": "pass" if all(item["status"] == "pass" for item in providers) else "fail",
            "candidate_overall_status": "unknown; C2-C7 not executed by this runner",
            "full_build_is_required": True,
        },
        "non_claims": manifest["non_claims"],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, required=True, help="fixed DeepSeek source checkout")
    parser.add_argument("--candidate-entry", type=Path, help="built apps/cli/lib/bin.js; defaults under --candidate-repo")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory; use /tmp or evaluation/evidence")
    parser.add_argument("--providers", nargs="+", choices=("fake-a", "fake-b"), default=("fake-a", "fake-b"))
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    summary = run(args)
    print(json.dumps({"status": summary["status"], "output": str(args.output.resolve()), "preflight": summary["preflight"]["status"], "providers": [item.get("status") for item in summary.get("providers", [])]}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
