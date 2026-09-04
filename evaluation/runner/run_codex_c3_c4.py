#!/usr/bin/env python3
"""Run the W7 Codex C3/C4 composition-adapter evaluation.

This runner is deliberately an acceptance/evaluation artifact.  It starts the
fixed local Codex CLI/app-server entrypoint against a loopback-only fake
Responses provider and a case-local effect sink.  The external adapter owns
the schedule, attempt, state, result, and reconciliation ledgers.  It does
not modify ZWorkbench product code and never contacts a real Provider.
"""

from __future__ import annotations

import argparse
import json
import os
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c3-c4"
EFFECT_SINK = FIXTURE / "effect-sink.py"
FAKE_PROVIDER = FIXTURE / "fake-provider.py"
RUNS = REPO_ROOT / "evaluation" / "runs"
CODEX_DEFAULT = shutil.which("codex")
CODEX_VERSION = "codex-cli 0.139.0"
ADAPTER_VERSION = "w7-codex-c3-c4-composition-adapter/v1"
SCHEMA = "zworkbench-w7-codex-c34/v1"

C3_SCENARIOS = {
    "first_trigger": ["trigger:first"],
    "same_key_duplicate": ["trigger:first", "trigger:duplicate"],
    "delayed_trigger": ["trigger:first", "trigger:delayed"],
    "interrupted_retry": ["trigger:interrupted", "resume:resume-after-interrupt", "trigger:duplicate-after-resume"],
    "missed_trigger": ["trigger:missed"],
}
C4_FAULTS = ("turn_interrupt", "provider_timeout", "tool_timeout", "process_interrupt")
C4_TOOL_CLASSES = ("read-only", "idempotent", "approval-required")
REPEATS = 3
WATCHDOG_SECONDS = 0.35
TOOL_INTERRUPT_SECONDS = 0.15


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with temporary.open("r+", encoding="utf-8") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class CaseLedger:
    """The one external durable owner used by the composition adapter."""

    def __init__(self, case_dir: Path, run_id: str, schedule_id: str, idempotency_key: str, scenario: str):
        self.case_dir = case_dir
        self.run_id = run_id
        self.schedule_id = schedule_id
        self.idempotency_key = idempotency_key
        self.state_path = case_dir / "state.json"
        self.events_path = case_dir / "events.jsonl"
        self.attempts_path = case_dir / "attempts.jsonl"
        self.schedule_path = case_dir / "schedule.jsonl"
        self.faults_path = case_dir / "faults.jsonl"
        self.results_path = case_dir / "results.jsonl"
        self.effects_path = case_dir / "effects.jsonl"
        self.tool_results_path = case_dir / "tool-results.jsonl"
        self.state = {
            "schema": SCHEMA,
            "run_id": run_id,
            "schedule_id": schedule_id,
            "idempotency_key": idempotency_key,
            "scenario": scenario,
            "thread_id": None,
            "turn_id": None,
            "phase": "created",
            "status": "running",
            "retry_count": 0,
            "last_checkpoint": "created",
            "effect_status": "unknown",
            "result_status": "unknown",
            "safe_stop_reason": None,
        }
        case_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.state_path, self.state)
        self.event("run.created", phase="created")

    def refresh_state(self):
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        return self.state

    def set_state(self, **updates):
        self.state.update(updates)
        write_json(self.state_path, self.state)

    def event(self, event_type: str, **payload):
        self.refresh_state()
        event = {
            "schema": SCHEMA,
            "seq": len(read_jsonl(self.events_path)) + 1,
            "at": now(),
            "type": event_type,
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "thread_id": self.state.get("thread_id"),
            "turn_id": self.state.get("turn_id"),
            **payload,
        }
        append_jsonl(self.events_path, event)
        if event_type == "fault.injected":
            append_jsonl(self.faults_path, event)
        return event

    def schedule(self, trigger_kind: str, *, missed=False, late=False):
        record = {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "trigger_kind": trigger_kind,
            "missed": missed,
            "late": late,
            "delivery_semantics": "run-once-late" if missed else "deliver-once",
        }
        append_jsonl(self.schedule_path, record)
        self.event("schedule.triggered", trigger_kind=trigger_kind, missed=missed, late=late)

    def attempt(self, attempt_id: str, mode: str, phase: str, outcome: str):
        record = {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "attempt_id": attempt_id,
            "mode": mode,
            "phase": phase,
            "outcome": outcome,
            "thread_id": self.state.get("thread_id"),
            "turn_id": self.state.get("turn_id"),
        }
        append_jsonl(self.attempts_path, record)
        self.event("attempt." + phase, attempt_id=attempt_id, mode=mode, outcome=outcome)

    def finish_result(self, outcome: str, **payload):
        result = {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "outcome": outcome,
            "thread_id": self.state.get("thread_id"),
            "turn_id": self.state.get("turn_id"),
            **payload,
        }
        append_jsonl(self.results_path, result)
        self.set_state(result_status="completed", last_checkpoint="result-recorded")
        self.event("result.recorded", outcome=outcome, **payload)


class AppServer:
    """Small JSON-RPC client for the fixed Codex app-server stdio surface."""

    def __init__(self, executable: str, case_dir: Path, code_home: Path, ledger: CaseLedger, expected_command: str, approval_required: bool):
        self.executable = executable
        self.case_dir = case_dir
        self.code_home = code_home
        self.ledger = ledger
        self.expected_command = expected_command
        self.approval_required = approval_required
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.messages = []
        self.next_id = 1
        self.stderr_path = case_dir / "codex-stderr.log"

    def start(self):
        env = os.environ.copy()
        # CODEX_HOME is intentionally case-local so Codex thread/rollout state
        # cannot mix with the operator's normal Codex history.
        env["CODEX_HOME"] = str(self.code_home)
        env["CODEX_CI"] = "1"
        command = [
            self.executable,
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
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        response = self.request("initialize", {"clientInfo": {"name": "w7-codex-c3-c4-adapter", "version": ADAPTER_VERSION}})
        if "result" not in response:
            raise RuntimeError(f"Codex initialize failed: {response}")
        self.notify("initialized", {})
        return response

    def notify(self, method: str, params):
        if not self.process or not self.process.stdin:
            raise RuntimeError("app-server is not running")
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write(encode(message) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params, timeout=15):
        if not self.process or not self.process.stdin:
            raise RuntimeError("app-server is not running")
        request_id = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self.process.stdin.write(encode(message) + "\n")
        self.process.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            item = self.read_one(max(0.01, end - time.monotonic()))
            if item is None:
                continue
            if item.get("id") == request_id:
                return item
        raise TimeoutError(f"Codex request timed out: {method}")

    def read_one(self, timeout):
        if self.process is None or self.process.stdout is None:
            return None
        ready = self.selector.select(timeout)
        if not ready:
            return None
        line = self.process.stdout.readline()
        if not line:
            return None
        item = json.loads(line)
        self.messages.append(item)
        append_jsonl(self.case_dir / "codex-events.jsonl", item)
        if "method" in item and "id" in item:
            self.handle_server_request(item)
        return item

    def handle_server_request(self, item):
        method = item.get("method")
        params = item.get("params") or {}
        request_id = item.get("id")
        if method == "item/commandExecution/requestApproval":
            command = params.get("command") or ""
            allowed = self.command_is_allowlisted(command)
            self.ledger.event(
                "codex.approval.requested",
                approval_request_id=request_id,
                command=command,
                decision="accept" if allowed else "decline",
                approval_scope="one-command-one-run" if allowed else "fail-closed",
            )
            self.respond(request_id, {"decision": "accept" if allowed else "decline"})
            return
        # Any unrecognized server-side request is denied at the protocol
        # boundary.  This keeps the fixture from silently widening its scope.
        self.ledger.event("codex.server_request.denied", request_id=request_id, method=method, params=params)
        self.respond_error(request_id, -32001, f"unsupported server request: {method}")

    def command_is_allowlisted(self, command: str):
        if not command or "effect-sink.py" not in command:
            return False
        forbidden = ("git ", "curl ", "wget ", "rm ", "sudo ", "deploy", "fake-secret", "http://", "https://")
        if any(token in command for token in forbidden):
            return False
        # The wrapper may be `/bin/zsh -lc '...'`; checking the exact operation
        # and key is more stable than depending on that shell wrapper spelling.
        try:
            expected_shell_command = json.loads(self.expected_command)["cmd"]
            expected_tokens = shlex.split(expected_shell_command)
        except (KeyError, json.JSONDecodeError, ValueError):
            return False
        return all(token in command for token in expected_tokens)

    def respond(self, request_id, result):
        self.process.stdin.write(encode({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        self.process.stdin.flush()

    def respond_error(self, request_id, code, message):
        self.process.stdin.write(encode({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}) + "\n")
        self.process.stdin.flush()

    def wait_for(self, predicate, timeout=30, start=0):
        for item in self.messages[start:]:
            if predicate(item):
                return item
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            item = self.read_one(max(0.01, end - time.monotonic()))
            if item is not None and predicate(item):
                return item
        raise TimeoutError("Codex event wait timed out")

    def thread_start(self, cwd: Path, approval_policy: str):
        response = self.request(
            "thread/start",
            {
                "cwd": str(cwd),
                "model": "fake-model",
                "modelProvider": "ollama",
                "sandbox": "workspace-write",
                "approvalPolicy": approval_policy,
                "ephemeral": False,
            },
        )
        if "error" in response:
            raise RuntimeError(response)
        thread_id = response["result"]["thread"]["id"]
        self.ledger.set_state(thread_id=thread_id, phase="thread-started", last_checkpoint="thread-started")
        self.ledger.event("codex.thread.started", codex_thread_id=thread_id, model_provider="ollama", model="fake-model")
        return thread_id

    def thread_resume(self, thread_id: str):
        response = self.request("thread/resume", {"threadId": thread_id}, timeout=20)
        if "error" in response:
            raise RuntimeError(response)
        resumed_id = response["result"]["thread"]["id"]
        if resumed_id != thread_id:
            raise RuntimeError(f"Codex changed thread id during resume: {thread_id} -> {resumed_id}")
        self.ledger.set_state(thread_id=thread_id, phase="thread-resumed", last_checkpoint="thread-resumed")
        self.ledger.event("codex.thread.resumed", codex_thread_id=thread_id)
        return response

    def turn_start(self, thread_id: str, prompt: str):
        response = self.request(
            "turn/start",
            {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
        )
        if "error" in response:
            raise RuntimeError(response)
        turn_id = response["result"]["turn"]["id"]
        self.ledger.set_state(turn_id=turn_id, phase="turn-started", last_checkpoint="turn-started")
        self.ledger.event("codex.turn.started", codex_thread_id=thread_id, codex_turn_id=turn_id, prompt_marker=prompt.split()[0])
        return turn_id

    def wait_turn_completed(self, thread_id: str, turn_id: str, timeout=30):
        predicate = lambda item: item.get("method") == "turn/completed" \
            and item.get("params", {}).get("threadId") == thread_id \
            and item.get("params", {}).get("turn", {}).get("id") == turn_id
        started = time.monotonic()
        try:
            # Some 0.139.0 app-server paths emit thread/status=idle before
            # flushing turn/completed.  Do not infer completion from idle.
            event = self.wait_for(predicate, timeout=min(timeout, 0.5))
        except TimeoutError:
            # A read-only request is a protocol poll/flush, not a state
            # shortcut.  The matching turn/completed notification is still
            # mandatory below.
            try:
                self.request("thread/read", {"threadId": thread_id}, timeout=5)
            except (TimeoutError, RuntimeError):
                pass
            remaining = max(0.1, timeout - (time.monotonic() - started))
            event = self.wait_for(predicate, timeout=remaining)
        turn = event["params"]["turn"]
        self.ledger.event("codex.turn.completed", codex_thread_id=thread_id, codex_turn_id=turn_id, status=turn.get("status"), error=turn.get("error"))
        return turn

    def wait_item(self, thread_id: str, turn_id: str, item_type: str, completed=False, timeout=30):
        method = "item/completed" if completed else "item/started"
        return self.wait_for(
            lambda item: item.get("method") == method
            and item.get("params", {}).get("threadId") == thread_id
            and item.get("params", {}).get("turnId") == turn_id
            and item.get("params", {}).get("item", {}).get("type") in {item_type, item_type.replace("_", "")},
            timeout=timeout,
        )

    def interrupt(self, thread_id: str, turn_id: str, reason: str):
        self.ledger.event("fault.injected", fault=reason, injection_point=reason, control="turn/interrupt")
        response = self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=15)
        if "error" in response:
            raise RuntimeError(response)
        self.ledger.event("codex.turn.interrupt.requested", codex_thread_id=thread_id, codex_turn_id=turn_id, reason=reason)
        return response

    def terminate_group(self, sig=signal.SIGTERM):
        if not self.process or self.process.poll() is not None:
            return self.process.returncode if self.process else None
        try:
            os.killpg(self.process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=6)
        return self.process.returncode

    def close(self):
        if not self.process:
            return
        if self.process.poll() is None:
            self.terminate_group(signal.SIGTERM)
        stderr = self.process.stderr.read() if self.process.stderr else ""
        self.stderr_path.write_text(stderr, encoding="utf-8")
        try:
            self.selector.unregister(self.process.stdout)
        except Exception:
            pass


def start_provider(case_dir: Path, mode: str, command: str, retry_command: str, port: int = 11434, provider_id: str = "w7-fake-codex"):
    ready = case_dir / "provider-ready.json"
    request_log = case_dir / "provider-requests.jsonl"
    provider_log = (case_dir / "provider.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
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
            "--command",
            command,
            "--retry-command",
            retry_command,
            "--request-log",
            str(request_log),
            "--ready-file",
            str(ready),
        ],
        stdout=provider_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if ready.exists():
            try:
                payload = json.loads(ready.read_text(encoding="utf-8"))
                with urlopen(f"http://127.0.0.1:{payload['port']}/health", timeout=0.5) as response:
                    if response.status == 200:
                        return process, provider_log, payload
            except Exception:
                pass
        if process.poll() is not None:
            break
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=3)
    provider_log.close()
    raise RuntimeError("W7 fake Provider failed readiness")


def stop_provider(process, provider_log):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
    provider_log.close()


def command_for(case: CaseLedger, tool_class: str, sleep_ms=0):
    parts = [
        "python3",
        "effect-sink.py",
        "--ledger",
        "effects.jsonl",
        "--result-ledger",
        "tool-results.jsonl",
        "--operation-id",
        f"{case.run_id}:operation-1",
        "--idempotency-key",
        case.idempotency_key,
        "--run-id",
        case.run_id,
        "--side-effect-class",
        tool_class,
    ]
    if sleep_ms:
        parts.extend(["--sleep-before-ms", str(sleep_ms)])
    shell_command = " ".join(shlex.quote(part) for part in parts)
    return json.dumps({"cmd": shell_command}, ensure_ascii=False, separators=(",", ":"))


def prepare_case(case_dir: Path, run_id: str, scenario: str, tool_class: str | None = None, fault: str | None = None):
    case = CaseLedger(case_dir, run_id, "codex-c3-c4-v1", f"codex-c3-c4-v1:{run_id}", scenario)
    write_json(
        case_dir / "case-manifest.json",
        {
            "schema": SCHEMA,
            "run_id": run_id,
            "schedule_id": case.schedule_id,
            "idempotency_key": case.idempotency_key,
            "scenario": scenario,
            "tool_class": tool_class,
            "fault": fault,
            "fixture": "w7-codex-c3-c4",
            "candidate": "Codex Harness",
            "candidate_version": CODEX_VERSION,
            "provider": "w7-fake-codex via loopback /v1/responses",
            "adapter_version": ADAPTER_VERSION,
        },
    )
    shutil.copyfile(EFFECT_SINK, case_dir / "effect-sink.py")
    return case


def update_effect_status(case: CaseLedger):
    effects = read_jsonl(case.effects_path)
    tool_results = read_jsonl(case.tool_results_path)
    case.set_state(
        effect_status="applied" if effects else "none",
        result_status="completed" if tool_results else case.state.get("result_status", "unknown"),
    )
    return effects, tool_results


def setup_server(case: CaseLedger, provider_mode: str, tool_class: str, sleep_ms=0):
    initial_command = command_for(case, tool_class, sleep_ms=sleep_ms)
    retry_command = command_for(case, tool_class, sleep_ms=0)
    provider, provider_log, provider_info = start_provider(case.case_dir, provider_mode, initial_command, retry_command)
    code_home = case.case_dir / "codex-home"
    code_home.mkdir(parents=True, exist_ok=True)
    server = AppServer(shutil.which("codex") or "codex", case.case_dir, code_home, case, initial_command, tool_class == "approval-required")
    server.start()
    case.event("provider.ready", provider_id=provider_info["provider_id"], endpoint=f"http://127.0.0.1:{provider_info['port']}/v1/responses")
    return server, provider, provider_log


def close_components(server, provider, provider_log):
    if server:
        server.close()
    if provider:
        stop_provider(provider, provider_log)


def run_codex_initial(case: CaseLedger, server: AppServer, tool_class: str, fault: str | None = None, process_interrupt=False):
    approval_policy = "on-request" if tool_class == "approval-required" else "never"
    thread_id = server.thread_start(case.case_dir, approval_policy)
    prompt = "W7_INITIAL Execute the allow-listed case-local effect command once and report fixture-ok."
    turn_id = server.turn_start(thread_id, prompt)
    case.event("attempt.codex-dispatched", mode="initial", fault=fault, codex_thread_id=thread_id, codex_turn_id=turn_id)

    if fault == "turn_interrupt":
        server.wait_for(lambda item: item.get("method") == "turn/started" and item.get("params", {}).get("turn", {}).get("id") == turn_id, timeout=10)
        server.interrupt(thread_id, turn_id, "turn_interrupt")
        turn = server.wait_turn_completed(thread_id, turn_id, timeout=15)
        return {"initial_status": turn.get("status"), "initial_returncode": 0, "interrupted": True}
    if fault == "provider_timeout":
        server.wait_for(lambda item: item.get("method") == "turn/started" and item.get("params", {}).get("turn", {}).get("id") == turn_id, timeout=10)
        time.sleep(WATCHDOG_SECONDS)
        server.interrupt(thread_id, turn_id, "provider_timeout")
        turn = server.wait_turn_completed(thread_id, turn_id, timeout=15)
        return {"initial_status": turn.get("status"), "initial_returncode": 0, "interrupted": True}
    if fault == "tool_timeout":
        server.wait_item(thread_id, turn_id, "commandExecution", completed=False, timeout=20)
        time.sleep(TOOL_INTERRUPT_SECONDS)
        server.interrupt(thread_id, turn_id, "tool_timeout")
        turn = server.wait_turn_completed(thread_id, turn_id, timeout=15)
        return {"initial_status": turn.get("status"), "initial_returncode": 0, "interrupted": True}
    if process_interrupt:
        server.wait_item(thread_id, turn_id, "commandExecution", completed=True, timeout=20)
        effects, tool_results = update_effect_status(case)
        case.event("fault.injected", fault="process_interrupt", injection_point="after-tool-result-before-turn-completion", effect_count=len(effects), tool_result_count=len(tool_results))
        return {"initial_status": "process_interrupted", "initial_returncode": server.terminate_group(signal.SIGTERM), "interrupted": True}
    turn = server.wait_turn_completed(thread_id, turn_id, timeout=30)
    return {"initial_status": turn.get("status"), "initial_returncode": 0, "interrupted": False}


def recover_after_interruption(case: CaseLedger, server: AppServer | None, tool_class: str, fault: str, process_was_killed=False):
    case.refresh_state()
    thread_id = case.state.get("thread_id")
    if not thread_id:
        raise RuntimeError("missing thread_id before recovery")
    if process_was_killed:
        # The loopback provider remains the same process.  Only the Codex
        # app-server is restarted, reusing the case-local CODEX_HOME so the
        # thread/rollout identity is the thing under test.
        expected_command = command_for(case, tool_class, sleep_ms=0)
        server = AppServer(
            shutil.which("codex") or "codex",
            case.case_dir,
            case.case_dir / "codex-home",
            case,
            expected_command,
            tool_class == "approval-required",
        )
        server.start()
        owned_components = (server, None, None)
    else:
        owned_components = (server, None, None)
    try:
        server.thread_resume(thread_id)
        effects, tool_results = update_effect_status(case)
        if effects or tool_results:
            case.event(
                "side_effect.reconciled",
                source="external-effect-and-tool-result-ledger",
                effect_count=len(effects),
                tool_result_count=len(tool_results),
                decision="no-reexecution",
            )
            turn_id = server.turn_start(thread_id, "W7_RECONCILE_NO_TOOL Reconcile the durable ledgers; do not call any tool; report fixture-ok.")
            server.wait_turn_completed(thread_id, turn_id, timeout=30)
            case.set_state(status="completed", phase="completed", last_checkpoint="reconciled")
            case.finish_result("completed-after-reconcile", effect_count=len(effects), tool_result_count=len(tool_results))
            return server, None, None, "completed"

        if fault == "tool_timeout" and tool_class == "approval-required":
            case.set_state(status="safe_stopped", phase="safe-stopped", last_checkpoint="safe-stopped", safe_stop_reason="approval-required tool outcome unknown after timeout")
            case.event("run.safe_stopped", reason=case.state["safe_stop_reason"])
            return server, None, None, "safe_stopped"

        case.set_state(retry_count=case.state.get("retry_count", 0) + 1, phase="retry-decided", last_checkpoint="retry-decided")
        case.event("retry.decided", retry_number=case.state["retry_count"], scope="tool-or-turn", reason="no durable tool result; allow one replay-safe or pre-effect retry")
        retry_turn = server.turn_start(thread_id, "W7_RETRY_TOOL Retry the allow-listed case-local effect command once and report fixture-ok.")
        server.wait_turn_completed(thread_id, retry_turn, timeout=30)
        effects, tool_results = update_effect_status(case)
        if tool_class != "read-only" and len(effects) != 1:
            raise RuntimeError(f"retry did not produce exactly one effect: {len(effects)}")
        case.event("side_effect.reconciled", source="post-retry-ledger", effect_count=len(effects), tool_result_count=len(tool_results), decision="one-bounded-retry")
        case.set_state(status="completed", phase="completed", last_checkpoint="retry-completed")
        case.finish_result("completed-after-retry", effect_count=len(effects), tool_result_count=len(tool_results))
        return server, None, None, "completed"
    except Exception:
        if process_was_killed:
            close_components(*owned_components)
        raise


def verify_c3_case(case: CaseLedger, invocation_count: int, expected_duplicate_count: int):
    case.refresh_state()
    schedule = read_jsonl(case.schedule_path)
    attempts = read_jsonl(case.attempts_path)
    events = read_jsonl(case.events_path)
    effects = read_jsonl(case.effects_path)
    tool_results = read_jsonl(case.tool_results_path)
    results = read_jsonl(case.results_path)
    duplicate_count = sum(item.get("type") == "idempotency.duplicate" for item in events)
    required_ids = all(item.get("run_id") == case.run_id and item.get("schedule_id") == case.schedule_id and item.get("idempotency_key") == case.idempotency_key for item in events)
    passed = all(
        [
            case.state.get("thread_id") is not None,
            case.state.get("turn_id") is not None,
            len(schedule) == invocation_count,
            len(attempts) == invocation_count * 2,
            duplicate_count == expected_duplicate_count,
            len(effects) == 1,
            len(tool_results) >= 1,
            len(results) == 1,
            case.state.get("status") == "completed",
            case.state.get("effect_status") == "applied",
            required_ids,
        ]
    )
    return {
        "scenario": case.state["scenario"],
        "status": "pass" if passed else "fail",
        "observed": {
            "schedule_records": len(schedule),
            "attempt_records": len(attempts),
            "duplicate_events": duplicate_count,
            "effect_records": len(effects),
            "tool_result_records": len(tool_results),
            "result_records": len(results),
            "thread_id": case.state.get("thread_id"),
            "turn_id": case.state.get("turn_id"),
            "final_status": case.state.get("status"),
        },
        "checks": {
            "one_effect_per_key": len(effects) == 1,
            "duplicate_delivery_suppressed": duplicate_count == expected_duplicate_count,
            "attempt_history_complete": len(attempts) == invocation_count * 2,
            "ids_correlated": required_ids,
            "durable_result": len(results) == 1,
        },
        "evidence_dir": str(case.case_dir),
    }


def run_c3_case(output_dir: Path, scenario: str, repeat: int, executable: str):
    case_dir = output_dir / "c3" / scenario / f"repeat-{repeat:02d}"
    run_id = f"w7-c3-{scenario}-{repeat:02d}"
    case = prepare_case(case_dir, run_id, scenario, tool_class="idempotent")
    server = provider = provider_log = None
    try:
        for spec in C3_SCENARIOS[scenario]:
            mode, kind = spec.split(":", 1)
            case.schedule(kind, missed=kind == "missed", late=kind == "delayed")
            attempt_id = f"{run_id}:attempt-{len(read_jsonl(case.attempts_path)) // 2 + 1:03d}"
            case.attempt(attempt_id, mode, "started", "claimed")
            if case.state.get("status") == "completed":
                if mode == "resume":
                    # Resume is a recovery control action, not a second
                    # schedule delivery.  The following duplicate trigger is
                    # the one that exercises C3 idempotency after recovery.
                    case.event("recovery.already-completed", trigger_kind=kind, decision="no-codex-dispatch")
                    case.attempt(attempt_id, mode, "terminal", "already-completed")
                else:
                    case.event("idempotency.duplicate", trigger_kind=kind, decision="no-codex-dispatch")
                    case.attempt(attempt_id, mode, "terminal", "deduplicated")
                continue
            case.set_state(phase="claimed", last_checkpoint="idempotency-claimed", effect_status="pending")
            fault = "process_interrupt" if scenario == "interrupted_retry" and mode == "trigger" and kind == "interrupted" else None
            if server is None:
                server, provider, provider_log = setup_server(case, "process_interrupt" if fault else "normal", "idempotent")
            initial = run_codex_initial(case, server, "idempotent", fault=fault, process_interrupt=bool(fault))
            update_effect_status(case)
            if fault:
                server, recovered_provider, recovered_log, status = recover_after_interruption(case, None, "idempotent", fault, process_was_killed=True)
                if recovered_provider:
                    if provider:
                        stop_provider(provider, provider_log)
                    provider, provider_log = recovered_provider, recovered_log
            else:
                case.set_state(status="completed", phase="completed", last_checkpoint="turn-completed")
                case.finish_result("completed", effect_count=len(read_jsonl(case.effects_path)), tool_result_count=len(read_jsonl(case.tool_results_path)))
            case.attempt(attempt_id, mode, "terminal", initial.get("initial_status", "completed"))
        expected_duplicates = 1 if scenario == "interrupted_retry" else len(C3_SCENARIOS[scenario]) - 1
        return verify_c3_case(case, len(C3_SCENARIOS[scenario]), expected_duplicates)
    except Exception as exc:
        case.event("run.error", error=repr(exc))
        case.set_state(status="unknown", phase="stop", last_checkpoint="error", safe_stop_reason=repr(exc))
        return {"scenario": scenario, "status": "unknown", "error": repr(exc), "evidence_dir": str(case_dir)}
    finally:
        close_components(server, provider, provider_log)


def verify_c4_case(case: CaseLedger, fault: str, tool_class: str, initial):
    case.refresh_state()
    events = read_jsonl(case.events_path)
    effects = read_jsonl(case.effects_path)
    tool_results = read_jsonl(case.tool_results_path)
    results = read_jsonl(case.results_path)
    approvals = [item for item in events if item.get("type") == "codex.approval.requested"]
    faults = [item for item in events if item.get("type") == "fault.injected"]
    reconciled = [item for item in events if item.get("type") == "side_effect.reconciled"]
    retry_count = case.state.get("retry_count", 99)
    physical_effects = sum(item.get("physical_effect_count", 0) for item in effects)
    expected_approval = tool_class == "approval-required"
    approval_ok = bool(approvals) if expected_approval else not approvals
    recovery_controls_pass = all(
        [
            initial.get("interrupted") is True,
            case.state.get("thread_id") is not None,
            case.state.get("turn_id") is not None,
            bool(faults),
            case.state.get("status") in {"completed", "safe_stopped"},
            case.state.get("status") != "unknown",
            retry_count <= 1,
            physical_effects <= 1,
            len(effects) <= 1,
            bool(reconciled) or case.state.get("status") == "safe_stopped",
            len(results) <= 1,
        ]
    )
    native_approval_evidence = approval_ok
    if recovery_controls_pass and expected_approval and not approvals:
        status = "unknown"
        unknown_reason = "codex-native-approval-request-not-observed"
    else:
        status = "pass" if recovery_controls_pass and native_approval_evidence else "fail"
        unknown_reason = None
    return {
        "case_id": case.case_dir.name,
        "fault": fault,
        "tool_class": tool_class,
        "status": status,
        **({"unknown_reason": unknown_reason} if unknown_reason else {}),
        "observed": {
            "initial_status": initial.get("initial_status"),
            "final_status": case.state.get("status"),
            "retry_count": retry_count,
            "effect_records": len(effects),
            "tool_result_records": len(tool_results),
            "physical_effects": physical_effects,
            "result_records": len(results),
            "approval_requests": len(approvals),
            "native_approval_evidence": native_approval_evidence,
            "fault_records": len(faults),
            "reconcile_events": len(reconciled),
        },
        "checks": {
            "real_codex_interruption_or_timeout": initial.get("interrupted") is True,
            "state_not_lost": case.state.get("thread_id") is not None and case.state.get("turn_id") is not None,
            "retry_bounded": retry_count <= 1,
            "unsafe_effect_duplicate_free": physical_effects <= 1,
            "approval_boundary": native_approval_evidence,
            "native_approval_observed": bool(approvals),
            "recovery_controls_pass": recovery_controls_pass,
            "reconcile_or_safe_stop": bool(reconciled) or case.state.get("status") == "safe_stopped",
        },
        "evidence_dir": str(case.case_dir),
    }


def run_c4_case(output_dir: Path, fault: str, tool_class: str, repeat: int, executable: str):
    case_dir = output_dir / "c4" / fault / tool_class / f"repeat-{repeat:02d}"
    run_id = f"w7-c4-{fault}-{tool_class}-{repeat:02d}"
    case = prepare_case(case_dir, run_id, f"c4:{fault}", tool_class=tool_class, fault=fault)
    server = provider = provider_log = None
    try:
        provider_mode = {"turn_interrupt": "before_tool", "provider_timeout": "provider_timeout", "tool_timeout": "tool_timeout", "process_interrupt": "process_interrupt"}[fault]
        server, provider, provider_log = setup_server(case, provider_mode, tool_class, sleep_ms=700 if fault == "tool_timeout" else 0)
        initial = run_codex_initial(case, server, tool_class, fault=fault, process_interrupt=fault == "process_interrupt")
        update_effect_status(case)
        if fault == "process_interrupt":
            server, recovered_provider, recovered_log, _status = recover_after_interruption(case, None, tool_class, fault, process_was_killed=True)
            if recovered_provider:
                stop_provider(provider, provider_log)
                provider, provider_log = recovered_provider, recovered_log
        else:
            server, recovered_provider, recovered_log, _status = recover_after_interruption(case, server, tool_class, fault, process_was_killed=False)
        if tool_class == "approval-required":
            approval_events = [item for item in read_jsonl(case.events_path) if item.get("type") == "codex.approval.requested"]
            if not approval_events:
                case.event(
                    "codex.approval.request.missing",
                    expected=True,
                    decision="unknown-stop",
                    reason="workspace-local-command-did-not-trigger-native-approval-request",
                    approval_policy="on-request",
                    sandbox="workspace-write",
                )
        result = verify_c4_case(case, fault, tool_class, initial)
        return result
    except Exception as exc:
        case.event("run.error", error=repr(exc))
        case.set_state(status="unknown", phase="stop", last_checkpoint="error", safe_stop_reason=repr(exc))
        return {"case_id": case_dir.name, "fault": fault, "tool_class": tool_class, "status": "unknown", "error": repr(exc), "evidence_dir": str(case_dir)}
    finally:
        close_components(server, provider, provider_log)


def run_smoke(output_dir: Path, executable: str):
    case_dir = output_dir / "smoke"
    case = prepare_case(case_dir, "w7-smoke-01", "smoke", tool_class="read-only")
    server = provider = provider_log = None
    try:
        server, provider, provider_log = setup_server(case, "normal", "read-only")
        result = run_codex_initial(case, server, "read-only")
        update_effect_status(case)
        case.set_state(status="completed", phase="completed", last_checkpoint="smoke-completed")
        case.finish_result("smoke-completed", effect_count=0, tool_result_count=len(read_jsonl(case.tool_results_path)))
        return {"status": "pass", "initial": result, "evidence_dir": str(case_dir)}
    except Exception as exc:
        return {"status": "unknown", "error": repr(exc), "evidence_dir": str(case_dir)}
    finally:
        close_components(server, provider, provider_log)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true")
    group.add_argument("--c3", action="store_true")
    group.add_argument("--c4", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--codex", default=CODEX_DEFAULT)
    args = parser.parse_args()
    if not args.codex:
        raise SystemExit("codex executable is not installed")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("w7-codex-c3-c4-%Y%m%dT%H%M%S") + f"-{started.microsecond:06d}Z"
    output_dir = args.output or (RUNS / run_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    if args.smoke:
        summary = {"schema": SCHEMA, "run_id": run_id, "mode": "smoke", "result": run_smoke(output_dir, args.codex), "classification": "acceptance/evaluation"}
    elif args.c3:
        cases = [run_c3_case(output_dir, scenario, repeat, args.codex) for scenario in C3_SCENARIOS for repeat in range(1, REPEATS + 1)]
        passed = sum(item.get("status") == "pass" for item in cases)
        summary = {
            "schema": SCHEMA,
            "run_id": run_id,
            "mode": "c3",
            "classification": "acceptance/evaluation",
            "candidate": {"name": "Codex Harness", "version": CODEX_VERSION, "entrypoint": args.codex},
            "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE)},
            "threshold": {"scenarios": list(C3_SCENARIOS), "repeats_per_scenario": REPEATS, "same_key_effective_side_effects": 1, "duplicate_extra_effects": 0, "native_scheduler": "not measured; external deterministic trigger"},
            "status": "pass-with-composition" if passed == len(cases) else "unknown/stop",
            "cases_passed": passed,
            "cases_total": len(cases),
            "checks": {"all_cases_pass": passed == len(cases), "one_effect_per_key": all(item.get("checks", {}).get("one_effect_per_key") for item in cases if item.get("status") == "pass"), "missing_evidence_stops": True},
            "cases": cases,
        }
    else:
        cases = [run_c4_case(output_dir, fault, tool_class, repeat, args.codex) for fault in C4_FAULTS for tool_class in C4_TOOL_CLASSES for repeat in range(1, REPEATS + 1)]
        passed = sum(item.get("status") == "pass" for item in cases)
        summary = {
            "schema": SCHEMA,
            "run_id": run_id,
            "mode": "c4",
            "classification": "acceptance/evaluation",
            "candidate": {"name": "Codex Harness", "version": CODEX_VERSION, "entrypoint": args.codex},
            "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE)},
            "threshold": {"faults": list(C4_FAULTS), "tool_classes": list(C4_TOOL_CLASSES), "repeats_per_fault_tool_class": REPEATS, "critical_state_loss": 0, "unsafe_side_effect_duplicate": 0, "max_retry_count": 1, "reconcile_before_resume_or_retry": True},
            "status": "pass-with-composition" if passed == len(cases) else "unknown/stop",
            "cases_passed": passed,
            "cases_total": len(cases),
            "unknown_cases": sum(item.get("status") == "unknown" for item in cases),
            "failed_cases": sum(item.get("status") == "fail" for item in cases),
            "checks": {
                "all_cases_pass": passed == len(cases),
                "recovery_controls_pass": all(item.get("checks", {}).get("recovery_controls_pass") for item in cases),
                "critical_state_loss_zero": all(item.get("checks", {}).get("state_not_lost") for item in cases),
                "unsafe_side_effect_duplicates_zero": all(item.get("checks", {}).get("unsafe_effect_duplicate_free") for item in cases),
                "retry_bounded": all(item.get("checks", {}).get("retry_bounded") for item in cases),
                "native_approval_evidence_complete": all(item.get("checks", {}).get("native_approval_observed") for item in cases if item.get("tool_class") == "approval-required"),
                "missing_evidence_stops": True,
            },
            "cases": cases,
        }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    summary_status = summary.get("status") or summary.get("result", {}).get("status")
    summary_cases = summary.get("cases_passed", 1 if summary.get("result", {}).get("status") == "pass" else 0)
    summary_total = summary.get("cases_total", 1)
    print(json.dumps({"run_id": run_id, "summary": str(summary_path), "mode": summary["mode"], "status": summary_status, "cases": f"{summary_cases}/{summary_total}"}, ensure_ascii=False, indent=2))
    if summary_status not in {"pass-with-composition", "pass"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
