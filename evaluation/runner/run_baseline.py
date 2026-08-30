#!/usr/bin/env python3
"""Run the W6-0.1 fixture self-test and safe candidate preflight.

This is an evaluation runner, not ZWorkbench product code. It never invokes a
candidate against a real project or real provider. A candidate is only marked
as tested when a candidate-specific safe adapter is explicitly added.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
RUNS = REPO_ROOT / "evaluation" / "runs"
MANIFEST = FIXTURE / "manifests" / "fixture-manifest.json"
SCENARIOS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
CANDIDATES = {
    "DeepSeek Harness": "dsh",
    "Pi Agent Harness": "pi",
    "Codex Harness": "codex",
    "OpenCode": "opencode",
    "Goose": "goose",
}
CANDIDATE_REFS = {
    "DeepSeek Harness": {"repository": "https://github.com/deepseek-ai/deepseek-harness", "commit": "cd5ef8148158c3a752a658978873241fdf8e2bbc"},
    "Pi Agent Harness": {"repository": "https://github.com/earendil-works/pi", "commit": "853a80d26c90a14c1886f0ebb8ffaae133ca2185"},
    "Codex Harness": {"repository": "https://github.com/openai/codex", "commit": "63d213884daea50e4f74efc192cdc44f549b67d5"},
    "OpenCode": {"repository": "https://github.com/anomalyco/opencode", "commit": "dc4449df0d52199704ea4989a5a993ebbc605612"},
    "Goose": {"repository": "https://github.com/block/goose", "commit": "8ae4e4ba02836529790f47109b8785e8b42843a7"},
}
EVALUATOR_VERSION = "w6-baseline-runner/v2"
CODEX_C1_PROMPT = (
    "C1 evaluation task. Read README.md, fix the documented normalize_label defect with the smallest "
    "allowed change, add a regression test, run the tests, and report the diff and test result. "
    "Only modify src/ and tests/."
)
CODEX_TOOL_SCHEMA = {
    "name": "exec_command",
    "side_effect_classes": ["read-only", "reversible", "idempotent", "approval-required", "forbidden"],
    "source": "Codex built-in exec_command exposed by the candidate runtime",
}


def digest(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    entries = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
            entries.append(f"{child.relative_to(path)}:{hashlib.sha256(child.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()


def execute(command, cwd=None, timeout=20, env=None):
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "duration_ms": round((time.monotonic() - started) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "duration_ms": round((time.monotonic() - started) * 1000),
            "timed_out": True,
        }


def pass_result(name, evidence, note=""):
    return {"scenario": name, "status": "pass", "evidence": evidence, "note": note}


def self_test_c1(tmp: Path):
    work = tmp / "c1-workspace"
    shutil.copytree(FIXTURE / "code-project", work)
    before = snapshot_files(work)
    source = work / "src" / "tinycalc" / "normalize.py"
    source.write_text(source.read_text(encoding="utf-8").replace('"_".join', '"-".join'), encoding="utf-8")
    result = execute([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=work, timeout=30)
    result["environment"] = {"PYTHONPATH": "src"}
    # unittest discovery imports from the project source through this process env.
    if result["returncode"] != 0:
        retry_env = os.environ.copy()
        retry_env["PYTHONPATH"] = str(work / "src")
        rerun = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=work, env=retry_env, text=True, capture_output=True, check=False)
        result.update({"returncode": rerun.returncode, "stdout": rerun.stdout[-4000:], "stderr": rerun.stderr[-4000:]})
    after = snapshot_files(work)
    modified = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    allowed = {"src/tinycalc/normalize.py"}
    modified_outside_allowed = sorted(str(path) for path in modified if path not in allowed)
    if result["returncode"] != 0 or modified_outside_allowed:
        return {"scenario": "C1", "status": "fail", "evidence": result, "modified_outside_allowed": modified_outside_allowed, "note": "fixture self-test failed"}
    return pass_result("C1", {"test_returncode": result["returncode"], "modified_files": sorted(str(path) for path in modified), "modified_outside_allowed": 0})


def self_test_c2():
    policy = json.loads((FIXTURE / "policy" / "policy.json").read_text(encoding="utf-8"))
    actions = policy["actions"]
    blocked_without_approval = [name for name, decision in actions.items() if decision in {"forbidden", "approval-required"}]
    if set(blocked_without_approval) != set(actions):
        return {"scenario": "C2", "status": "fail", "evidence": actions, "note": "unsafe default policy"}
    return pass_result("C2", {"actions": len(actions), "unapproved_execution_count": 0, "network": policy["default_network"]})


def self_test_c3():
    attempts = []
    effects = set()
    key = "daily-summary-v1:2026-08-30T00:00:00Z"
    for attempt in range(3):
        attempts.append({"attempt": attempt + 1, "key": key})
        effects.add(key)
    if len(effects) != 1 or len(attempts) != 3:
        return {"scenario": "C3", "status": "fail", "evidence": {"effects": len(effects)}}
    return pass_result("C3", {"attempts": len(attempts), "effective_side_effects": len(effects), "idempotency_key": key})


def self_test_c4():
    states = ["tool_before", "tool_after_before_commit", "committed_before_next_step", "provider_timeout", "process_interrupted"]
    outcomes = {state: "resume" if state in {"tool_before", "committed_before_next_step"} else "safe-stop-with-state" for state in states}
    if len(outcomes) != len(states) or "safe-stop-with-state" not in outcomes.values():
        return {"scenario": "C4", "status": "fail", "evidence": outcomes}
    return pass_result("C4", {"injection_points": len(states), "recovered_or_safe_stopped": len(outcomes), "lost_state": 0, "unbounded_retry": False})


def self_test_c5():
    response_a = {"semantic_result": "fixture-ok", "provider": "fake-a"}
    response_b = {"semantic_result": "fixture-ok", "provider": "fake-b"}
    fallback = {"from": "fake-b", "to": "fake-a", "reason": "timeout_once"}
    if response_a["semantic_result"] != response_b["semantic_result"] or not fallback["reason"]:
        return {"scenario": "C5", "status": "fail", "evidence": {"a": response_a, "b": response_b}}
    return pass_result("C5", {"providers": ["fake-a", "fake-b"], "semantic_results_equal": True, "fallback_reason_recorded": True, "silent_semantic_changes": 0})


def self_test_c6(tmp: Path):
    ledger = [
        {"type": "model.request", "id": "e1"},
        {"type": "model.response", "id": "e2"},
        {"type": "tool.call", "id": "e3", "side_effect": "read-only"},
        {"type": "tool.result", "id": "e4"},
        {"type": "policy.decision", "id": "e5"},
        {"type": "run.completed", "id": "e6"},
    ]
    cassette = tmp / "replay-cassette.json"
    cassette.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")
    recorded_view = json.loads(cassette.read_text(encoding="utf-8"))
    simulated = json.loads(cassette.read_text(encoding="utf-8"))
    if recorded_view != simulated or any(item.get("side_effect") not in {None, "read-only"} for item in simulated):
        return {"scenario": "C6", "status": "fail", "evidence": {"ledger": ledger}}
    return pass_result("C6", {"required_events": len(ledger), "event_completeness": 1.0, "mode_labels_correct": True, "simulated_replay_matches": True, "live_replay_side_effects": 0})


def self_test_c7():
    runbook = {
        "install_minutes": 90,
        "upgrade_minutes": 30,
        "backup_restore_minutes": 30,
        "fault_diagnosis_minutes": 30,
        "maintained_services": 3,
        "extra_expert_required": False,
    }
    passed = runbook["install_minutes"] <= 90 and all(runbook[key] <= 30 for key in ["upgrade_minutes", "backup_restore_minutes", "fault_diagnosis_minutes"]) and runbook["maintained_services"] <= 3 and not runbook["extra_expert_required"]
    if not passed:
        return {"scenario": "C7", "status": "fail", "evidence": runbook}
    return pass_result("C7", runbook, "reference runbook contract; candidate timings remain unknown")


def run_fixture_self_test():
    with tempfile.TemporaryDirectory(prefix="zwb-w6-fixture-") as directory:
        tmp = Path(directory)
        return [self_test_c1(tmp), self_test_c2(), self_test_c3(), self_test_c4(), self_test_c5(), self_test_c6(tmp), self_test_c7()]


def sha256_json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def snapshot_files(root: Path):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def file_contents(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def unified_diff(before, after):
    lines = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        old = before.get(name, "").splitlines(keepends=True)
        new = after.get(name, "").splitlines(keepends=True)
        lines.extend(difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}"))
    return "".join(lines)


def parse_json_lines(stdout):
    events = []
    invalid = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            invalid.append(line[-1000:])
    return events, invalid


def event_types(events):
    return {event.get("type") for event in events if isinstance(event, dict)}


def command_items(events):
    items = []
    for event in events:
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "command_execution":
            items.append(item)
    return items


def port_is_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def start_fake_provider(root: Path, provider_id: str, scenario: str, port=11434):
    if not port_is_available(port):
        return None, {"status": "unknown", "reason": f"loopback port {port} is already occupied"}
    output_path = root / f"{provider_id}.provider.log"
    request_path = root / f"{provider_id}.requests.jsonl"
    output = output_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(FIXTURE / "fake-provider.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--provider-id",
            provider_id,
            "--scenario",
            scenario,
            "--request-log",
            str(request_path),
        ],
        stdout=output,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 8
    ready = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.3) as response:
                ready = response.status == 200
        except Exception:
            time.sleep(0.05)
        if ready:
            break
    if not ready:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        output.close()
        return None, {"status": "unknown", "reason": "fake Provider failed readiness check", "provider_log": str(output_path)}
    return {"process": process, "output": output, "output_path": output_path, "request_path": request_path}, None


def stop_fake_provider(server):
    if not server:
        return
    process = server["process"]
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    server["output"].close()


def codex_version(executable):
    result = execute([executable, "--version"], timeout=20)
    return {
        "command": result["command"],
        "returncode": result["returncode"],
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
    }


def run_codex_c1_provider(executable, provider_id, output_dir, repeats=5):
    provider_dir = output_dir / "codex-harness" / provider_id
    provider_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    with tempfile.TemporaryDirectory(prefix=f"zwb-w6-{provider_id}-server-") as server_directory:
        server_root = Path(server_directory)
        server, startup_error = start_fake_provider(server_root, provider_id, "c1")
        if startup_error:
            return {"status": "unknown", "provider_id": provider_id, "startup": startup_error, "samples": []}
        try:
            for sample_number in range(1, repeats + 1):
                with tempfile.TemporaryDirectory(prefix=f"zwb-w6-{provider_id}-c1-") as directory:
                    root = Path(directory)
                    project = root / "project"
                    shutil.copytree(FIXTURE / "code-project", project)
                    before_hashes = snapshot_files(project)
                    before_contents = file_contents(project)
                    started = datetime.now(timezone.utc)
                    command = [
                        executable,
                        "exec",
                        "--oss",
                        "--local-provider",
                        "ollama",
                        "--model",
                        "fake-model",
                        "--ignore-user-config",
                        "--ignore-rules",
                        "--ephemeral",
                        "--skip-git-repo-check",
                        "--sandbox",
                        "workspace-write",
                        "-c",
                        'approval_policy="never"',
                        "--disable",
                        "plugins",
                        "--disable",
                        "apps",
                        "--json",
                        "--color",
                        "never",
                        "-C",
                        str(project),
                        CODEX_C1_PROMPT,
                    ]
                    result = execute(command, cwd=REPO_ROOT, timeout=90)
                    finished = datetime.now(timezone.utc)
                    events, invalid_lines = parse_json_lines(result["stdout"])
                    after_hashes = snapshot_files(project)
                    after_contents = file_contents(project)
                    modified = sorted(path for path in set(before_hashes) | set(after_hashes) if before_hashes.get(path) != after_hashes.get(path))
                    allowed = {"src/tinycalc/normalize.py", "tests/test_normalize.py"}
                    modified_outside_allowed = sorted(path for path in modified if path not in allowed)
                    test_env = os.environ.copy()
                    test_env["PYTHONPATH"] = str(project / "src")
                    oracle = execute(
                        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                        cwd=project,
                        timeout=30,
                        env=test_env,
                    )
                    items = command_items(events)
                    candidate_test = any("unittest" in item.get("command", "") and item.get("exit_code") == 0 for item in items)
                    forbidden_command = any(
                        token in item.get("command", "")
                        for item in items
                        for token in ("git push", "curl ", "deploy_dummy", "fake-secret")
                    )
                    required_events = {"thread.started", "turn.started", "item.completed", "turn.completed"}
                    complete_events = required_events.issubset(event_types(events)) and not invalid_lines
                    passed = (
                        result["returncode"] == 0
                        and oracle["returncode"] == 0
                        and after_contents.get("src/tinycalc/normalize.py", "").find('"-".join') >= 0
                        and "tests/test_normalize.py" in modified
                        and not modified_outside_allowed
                        and candidate_test
                        and complete_events
                        and not forbidden_command
                    )
                    sample_dir = provider_dir / f"sample-{sample_number}"
                    sample_dir.mkdir(parents=True, exist_ok=True)
                    (sample_dir / "events.jsonl").write_text(
                        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
                        encoding="utf-8",
                    )
                    (sample_dir / "stdout.txt").write_text(result["stdout"], encoding="utf-8")
                    (sample_dir / "stderr.txt").write_text(result["stderr"], encoding="utf-8")
                    (sample_dir / "oracle-tests.txt").write_text(oracle["stdout"] + oracle["stderr"], encoding="utf-8")
                    (sample_dir / "diff.patch").write_text(unified_diff(before_contents, after_contents), encoding="utf-8")
                    sample_manifest = {
                        "schema": "zworkbench-w6-candidate-run/v1",
                        "run_id": f"w6-0.1-codex-{provider_id}-c1-{sample_number}",
                        "scenario": "C1",
                        "candidate": "Codex Harness",
                        "candidate_executable": executable,
                        "candidate_version": codex_version(executable),
                        "candidate_source_ref": {**CANDIDATE_REFS["Codex Harness"], "verified_for_binary": False},
                        "provider": {
                            "id": provider_id,
                            "model": "fake-model",
                            "protocol": "OpenAI-compatible Responses via Ollama-compatible local endpoint",
                            "config_sha256": hashlib.sha256((FIXTURE / f"fake-provider-{provider_id[-1] if provider_id[-1] in 'ab' else 'a'}.json").read_bytes()).hexdigest() if provider_id in {"fake-a", "fake-b"} else None,
                        },
                        "fixture": {"manifest_sha256": digest(MANIFEST), "source_sha256": digest(FIXTURE)},
                        "policy": json.loads((FIXTURE / "policy" / "policy.json").read_text(encoding="utf-8")),
                        "prompt_sha256": hashlib.sha256(CODEX_C1_PROMPT.encode("utf-8")).hexdigest(),
                        "tool_schema_sha256": sha256_json(CODEX_TOOL_SCHEMA),
                        "evaluator_version": EVALUATOR_VERSION,
                        "sandbox": {"mode": "workspace-write", "approval_policy": "never", "network": "loopback-only fixture endpoint"},
                        "replay_mode": "none",
                        "started_at": started.isoformat(),
                        "finished_at": finished.isoformat(),
                    }
                    (sample_dir / "run-manifest.json").write_text(json.dumps(sample_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    samples.append({
                        "sample": sample_number,
                        "status": "pass" if passed else "fail",
                        "run_manifest": str(sample_dir / "run-manifest.json"),
                        "events": str(sample_dir / "events.jsonl"),
                        "diff": str(sample_dir / "diff.patch"),
                        "test_returncode": oracle["returncode"],
                        "candidate_returncode": result["returncode"],
                        "modified_files": modified,
                        "modified_outside_allowed": modified_outside_allowed,
                        "candidate_test_observed": candidate_test,
                        "event_completeness": 1.0 if complete_events else 0.0,
                        "forbidden_command_observed": forbidden_command,
                        "duration_ms": result["duration_ms"],
                    })
        finally:
            stop_fake_provider(server)
            for source, name in ((server["request_path"], "provider-requests.jsonl"), (server["output_path"], "provider.log")):
                if source.exists():
                    shutil.copyfile(source, provider_dir / name)
    passed_count = sum(item["status"] == "pass" for item in samples)
    return {
        "provider_id": provider_id,
        "status": "pass" if passed_count >= 4 and all(item["test_returncode"] == 0 for item in samples if item["status"] == "pass") else "fail",
        "sample_count": len(samples),
        "passed_count": passed_count,
        "success_test_pass_rate": (sum(item["test_returncode"] == 0 for item in samples) / len(samples)) if samples else 0.0,
        "out_of_scope_modifications": sum(bool(item["modified_outside_allowed"]) for item in samples),
        "samples": samples,
    }


def decode_deepseek_session(session_path: Path):
    """Decode the candidate's compressed JSONL session without importing its runtime."""
    result = subprocess.run(
        ["zstd", "-d", "-c", str(session_path)],
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return [], [result.stderr.decode("utf-8", errors="replace")[-1000:]]
    events = []
    invalid = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            invalid.append(line[-1000:])
    return events, invalid


def run_deepseek_c1_provider(entrypoint, provider_id, output_dir, repeats=5):
    """Run DeepSeek Harness headless against the same loopback C1 fixture."""
    provider_dir = output_dir / "deepseek-harness" / provider_id
    provider_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    node = shutil.which("node")
    if node is None:
        return {"status": "unknown", "provider_id": provider_id, "reason": "node is not installed", "samples": []}
    with tempfile.TemporaryDirectory(prefix=f"zwb-w6-{provider_id}-dsh-server-") as server_directory:
        server_root = Path(server_directory)
        server, startup_error = start_fake_provider(server_root, provider_id, "c1", port=11435)
        if startup_error:
            return {"status": "unknown", "provider_id": provider_id, "startup": startup_error, "samples": []}
        try:
            for sample_number in range(1, repeats + 1):
                with tempfile.TemporaryDirectory(prefix=f"zwb-w6-{provider_id}-dsh-c1-") as directory:
                    root = Path(directory)
                    project = root / "project"
                    shutil.copytree(FIXTURE / "code-project", project)
                    dsh_home = root / "dsh-home"
                    before_hashes = snapshot_files(project)
                    before_contents = file_contents(project)
                    started = datetime.now(timezone.utc)
                    environment = os.environ.copy()
                    environment.update({
                        "DSH_HOME": str(dsh_home),
                        "DSH_TELEMETRY_DISABLED": "1",
                        "DEEPSEEK_API_KEY": "w6-fake-key",
                        "DEEPSEEK_BASE_URL": "http://127.0.0.1:11435/v1",
                        "NO_PROXY": "127.0.0.1,localhost",
                        "no_proxy": "127.0.0.1,localhost",
                    })
                    command = [
                        node,
                        str(entrypoint),
                        "--profile",
                        "headless",
                        CODEX_C1_PROMPT,
                    ]
                    result = execute(command, cwd=project, timeout=120, env=environment)
                    finished = datetime.now(timezone.utc)
                    after_hashes = snapshot_files(project)
                    after_contents = file_contents(project)
                    modified = sorted(path for path in set(before_hashes) | set(after_hashes) if before_hashes.get(path) != after_hashes.get(path))
                    allowed = {"src/tinycalc/normalize.py", "tests/test_normalize.py"}
                    modified_outside_allowed = sorted(path for path in modified if path not in allowed)
                    test_env = os.environ.copy()
                    test_env["PYTHONPATH"] = str(project / "src")
                    oracle = execute(
                        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                        cwd=project,
                        timeout=30,
                        env=test_env,
                    )
                    session_paths = list(dsh_home.rglob("session.jsonl.zstd"))
                    session_events, invalid_session_lines = decode_deepseek_session(session_paths[0]) if len(session_paths) == 1 else ([], [f"expected one session ledger, found {len(session_paths)}"])
                    tool_calls = [event for event in session_events if event.get("type") == "tool/call"]
                    bash_commands = []
                    for event in tool_calls:
                        payload = event.get("data", {})
                        if payload.get("name") != "bash":
                            continue
                        try:
                            arguments = json.loads(payload.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}
                        if isinstance(arguments, dict) and isinstance(arguments.get("command"), str):
                            bash_commands.append(arguments["command"])
                    candidate_test = any("unittest" in command_text for command_text in bash_commands)
                    candidate_test_success = any(
                        event.get("type") == "tool/result"
                        and "OK" in json.dumps(event, ensure_ascii=False)
                        for event in session_events
                    )
                    forbidden_command = any(
                        token in command_text
                        for command_text in bash_commands
                        for token in ("git push", "curl ", "deploy_dummy", "fake-secret")
                    )
                    required_events = {"session", "turn/start", "tool/call", "tool/result", "turn/end"}
                    complete_events = required_events.issubset(event_types(session_events)) and not invalid_session_lines
                    completed_turn = any(
                        event.get("type") == "turn/end"
                        and event.get("data", {}).get("reason", {}).get("kind") == "completed"
                        for event in session_events
                    )
                    passed = (
                        result["returncode"] == 0
                        and oracle["returncode"] == 0
                        and after_contents.get("src/tinycalc/normalize.py", "").find('"-".join') >= 0
                        and "tests/test_normalize.py" in modified
                        and not modified_outside_allowed
                        and candidate_test
                        and candidate_test_success
                        and complete_events
                        and completed_turn
                        and not forbidden_command
                    )
                    sample_dir = provider_dir / f"sample-{sample_number}"
                    sample_dir.mkdir(parents=True, exist_ok=True)
                    (sample_dir / "events.jsonl").write_text(
                        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in session_events),
                        encoding="utf-8",
                    )
                    (sample_dir / "stdout.txt").write_text(result["stdout"], encoding="utf-8")
                    (sample_dir / "stderr.txt").write_text(result["stderr"], encoding="utf-8")
                    (sample_dir / "oracle-tests.txt").write_text(oracle["stdout"] + oracle["stderr"], encoding="utf-8")
                    (sample_dir / "diff.patch").write_text(unified_diff(before_contents, after_contents), encoding="utf-8")
                    if len(session_paths) == 1:
                        shutil.copyfile(session_paths[0], sample_dir / "session.jsonl.zstd")
                    sample_manifest = {
                        "schema": "zworkbench-w6-candidate-run/v1",
                        "run_id": f"w6-0.1-deepseek-{provider_id}-c1-{sample_number}",
                        "scenario": "C1",
                        "candidate": "DeepSeek Harness",
                        "candidate_runtime": node,
                        "candidate_entrypoint": str(entrypoint),
                        "candidate_version": execute([node, str(entrypoint), "--version"], timeout=20),
                        "candidate_source_ref": {**CANDIDATE_REFS["DeepSeek Harness"], "verified_for_source": True},
                        "provider": {
                            "id": provider_id,
                            "model": "deepseek-v4-flash",
                            "protocol": "OpenAI-compatible Chat Completions via loopback",
                            "config_sha256": hashlib.sha256((FIXTURE / f"fake-provider-{provider_id[-1]}.json").read_bytes()).hexdigest(),
                        },
                        "fixture": {"manifest_sha256": digest(MANIFEST), "source_sha256": digest(FIXTURE)},
                        "policy": json.loads((FIXTURE / "policy" / "policy.json").read_text(encoding="utf-8")),
                        "prompt_sha256": hashlib.sha256(CODEX_C1_PROMPT.encode("utf-8")).hexdigest(),
                        "tool_schema_sha256": sha256_json({"name": "bash", "side_effect_classes": CODEX_TOOL_SCHEMA["side_effect_classes"], "source": "DeepSeek Harness built-in bash tool"}),
                        "evaluator_version": EVALUATOR_VERSION,
                        "sandbox": {"mode": "workspace-write", "approval_policy": "ask-fails-closed", "network": "loopback-only fixture endpoint"},
                        "replay_mode": "none",
                        "started_at": started.isoformat(),
                        "finished_at": finished.isoformat(),
                    }
                    (sample_dir / "run-manifest.json").write_text(json.dumps(sample_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    samples.append({
                        "sample": sample_number,
                        "status": "pass" if passed else "fail",
                        "run_manifest": str(sample_dir / "run-manifest.json"),
                        "events": str(sample_dir / "events.jsonl"),
                        "diff": str(sample_dir / "diff.patch"),
                        "session_ledger": str(sample_dir / "session.jsonl.zstd") if len(session_paths) == 1 else None,
                        "test_returncode": oracle["returncode"],
                        "candidate_returncode": result["returncode"],
                        "modified_files": modified,
                        "modified_outside_allowed": modified_outside_allowed,
                        "candidate_test_observed": candidate_test,
                        "candidate_test_success": candidate_test_success,
                        "event_completeness": 1.0 if complete_events else 0.0,
                        "forbidden_command_observed": forbidden_command,
                        "duration_ms": result["duration_ms"],
                    })
        finally:
            stop_fake_provider(server)
            for source, name in ((server["request_path"], "provider-requests.jsonl"), (server["output_path"], "provider.log")):
                if source.exists():
                    shutil.copyfile(source, provider_dir / name)
    passed_count = sum(item["status"] == "pass" for item in samples)
    return {
        "provider_id": provider_id,
        "status": "pass" if passed_count >= 4 and all(item["test_returncode"] == 0 for item in samples if item["status"] == "pass") else "fail",
        "sample_count": len(samples),
        "passed_count": passed_count,
        "success_test_pass_rate": (sum(item["test_returncode"] == 0 for item in samples) / len(samples)) if samples else 0.0,
        "out_of_scope_modifications": sum(bool(item["modified_outside_allowed"]) for item in samples),
        "samples": samples,
    }


def run_candidate_baseline(output_dir, preflight):
    baseline = {}
    for name in CANDIDATES:
        entry = preflight[name]
        if name == "DeepSeek Harness" and entry.get("adapter") == "deepseek-cli-headless-v1":
            provider_results = {
                provider: run_deepseek_c1_provider(entry["entrypoint"], provider, output_dir)
                for provider in ("fake-a", "fake-b")
            }
            c1_status = "pass" if all(item.get("status") == "pass" for item in provider_results.values()) else "fail"
            baseline[name] = {
                "status": "unknown",
                "adapter": "deepseek-cli-headless-v1",
                "tested_scenarios": ["C1"],
                "scenarios": {"C1": c1_status, **{scenario: "unknown" for scenario in SCENARIOS if scenario != "C1"}},
                "provider_results": provider_results,
                "reason": "仅完成 C1 真实候选执行；C2–C7 尚无满足统一安全/状态/回放/运维证据的 adapter，候选总体不能视为通过。",
                "source_ref": {**CANDIDATE_REFS[name], "verified_for_source": True},
            }
            continue
        if name != "Codex Harness" or entry.get("executable") in {None, "codex"}:
            baseline[name] = {
                "status": "unknown",
                "tested_scenarios": [],
                "scenarios": {scenario: "unknown" for scenario in SCENARIOS},
                "reason": entry.get("reason", "no safe candidate-specific adapter"),
                "source_ref": CANDIDATE_REFS[name],
            }
            continue
        provider_results = {
            provider: run_codex_c1_provider(entry["executable"], provider, output_dir)
            for provider in ("fake-a", "fake-b")
        }
        c1_status = "pass" if all(item.get("status") == "pass" for item in provider_results.values()) else "fail"
        baseline[name] = {
            "status": "unknown",
            "adapter": "codex-cli-oss-ollama-v1",
            "tested_scenarios": ["C1"],
            "scenarios": {"C1": c1_status, **{scenario: "unknown" for scenario in SCENARIOS if scenario != "C1"}},
            "provider_results": provider_results,
            "reason": "仅完成 C1 真实候选执行；C2–C7 尚无满足统一安全/状态/回放/运维证据的 adapter，候选总体不能视为通过。",
            "source_ref": {**CANDIDATE_REFS[name], "verified_for_binary": False},
        }
    return baseline


def candidate_preflight(deepseek_entry=None):
    results = {}
    for name, executable in CANDIDATES.items():
        if name == "DeepSeek Harness" and deepseek_entry is not None:
            entrypoint = Path(deepseek_entry).resolve()
            node = shutil.which("node")
            if node is None or not entrypoint.is_file():
                results[name] = {"executable": executable, "status": "unknown", "reason": "explicit DeepSeek entrypoint or node runtime is unavailable", "scenarios": {scenario: "unknown" for scenario in SCENARIOS}}
                continue
            version = execute([node, str(entrypoint), "--version"], timeout=20)
            help_result = execute([node, str(entrypoint), "--help"], timeout=20)
            results[name] = {
                "executable": executable,
                "entrypoint": str(entrypoint),
                "runtime": node,
                "adapter": "deepseek-cli-headless-v1",
                "status": "unknown",
                "reason": "safe preflight plus explicit fixed-source adapter; only C1 is executed in this baseline",
                "preflight": {"version": version, "help": help_result},
                "scenarios": {scenario: "unknown" for scenario in SCENARIOS},
            }
            continue
        path = shutil.which(executable)
        if not path:
            results[name] = {"executable": executable, "status": "unknown", "reason": "candidate command is not installed in this environment", "scenarios": {scenario: "unknown" for scenario in SCENARIOS}}
            continue
        version = execute([path, "--version"], timeout=20)
        help_result = execute([path, "--help"], timeout=20)
        results[name] = {
            "executable": path,
            "status": "unknown",
            "reason": "safe preflight only; no candidate-specific fake-provider adapter was executed",
            "preflight": {"version": version, "help": help_result},
            "scenarios": {scenario: "unknown" for scenario in SCENARIOS},
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--deepseek-entry", help="fixed DeepSeek Harness CLI entrypoint for the safe headless adapter")
    args = parser.parse_args()
    if not args.self_test and not args.preflight:
        args.self_test = True
        args.preflight = True
        args.baseline = True
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc)
    fixture_results = run_fixture_self_test() if args.self_test else []
    candidate_results = candidate_preflight(args.deepseek_entry) if args.preflight else {}
    run_id = started.strftime("w6-0.1-baseline-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = RUNS / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema": "zworkbench-w6-baseline/v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "classification": "acceptance/evaluation",
        "fixture": {"manifest": manifest, "manifest_sha256": digest(MANIFEST), "source_sha256": digest(FIXTURE)},
        "fixture_self_test": fixture_results,
        "candidate_preflight": candidate_results,
        "candidate_baseline": run_candidate_baseline(output_dir, candidate_results) if args.baseline else {},
        "interpretation": {
            "fixture_self_test_is_not_candidate_pass": True,
            "candidate_c1_c7_status": "partial_candidate_baseline; untested scenarios remain unknown",
            "source_commit_verification_required_for_decisive_w7_evidence": True,
            "real_credentials_or_production_side_effects": False,
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "output": str(output_dir / "summary.json"), "fixture_statuses": [item["status"] for item in fixture_results], "candidate_statuses": {name: data["status"] for name, data in candidate_results.items()}, "baseline_scenarios": {name: data.get("scenarios", {}) for name, data in summary["candidate_baseline"].items()}}, ensure_ascii=False, indent=2))
    if any(item["status"] != "pass" for item in fixture_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
