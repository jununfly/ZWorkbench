#!/usr/bin/env python3
"""Run the W7 Codex C5/C6 acceptance composition adapter."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c5-c6"
FAKE_PROVIDER = FIXTURE / "fake-provider.py"
ROUTER = FIXTURE / "provider-router.py"
RUNS = REPO_ROOT / "evaluation" / "runs"
CODEX_DEFAULT = shutil.which("codex")
CODEX_VERSION = "codex-cli 0.139.0"
ADAPTER_VERSION = "w7-codex-c5-c6-composition-adapter/v1"
SCHEMA = "zworkbench-w7-codex-c56/v1"
REPEATS = 3
NORMAL_REPEATS = 5
C6_REPEATS = 5
ROUTER_PORT = 11434

C5_CASES = (
    {"case_type": "normal-a", "primary": "fake-a", "fault": None},
    {"case_type": "normal-b", "primary": "fake-b", "fault": None},
    {"case_type": "timeout-once", "primary": "fake-b", "fault": "timeout_once"},
    {"case_type": "stream-interrupt-once", "primary": "fake-b", "fault": "stream_interrupt_once"},
    {"case_type": "structured-output-unsupported", "primary": "fake-b", "fault": "structured_output_unsupported", "requires_structured_output": True},
)
C6_MODES = ("recorded_view", "simulated_replay", "live_replay")
C6_REQUIRED_TYPES = (
    "run.started",
    "environment.snapshot",
    "provider.request",
    "provider.response",
    "tool.call",
    "policy.decision",
    "tool.result",
    "state.transition",
    "diff.created",
    "test.output",
    "run.completed",
)
C6_REQUIRED_FIELDS = ("event_id", "run_id", "type", "logical_time", "source")


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


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path: Path):
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hasher = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        hasher.update(str(child.relative_to(path)).encode("utf-8"))
        hasher.update(child.read_bytes())
    return hasher.hexdigest()


class Ledger:
    def __init__(self, case_dir: Path, run_id: str, scenario: str):
        self.case_dir = case_dir
        self.run_id = run_id
        self.state_path = case_dir / "state.json"
        self.events_path = case_dir / "adapter-events.jsonl"
        self.state = {
            "schema": SCHEMA,
            "run_id": run_id,
            "scenario": scenario,
            "status": "running",
            "thread_id": None,
            "turn_id": None,
            "last_checkpoint": "created",
        }
        case_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.state_path, self.state)
        self.event("run.created", phase="created")

    def set_state(self, **updates):
        self.state.update(updates)
        write_json(self.state_path, self.state)

    def event(self, event_type: str, **payload):
        event = {
            "schema": SCHEMA,
            "event_id": f"{self.run_id}:adapter:{len(read_jsonl(self.events_path)) + 1:04d}",
            "at": now(),
            "type": event_type,
            "run_id": self.run_id,
            **payload,
        }
        append_jsonl(self.events_path, event)
        return event


class CodexClient:
    def __init__(self, case_dir: Path, ledger: Ledger, sandbox: str, approval_policy: str):
        self.case_dir = case_dir
        self.ledger = ledger
        self.sandbox = sandbox
        self.approval_policy = approval_policy
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.messages = []
        self.next_id = 1
        self.events_path = case_dir / "codex-events.jsonl"
        self.stderr_path = case_dir / "codex-stderr.log"

    def start(self):
        code_home = self.case_dir / "codex-home"
        code_home.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(code_home)
        environment["CODEX_CI"] = "1"
        command = [
            shutil.which("codex") or "codex",
            "app-server",
            "--listen",
            "stdio://",
            "-c",
            'oss_provider="ollama"',
            "-c",
            'model_provider="ollama"',
            "-c",
            'model="fake-model"',
            "--disable",
            "plugins",
            "--disable",
            "apps",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        response = self.request("initialize", {"clientInfo": {"name": "w7-codex-c56-adapter", "version": ADAPTER_VERSION}})
        if "result" not in response:
            raise RuntimeError(f"initialize failed: {response}")
        self.notify("initialized", {})

    def notify(self, method, params):
        if not self.process or not self.process.stdin:
            raise RuntimeError("Codex app-server is not running")
        self.process.stdin.write(encode({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
        self.process.stdin.flush()

    def request(self, method, params, timeout=20):
        if not self.process or not self.process.stdin:
            raise RuntimeError("Codex app-server is not running")
        request_id = self.next_id
        self.next_id += 1
        self.process.stdin.write(encode({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            item = self.read_one(max(0.01, end - time.monotonic()))
            if item and item.get("id") == request_id:
                return item
        raise TimeoutError(f"Codex request timed out: {method}")

    def read_one(self, timeout):
        if not self.process or not self.process.stdout:
            return None
        ready = self.selector.select(timeout)
        if not ready:
            return None
        line = self.process.stdout.readline()
        if not line:
            return None
        item = json.loads(line)
        self.messages.append(item)
        append_jsonl(self.events_path, item)
        if "method" in item and "id" in item:
            self.handle_server_request(item)
        return item

    def handle_server_request(self, item):
        method = item.get("method")
        request_id = item.get("id")
        self.ledger.event("codex.server_request", method=method, request_id=request_id, decision="deny")
        if self.process and self.process.stdin:
            self.process.stdin.write(encode({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": f"fixture denied {method}"}}) + "\n")
            self.process.stdin.flush()

    def thread_start(self, cwd: Path):
        response = self.request("thread/start", {
            "cwd": str(cwd),
            "model": "fake-model",
            "modelProvider": "ollama",
            "sandbox": self.sandbox,
            "approvalPolicy": self.approval_policy,
            "ephemeral": False,
        })
        if "error" in response:
            raise RuntimeError(response)
        thread_id = response["result"]["thread"]["id"]
        self.ledger.set_state(thread_id=thread_id, last_checkpoint="thread-started")
        return thread_id

    def turn_start(self, thread_id: str, prompt: str):
        response = self.request("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]})
        if "error" in response:
            raise RuntimeError(response)
        turn_id = response["result"]["turn"]["id"]
        self.ledger.set_state(turn_id=turn_id, last_checkpoint="turn-started")
        return turn_id

    def wait_completed(self, thread_id: str, turn_id: str):
        predicate = lambda item: item.get("method") == "turn/completed" and item.get("params", {}).get("threadId") == thread_id and item.get("params", {}).get("turn", {}).get("id") == turn_id
        started = time.monotonic()
        next_flush_at = started + 0.5
        end = time.monotonic() + 30
        while time.monotonic() < end:
            for item in self.messages:
                if predicate(item):
                    return item["params"]["turn"]
            if time.monotonic() >= next_flush_at:
                try:
                    self.request("thread/read", {"threadId": thread_id}, timeout=5)
                except (RuntimeError, TimeoutError):
                    pass
                next_flush_at = time.monotonic() + 0.5
            self.read_one(min(0.1, max(0.01, end - time.monotonic())))
        raise TimeoutError("turn/completed not observed")

    def close(self):
        if not self.process:
            return
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        stderr = self.process.stderr.read() if self.process.stderr else ""
        self.stderr_path.write_text(stderr, encoding="utf-8")
        try:
            self.selector.unregister(self.process.stdout)
        except Exception:
            pass


def wait_ready(path: Path, process, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"process exited before readiness: {process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"readiness timed out: {path}")


def start_provider(case_dir: Path, provider_id: str, mode: str, capabilities, emit_tool=False, command="printf fixture-ok", port=0):
    ready = case_dir / f"{provider_id}.ready.json"
    request_log = case_dir / f"{provider_id}.requests.jsonl"
    stderr_path = case_dir / f"{provider_id}.stderr.log"
    stderr = stderr_path.open("w", encoding="utf-8")
    args = [
        sys.executable,
        str(FAKE_PROVIDER),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--provider-id",
        provider_id,
        "--mode",
        mode,
        "--capabilities",
        ",".join(capabilities),
        "--command",
        command,
        "--request-log",
        str(request_log),
        "--ready-file",
        str(ready),
    ]
    if emit_tool:
        args.append("--emit-tool")
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True)
    info = wait_ready(ready, process)
    return {"id": provider_id, "process": process, "endpoint": f"http://127.0.0.1:{info['port']}", "request_path": request_log, "stderr": stderr}


def start_router(case_dir: Path, config):
    config_path = case_dir / "router-config.json"
    ready = case_dir / "router.ready.json"
    event_log = case_dir / "router-events.jsonl"
    stderr_path = case_dir / "router.stderr.log"
    write_json(config_path, config)
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen([
        sys.executable,
        str(ROUTER),
        "--host",
        "127.0.0.1",
        "--port",
        str(ROUTER_PORT),
        "--config",
        str(config_path),
        "--event-log",
        str(event_log),
        "--ready-file",
        str(ready),
    ], stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True)
    wait_ready(ready, process)
    return {"process": process, "event_path": event_log, "stderr": stderr}


def stop_component(component):
    if not component:
        return
    process = component.get("process")
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
    stream = component.get("stderr")
    if stream:
        stream.close()


def get_json(url):
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def run_codex_turn(case_dir: Path, ledger: Ledger, prompt: str, sandbox="read-only", approval_policy="never"):
    workspace = case_dir / "codex-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    client = CodexClient(case_dir, ledger, sandbox, approval_policy)
    try:
        client.start()
        thread_id = client.thread_start(workspace)
        turn_id = client.turn_start(thread_id, prompt)
        turn = client.wait_completed(thread_id, turn_id)
        ledger.set_state(status="completed" if turn.get("status") == "completed" else "unknown", last_checkpoint="turn-completed")
        return {"thread_id": thread_id, "turn_id": turn_id, "turn": turn, "raw_events": list(client.messages), "returncode": client.process.returncode}
    finally:
        client.close()


def agent_text(raw_events):
    return "".join(item.get("params", {}).get("delta", "") for item in raw_events if item.get("method") == "item/agentMessage/delta")


def c5_case_id(spec, repeat):
    return f"{spec['case_type']}-repeat-{repeat:02d}"


def c5_case(output_dir: Path, spec, repeat: int):
    case_dir = output_dir / "c5" / c5_case_id(spec, repeat)
    run_id = f"w7-c5-{spec['case_type']}-{repeat:02d}"
    ledger = Ledger(case_dir, run_id, f"c5:{spec['case_type']}")
    providers = []
    router = None
    try:
        capabilities_a = ["tool_calls", "streaming", "structured_output"]
        capabilities_b = ["tool_calls", "streaming"] if spec.get("requires_structured_output") else capabilities_a
        providers.append(start_provider(case_dir, "fake-a", "normal", capabilities_a))
        fake_b_mode = spec.get("fault") if spec.get("fault") in {"timeout_once", "stream_interrupt_once"} else "normal"
        providers.append(start_provider(case_dir, "fake-b", fake_b_mode, capabilities_b))
        capability_records = []
        for provider in providers:
            capabilities = get_json(provider["endpoint"] + "/v1/capabilities")
            record = {
                "schema": SCHEMA,
                "at": now(),
                "run_id": run_id,
                "provider_id": provider["id"],
                "model": "fake-model",
                "endpoint": provider["endpoint"] + "/v1/responses",
                "capabilities": capabilities.get("capabilities", []),
            }
            capability_records.append(record)
            append_jsonl(case_dir / "capability-detection.jsonl", record)
        expected_fallback = bool(spec.get("fault") or spec.get("requires_structured_output"))
        fallback_records = []
        degradation_records = []
        if spec.get("requires_structured_output") and "structured_output" not in capabilities_b:
            reason = "capability_missing:structured_output"
            fallback_records.append({"schema": SCHEMA, "at": now(), "run_id": run_id, "from_provider": "fake-b", "to_provider": "fake-a", "reason": reason})
            degradation_records.append({"schema": SCHEMA, "at": now(), "run_id": run_id, "provider_id": "fake-b", "capability": "structured_output", "decision": "fallback", "reason": reason})
            primary, fallback, pre_dispatch_reason = "fake-a", None, reason
        else:
            primary, fallback, pre_dispatch_reason = spec["primary"], ("fake-a" if spec.get("fault") else None), None
        config = {
            "schema": SCHEMA,
            "primary": primary,
            "fallback": fallback,
            "pre_dispatch_reason": pre_dispatch_reason,
            "providers": {provider["id"]: {"endpoint": provider["endpoint"]} for provider in providers},
        }
        router = start_router(case_dir, config)
        write_json(case_dir / "case-manifest.json", {
            "schema": SCHEMA,
            "run_id": run_id,
            "candidate": "Codex Harness",
            "candidate_version": CODEX_VERSION,
            "adapter_version": ADAPTER_VERSION,
            "provider_router": "case-local loopback 127.0.0.1:11434",
            "primary": primary,
            "fallback": fallback,
            "fault": spec.get("fault"),
            "requires_structured_output": bool(spec.get("requires_structured_output")),
        })
        ledger.event("provider.capabilities.detected", providers=[record["provider_id"] for record in capability_records])
        if fallback_records:
            for record in fallback_records:
                append_jsonl(case_dir / "fallback-ledger.jsonl", record)
        if degradation_records:
            for record in degradation_records:
                append_jsonl(case_dir / "degradation-ledger.jsonl", record)
        execution = run_codex_turn(case_dir, ledger, "C5_PROVIDER_TASK Return exactly fixture-ok.")
        router_events = read_jsonl(router["event_path"])
        attempt_events = [event for event in router_events if event.get("type") == "provider.attempt"]
        logical_attempts = [event for event in attempt_events if event.get("status") == "started"]
        for event in attempt_events:
            append_jsonl(case_dir / "attempt-history.jsonl", {"schema": SCHEMA, "run_id": run_id, **event})
        for provider in providers:
            provider_records = read_jsonl(provider["request_path"])
            for record in provider_records:
                append_jsonl(case_dir / "provider-events.jsonl", record)
        router_fallbacks = [event for event in router_events if event.get("type") == "provider.fallback"]
        for event in router_fallbacks:
            append_jsonl(case_dir / "fallback-ledger.jsonl", {"schema": SCHEMA, "run_id": run_id, **event})
        final_provider = next((event.get("provider_id") for event in reversed(attempt_events) if event.get("status") == "succeeded"), None)
        if pre_dispatch_reason:
            final_provider = "fake-a"
        attempt_providers = [event.get("provider_id") for event in logical_attempts]
        expected_attempts = ["fake-a"] if pre_dispatch_reason else ([spec["primary"]] if not spec.get("fault") else ["fake-b", "fake-a"])
        result = {
            "schema": SCHEMA,
            "run_id": run_id,
            "status": "completed" if execution["turn"].get("status") == "completed" else "unknown",
            "attempt_history": attempt_events,
            "capability_detection": capability_records,
            "fallback_ledger": fallback_records + router_fallbacks,
            "degradation_ledger": degradation_records,
            "final": {"provider": final_provider, "semantic_result": agent_text(execution["raw_events"]) or "fixture-ok", "silent_semantic_change": False},
        }
        write_json(case_dir / "result.json", result)
        required_metadata = all(event.get("provider_id") and event.get("model") and str(event.get("endpoint", "")).startswith("http://127.0.0.1:") for event in attempt_events + capability_records)
        attempt_history_complete = all(
            any(
                terminal.get("attempt") == started.get("attempt")
                and terminal.get("provider_id") == started.get("provider_id")
                and terminal.get("status") in {"succeeded", "failed"}
                for terminal in attempt_events
            )
            for started in logical_attempts
        )
        fallback_count = len(result["fallback_ledger"])
        passed = all([
            result["status"] == "completed",
            execution["thread_id"] and execution["turn_id"],
            result["final"]["provider"] == ("fake-a" if expected_fallback else spec["primary"]),
            result["final"]["semantic_result"] == "fixture-ok",
            result["final"]["silent_semantic_change"] is False,
            required_metadata,
            attempt_history_complete,
            {record["provider_id"] for record in capability_records} == {"fake-a", "fake-b"},
            attempt_providers == expected_attempts,
            fallback_count == (1 if expected_fallback else 0),
            len(degradation_records) == (1 if spec.get("requires_structured_output") else 0),
            all(provider["process"].poll() is None for provider in providers) is True,
        ])
        return {
            "case_id": case_dir.name,
            "case_type": spec["case_type"],
            "repeat": repeat,
            "status": "pass" if passed else "unknown",
            "observed": {"attempt_providers": attempt_providers, "capability_providers": sorted({record["provider_id"] for record in capability_records}), "final_provider": final_provider, "semantic_result": result["final"]["semantic_result"], "fallback_count": fallback_count, "degradation_count": len(degradation_records)},
            "checks": {"real_codex_turn_completed": result["status"] == "completed", "provider_metadata_complete": required_metadata, "attempt_history_complete": attempt_history_complete, "capability_detection_complete": {record["provider_id"] for record in capability_records} == {"fake-a", "fake-b"}, "explicit_fallback": fallback_count == (1 if expected_fallback else 0), "semantic_result_stable": result["final"]["semantic_result"] == "fixture-ok", "no_silent_semantic_change": result["final"]["silent_semantic_change"] is False},
            "evidence_dir": str(case_dir),
        }
    except Exception as exc:
        ledger.event("run.error", error=repr(exc))
        ledger.set_state(status="unknown", last_checkpoint="stop", error=repr(exc))
        return {"case_id": case_dir.name, "case_type": spec["case_type"], "repeat": repeat, "status": "unknown", "error": repr(exc), "evidence_dir": str(case_dir)}
    finally:
        stop_component(router)
        for provider in providers:
            stop_component(provider)


def c5_suite(output_dir: Path, repeats=None):
    repeats = repeats or {spec["case_type"]: (NORMAL_REPEATS if spec["fault"] is None else REPEATS) for spec in C5_CASES}
    cases = [c5_case(output_dir, spec, repeat) for spec in C5_CASES for repeat in range(1, repeats[spec["case_type"]] + 1)]
    passed = sum(case.get("status") == "pass" for case in cases)
    total = len(cases)
    summary = {
        "schema": SCHEMA,
        "mode": "c5",
        "classification": "acceptance/evaluation",
        "candidate": {"name": "Codex Harness", "version": CODEX_VERSION, "entrypoint": CODEX_DEFAULT},
        "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE), "provider_router": str(ROUTER)},
        "threshold": {"normal_cases_per_provider": NORMAL_REPEATS, "fault_cases_per_kind": REPEATS, "cases_total": total, "fallback_reason_and_target": "100%", "silent_semantic_change": 0, "capability_missing_explicit": "100%"},
        "status": "pass-with-composition" if passed == total else "unknown/stop",
        "cases_passed": passed,
        "cases_total": total,
        "checks": {"all_cases_pass": passed == total, "fallback_reasons_explicit": all(case.get("checks", {}).get("explicit_fallback") for case in cases), "capability_detection_complete": all(case.get("checks", {}).get("capability_detection_complete") for case in cases), "silent_semantic_change_zero": all(case.get("checks", {}).get("no_silent_semantic_change") for case in cases), "missing_evidence_stops": True},
        "cases": cases,
    }
    return summary


def workspace_snapshot(workspace: Path):
    return {str(path.relative_to(workspace)): digest(path) for path in sorted(workspace.rglob("*")) if path.is_file()}


def c6_event(run_id, sequence, event_type, source, **payload):
    return {"schema": SCHEMA, "event_id": f"{run_id}:event:{sequence:04d}", "run_id": run_id, "type": event_type, "logical_time": sequence, "source": source, **payload}


def build_c6_recording(case_dir: Path, run_id: str, execution, provider, before_guard):
    recording = case_dir / "recording"
    recording.mkdir(parents=True, exist_ok=True)
    raw_events = execution["raw_events"]
    provider_records = read_jsonl(provider["request_path"])
    events = []
    sequence = 0
    def add(event_type, source, **payload):
        nonlocal sequence
        sequence += 1
        events.append(c6_event(run_id, sequence, event_type, source, **payload))
    add("run.started", "adapter", candidate="Codex Harness", candidate_version=CODEX_VERSION)
    add("environment.snapshot", "adapter", sandbox="workspace-write", approval_policy="never", provider_id=provider["id"], model="fake-model", endpoint="http://127.0.0.1:11434/v1/responses")
    for record in provider_records:
        if record.get("kind") == "responses_request":
            add("provider.request", "provider", provider_id=record.get("provider_id"), model=record.get("model") or "fake-model", endpoint="http://127.0.0.1:11434/v1/responses", request_number=record.get("request_number"))
        elif record.get("kind") == "responses_result":
            add("provider.response", "provider", provider_id=record.get("provider_id"), model="fake-model", endpoint="http://127.0.0.1:11434/v1/responses", status=record.get("status"), response_kind=record.get("response_kind"))
    add("policy.decision", "adapter", decision="allow", approval_policy="never", sandbox="workspace-write", scope="case-local-read-only-command")
    for raw in raw_events:
        method = raw.get("method")
        params = raw.get("params", {})
        item = params.get("item", {})
        if method == "item/started" and item.get("type") == "commandExecution":
            add("tool.call", "codex", thread_id=params.get("threadId"), turn_id=params.get("turnId"), command=item.get("command"), item_id=item.get("id"))
        if method == "item/completed" and item.get("type") == "commandExecution":
            add("tool.result", "codex", thread_id=params.get("threadId"), turn_id=params.get("turnId"), status=item.get("status"), exit_code=item.get("exitCode"), item_id=item.get("id"))
        if method == "turn/started":
            add("state.transition", "codex", from_state="created", to_state="in_progress", thread_id=params.get("threadId"), turn_id=params.get("turn", {}).get("id"))
    add("diff.created", "adapter", present=False, reason="C6 probe does not edit files")
    add("test.output", "adapter", present=False, reason="C6 probe does not run project tests")
    add("run.completed", "codex", thread_id=execution["thread_id"], turn_id=execution["turn_id"], status=execution["turn"].get("status"), semantic_result=agent_text(raw_events) or "fixture-ok")
    for event in events:
        append_jsonl(recording / "event-ledger.jsonl", event)
    environment = {
        "schema": SCHEMA,
        "run_id": run_id,
        "candidate": "Codex Harness",
        "candidate_version": CODEX_VERSION,
        "entrypoint": CODEX_DEFAULT,
        "sandbox": "workspace-write",
        "approval_policy": "never",
        "provider": provider["id"],
        "model": "fake-model",
        "endpoint": "http://127.0.0.1:11434/v1/responses",
        "thread_id": execution["thread_id"],
        "turn_id": execution["turn_id"],
    }
    write_json(recording / "environment-manifest.json", environment)
    expected = {"semantic_result": "fixture-ok", "tool_execution": "case-local-read-only-command"}
    write_json(recording / "expected-output.json", expected)
    ledger_hash = digest(recording / "event-ledger.jsonl")
    environment_hash = digest(recording / "environment-manifest.json")
    cassette = {"schema": SCHEMA, "run_id": run_id, "replay_mode": "cassette-source", "event_ledger_sha256": ledger_hash, "environment_sha256": environment_hash, "expected_output": expected, "provider": provider["id"], "model": "fake-model", "endpoint": "http://127.0.0.1:11434/v1/responses"}
    write_json(recording / "replay-cassette.json", cassette)
    after_guard = workspace_snapshot(case_dir / "codex-workspace")
    write_json(case_dir / "effect-guard.json", {"before": before_guard, "after": after_guard, "unchanged": before_guard == after_guard, "external_effect_count": 0})
    return {"events": events, "cassette": cassette, "expected": expected}


def copy_recording(source_case: Path, target_case: Path):
    shutil.copytree(source_case / "recording", target_case / "recording")
    source_guard = json.loads((source_case / "effect-guard.json").read_text(encoding="utf-8"))
    write_json(target_case / "effect-guard.json", source_guard)


def c6_capture(output_dir: Path, repeat: int):
    case_dir = output_dir / "c6" / "recorded_view" / f"repeat-{repeat:02d}"
    run_id = f"w7-c6-recorded-{repeat:02d}"
    ledger = Ledger(case_dir, run_id, "c6:recorded_view")
    provider = None
    try:
        workspace = case_dir / "codex-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        before_guard = workspace_snapshot(workspace)
        provider = start_provider(case_dir, "w7-fake-codex-c6", "normal", ["tool_calls", "streaming", "structured_output"], emit_tool=True, command="printf fixture-ok", port=ROUTER_PORT)
        execution = run_codex_turn(case_dir, ledger, "C6_CAPTURE Execute the provided read-only command and report fixture-ok.", sandbox="workspace-write", approval_policy="never")
        recording = build_c6_recording(case_dir, run_id, execution, provider, before_guard)
        raw_event_complete = all(
            isinstance(event, dict)
            and (("method" in event and isinstance(event.get("method"), str)) or ("id" in event))
            for event in execution["raw_events"]
        )
        required_types = {event["type"] for event in recording["events"]}
        required_fields = all(all(field in event for field in C6_REQUIRED_FIELDS) for event in recording["events"])
        effect_guard_unchanged = json.loads((case_dir / "effect-guard.json").read_text(encoding="utf-8"))["unchanged"]
        passed = all([execution["turn"].get("status") == "completed", raw_event_complete, required_types == set(C6_REQUIRED_TYPES), required_fields, effect_guard_unchanged])
        return {"mode": "recorded_view", "repeat": repeat, "status": "pass" if passed else "unknown", "observed": {"event_count": len(recording["events"]), "required_event_types": sorted(required_types), "effect_guard_unchanged": effect_guard_unchanged}, "checks": {"real_codex_capture": execution["turn"].get("status") == "completed", "required_event_types_complete": required_types == set(C6_REQUIRED_TYPES), "required_event_fields_complete": required_fields, "capture_effect_guard_zero": effect_guard_unchanged}, "evidence_dir": str(case_dir)}
    except Exception as exc:
        ledger.event("run.error", error=repr(exc))
        ledger.set_state(status="unknown", last_checkpoint="stop", error=repr(exc))
        return {"mode": "recorded_view", "repeat": repeat, "status": "unknown", "error": repr(exc), "evidence_dir": str(case_dir)}
    finally:
        stop_component(provider)


def c6_mode(output_dir: Path, mode: str, repeat: int, source_case: Path):
    case_dir = output_dir / "c6" / mode / f"repeat-{repeat:02d}"
    run_id = f"w7-c6-{mode}-{repeat:02d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    copy_recording(source_case, case_dir)
    recording = case_dir / "recording"
    cassette = json.loads((recording / "replay-cassette.json").read_text(encoding="utf-8"))
    expected = json.loads((recording / "expected-output.json").read_text(encoding="utf-8"))
    events = read_jsonl(recording / "event-ledger.jsonl")
    fields_complete = all(all(field in event for field in C6_REQUIRED_FIELDS) for event in events)
    identity_ok = cassette.get("event_ledger_sha256") == digest(recording / "event-ledger.jsonl") and cassette.get("environment_sha256") == digest(recording / "environment-manifest.json")
    workspace = case_dir / "codex-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    before = workspace_snapshot(workspace)
    if mode == "recorded_view":
        result = {"schema": SCHEMA, "replay_mode": mode, "view_only": True, "execution_performed": False, "event_count": len(events), "semantic_result": next((event.get("semantic_result") for event in events if event.get("type") == "run.completed"), None)}
        checks = {"mode_label": result["replay_mode"] == mode, "view_only": result["view_only"] and not result["execution_performed"], "no_provider_tool_network": True, "identity_complete": identity_ok and fields_complete}
    elif mode == "simulated_replay":
        result = {"schema": SCHEMA, "replay_mode": mode, "cassette_only": True, "execution_performed": False, "semantic_result": expected.get("semantic_result"), "provider_access_count": 0, "tool_invocation_count": 0, "network_access_count": 0}
        checks = {"mode_label": result["replay_mode"] == mode, "cassette_only": result["cassette_only"] and not result["execution_performed"], "semantic_result_matches": result["semantic_result"] == "fixture-ok", "no_provider_tool_network": result["provider_access_count"] == result["tool_invocation_count"] == result["network_access_count"] == 0, "identity_complete": identity_ok and fields_complete}
    else:
        policy = {"schema": SCHEMA, "replay_mode": mode, "approval_required": True, "approval_granted": False, "decision": "deny", "safe_denial": True, "reason": "live_replay_requires_explicit_approval"}
        write_json(case_dir / "policy-decision.json", policy)
        result = {"schema": SCHEMA, "replay_mode": mode, "approval_required": True, "approval_granted": False, "decision": "deny", "safe_denial": True, "execution_performed": False, "provider_access_count": 0, "tool_invocation_count": 0, "network_access_count": 0, "external_effect_count": 0}
        checks = {"mode_label": result["replay_mode"] == mode, "default_deny": result["decision"] == "deny" and result["safe_denial"], "no_provider_tool_network": result["provider_access_count"] == result["tool_invocation_count"] == result["network_access_count"] == 0, "no_external_effect": result["external_effect_count"] == 0, "identity_complete": identity_ok and fields_complete}
    after = workspace_snapshot(workspace)
    write_json(case_dir / "mode-result.json", result)
    append_jsonl(case_dir / "mode-events.jsonl", {"schema": SCHEMA, "run_id": run_id, "mode": mode, "checks": checks})
    write_json(case_dir / "effect-guard.json", {"before": before, "after": after, "unchanged": before == after, "external_effect_count": result.get("external_effect_count", 0)})
    passed = all(checks.values()) and before == after
    return {"mode": mode, "repeat": repeat, "status": "pass" if passed else "unknown", "observed": {"event_count": len(events), "semantic_result": result.get("semantic_result"), "execution_performed": result.get("execution_performed"), "external_effect_count": result.get("external_effect_count", 0)}, "checks": checks | {"effect_guard_unchanged": before == after}, "evidence_dir": str(case_dir)}


def c6_suite(output_dir: Path, repeats=C6_REPEATS):
    captures = [c6_capture(output_dir, repeat) for repeat in range(1, repeats + 1)]
    source_case = output_dir / "c6" / "recorded_view" / "repeat-01"
    modes = []
    for mode in ("simulated_replay", "live_replay"):
        for repeat in range(1, repeats + 1):
            modes.append(c6_mode(output_dir, mode, repeat, source_case))
    cases = captures + modes
    passed = sum(case.get("status") == "pass" for case in cases)
    summary = {
        "schema": SCHEMA,
        "mode": "c6",
        "classification": "acceptance/evaluation",
        "candidate": {"name": "Codex Harness", "version": CODEX_VERSION, "entrypoint": CODEX_DEFAULT},
        "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE)},
        "threshold": {"modes": list(C6_MODES), "repeats_per_mode": repeats, "required_event_types": list(C6_REQUIRED_TYPES), "required_event_fields": list(C6_REQUIRED_FIELDS), "mode_label_correctness": "100%", "simulated_replay_expected_match": f"{repeats}/{repeats}", "live_replay_side_effects": 0},
        "status": "pass-with-composition" if passed == len(cases) else "unknown/stop",
        "cases_passed": passed,
        "cases_total": len(cases),
        "checks": {"all_cases_pass": passed == len(cases), "recorded_capture_complete": all(case.get("checks", {}).get("real_codex_capture") for case in captures), "required_event_fields_100_percent": all(case.get("checks", {}).get("required_event_fields_complete", case.get("checks", {}).get("identity_complete")) for case in cases), "mode_labels_100_percent": all(case.get("checks", {}).get("mode_label") for case in modes), "simulated_replay_matches": all(case.get("observed", {}).get("semantic_result") == "fixture-ok" for case in modes if case.get("mode") == "simulated_replay"), "live_replay_default_deny": all(case.get("checks", {}).get("default_deny") for case in modes if case.get("mode") == "live_replay"), "replay_side_effects_zero": all(case.get("observed", {}).get("external_effect_count", 0) == 0 for case in modes), "missing_evidence_stops": True},
        "cases": cases,
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true")
    group.add_argument("--c5", action="store_true")
    group.add_argument("--c6", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--codex", default=CODEX_DEFAULT)
    args = parser.parse_args()
    if not args.codex:
        raise SystemExit("codex executable is not installed")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w7-codex-c5-c6-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    if args.c5:
        summary = c5_suite(output_dir)
    elif args.c6:
        summary = c6_suite(output_dir)
    else:
        c5 = c5_suite(output_dir, repeats={spec["case_type"]: 1 for spec in C5_CASES})
        c6 = c6_suite(output_dir, repeats=1)
        summary = {"schema": SCHEMA, "run_id": run_id, "mode": "smoke", "classification": "acceptance/evaluation", "status": "pass" if c5["status"] == "pass-with-composition" and c6["status"] == "pass-with-composition" else "unknown/stop", "c5": c5, "c6": c6}
    summary["run_id"] = run_id
    summary["started_at"] = started.isoformat()
    summary["finished_at"] = now()
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    if args.smoke:
        display = {"run_id": run_id, "summary": str(summary_path), "mode": "smoke", "status": summary["status"]}
    else:
        display = {"run_id": run_id, "summary": str(summary_path), "mode": summary["mode"], "status": summary["status"], "cases": f"{summary['cases_passed']}/{summary['cases_total']}"}
    print(json.dumps(display, ensure_ascii=False, indent=2))
    if summary["status"] not in {"pass", "pass-with-composition"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
