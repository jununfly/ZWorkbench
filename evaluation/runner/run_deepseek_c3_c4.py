#!/usr/bin/env python3
"""Run the W6/W7-shaped C3/C4 fixture against DeepSeek ACP.

This is acceptance/evaluation infrastructure. It uses the fixed DeepSeek ACP
entrypoint, a case-local workspace and DSH_HOME, a loopback fake Chat
Completions provider, and the exact W7 Codex effect sink. The schedule,
attempt, result, effect and reconciliation ledgers are intentionally owned by
this external composition adapter so the report can distinguish native ACP
facts from composition facts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-c3-c4"
SOURCE_FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
EFFECT_SINK = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c3-c4" / "effect-sink.py"
MANIFEST_PATH = REPO_ROOT / "evaluation" / "candidates" / "deepseek" / "manifest.json"
SCHEMA = "zworkbench-w8-deepseek-c34/v1"
ADAPTER_VERSION = "w8-deepseek-c3-c4-composition-adapter/v1"
DEEPSEEK_VERSION = "0.1.2-alpha.1"
DEFAULT_ENTRY = "/Users/bilibili/Documents/workspace/github/deepseek-ai/deepseek-harness/apps/cli/lib/bin.js"

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


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            values.append(json.loads(line))
    return values


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def wait_until(predicate: Callable[[], bool], timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class CaseLedger:
    """The one external durable owner used by the DeepSeek composition adapter."""

    def __init__(self, case_dir: Path, run_id: str, scenario: str, *, tool_class: str | None = None, fault: str | None = None):
        self.case_dir = case_dir
        self.run_id = run_id
        self.schedule_id = f"{run_id}:schedule-1"
        self.idempotency_key = f"deepseek-c34-v1:{run_id}"
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
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "scenario": scenario,
            "tool_class": tool_class,
            "fault": fault,
            "candidate_session_id": None,
            "adapter_turn_id": None,
            "candidate_turn_id_observed": False,
            "candidate_tool_call_observed": False,
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

    def refresh(self) -> dict[str, Any]:
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        return self.state

    def set_state(self, **updates: Any) -> None:
        self.state.update(updates)
        write_json(self.state_path, self.state)

    def event(self, event_type: str, **payload: Any) -> None:
        self.refresh()
        event = {
            "schema": SCHEMA,
            "event_id": f"{self.run_id}:event:{len(read_jsonl(self.events_path)) + 1:04d}",
            "at": now(),
            "type": event_type,
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "candidate_session_id": self.state.get("candidate_session_id"),
            "adapter_turn_id": self.state.get("adapter_turn_id"),
            **payload,
        }
        append_jsonl(self.events_path, event)
        if event_type == "fault.injected":
            append_jsonl(self.faults_path, event)

    def schedule(self, trigger_kind: str, *, missed: bool = False, late: bool = False) -> None:
        append_jsonl(self.schedule_path, {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "trigger_kind": trigger_kind,
            "missed": missed,
            "late": late,
            "delivery_semantics": "run-once-late" if missed else "deliver-once",
        })
        self.event("schedule.triggered", trigger_kind=trigger_kind, missed=missed, late=late)

    def attempt(self, attempt_id: str, mode: str, phase: str, outcome: str) -> None:
        append_jsonl(self.attempts_path, {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "attempt_id": attempt_id,
            "mode": mode,
            "phase": phase,
            "outcome": outcome,
            "candidate_session_id": self.state.get("candidate_session_id"),
            "adapter_turn_id": self.state.get("adapter_turn_id"),
        })
        self.event(f"attempt.{phase}", attempt_id=attempt_id, mode=mode, outcome=outcome)

    def update_effect_status(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        effects = read_jsonl(self.effects_path)
        results = read_jsonl(self.tool_results_path)
        self.set_state(
            effect_status="applied" if effects else "none",
            result_status="completed" if results else self.state.get("result_status", "unknown"),
        )
        return effects, results

    def finish_result(self, outcome: str, **payload: Any) -> None:
        append_jsonl(self.results_path, {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "idempotency_key": self.idempotency_key,
            "outcome": outcome,
            "candidate_session_id": self.state.get("candidate_session_id"),
            "adapter_turn_id": self.state.get("adapter_turn_id"),
            **payload,
        })
        self.set_state(result_status="completed", last_checkpoint="result-recorded")
        self.event("result.recorded", outcome=outcome, **payload)


class AcpClient:
    """Line-oriented ACP client with explicit permission and update capture."""

    def __init__(self, entrypoint: Path, project: Path, home: Path, provider_url: str, case: CaseLedger, *, tool_class: str):
        environment = os.environ.copy()
        environment.update({
            "DSH_HOME": str(home),
            "DSH_TELEMETRY_DISABLED": "1",
            "DEEPSEEK_API_KEY": "w6-fake-key",
            "DEEPSEEK_BASE_URL": provider_url + "/v1",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        })
        self.case = case
        self.tool_class = tool_class
        self.process = subprocess.Popen(
            [shutil.which("node") or "node", str(entrypoint), "--profile", "acp"],
            cwd=project,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
        )
        self.transcript = case.case_dir / "acp-transcript.jsonl"
        # A recovery client shares the case transcript with the interrupted
        # client. Append so replay includes both the interruption and resume
        # legs instead of silently erasing the first process's frames.
        self.transcript_handle = self.transcript.open("a", encoding="utf-8")
        self.next_id = 1
        self.frames: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.permission_requests: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.tool_results: list[dict[str, Any]] = []
        self.prompt_request_id: int | None = None
        self.stdout_buffer = b""

    def _write(self, frame: dict[str, Any]) -> None:
        if self.process.stdin is None or self.process.stdin.closed:
            raise RuntimeError("ACP stdin is closed")
        self.process.stdin.write((encode(frame) + "\n").encode("utf-8"))
        self.process.stdin.flush()
        self._record("client", frame)

    def _record(self, side: str, frame: dict[str, Any]) -> None:
        self.transcript_handle.write(encode({"side": side, "frame": frame}) + "\n")
        self.transcript_handle.flush()

    def request_id(self, method: str, params: dict[str, Any]) -> int:
        request_id = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return request_id

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _handle_frame(self, frame: dict[str, Any]) -> None:
        self.frames.append(frame)
        self._record("server", frame)
        if frame.get("method") == "session/update":
            update = frame.get("params", {}).get("update", {})
            self.updates.append(update)
            kind = update.get("sessionUpdate")
            if kind == "tool_call":
                self.tool_calls.append(update)
                self.case.set_state(candidate_tool_call_observed=True)
                self.case.event("candidate.tool.call", tool_call_id=update.get("toolCallId"), title=update.get("title"), raw_input=update.get("rawInput"))
            elif kind == "tool_call_update":
                self.tool_results.append(update)
                self.case.event("candidate.tool.result", tool_call_id=update.get("toolCallId"), status=update.get("status"))
            elif kind == "agent_message_chunk":
                self.case.event("candidate.assistant.message", text=update.get("content", {}).get("text", ""))
        if frame.get("method") == "session/request_permission" and "id" in frame:
            self.permission_requests.append(frame)
            option_id = "allow-once" if self.tool_class == "approval-required" else "reject-once"
            self.case.event("candidate.permission.request", tool_call=frame.get("params", {}).get("toolCall"), decision=option_id)
            self._write({
                "jsonrpc": "2.0",
                "id": frame["id"],
                "result": {"outcome": {"outcome": "selected", "optionId": option_id}},
            })

    def read_one(self, timeout: float = 30.0) -> dict[str, Any]:
        if self.process.stdout is None:
            raise RuntimeError("ACP stdout is unavailable")

        # Do not combine select() with TextIOWrapper.readline(). A single pipe
        # read can place several JSON frames into TextIOWrapper's private
        # buffer; after consuming one frame, the next frame is then available
        # to readline() but the OS fd is no longer readable. select() would
        # incorrectly wait until its timeout and make a completed turn look
        # hung. Keep framing at the fd boundary so buffered frames are always
        # consumed before waiting on the pipe again.
        deadline = time.monotonic() + timeout
        while True:
            newline = self.stdout_buffer.find(b"\n")
            if newline >= 0:
                raw_line = self.stdout_buffer[:newline]
                self.stdout_buffer = self.stdout_buffer[newline + 1:]
                if raw_line.endswith(b"\r"):
                    raw_line = raw_line[:-1]
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("ACP frame timeout")
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                raise TimeoutError("ACP frame timeout")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                if self.stdout_buffer.strip():
                    line = self.stdout_buffer.decode("utf-8")
                    self.stdout_buffer = b""
                    break
                raise RuntimeError(f"ACP exited while reading: {self.process.poll()}")
            self.stdout_buffer += chunk

        try:
            frame = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"invalid ACP JSON: {line!r}") from error
        self._handle_frame(frame)
        return frame

    def wait_response(self, request_id: int, timeout: float = 60.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.read_one(max(0.05, deadline - time.monotonic()))
            if frame.get("id") == request_id:
                return frame
        raise TimeoutError(f"ACP response timeout: {request_id}")

    def wait_frame(self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 60.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.read_one(max(0.05, deadline - time.monotonic()))
            if predicate(frame):
                return frame
        raise TimeoutError("ACP predicate timeout")

    def request(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        return self.wait_response(self.request_id(method, params), timeout)

    def initialize_new(self, project: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
        initialized = self.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        created = self.request("session/new", {"cwd": str(project), "mcpServers": []})
        session_id = created.get("result", {}).get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise RuntimeError(f"session/new returned no session id: {created}")
        self.case.set_state(candidate_session_id=session_id, phase="session-created", last_checkpoint="candidate-session-created")
        return initialized, created, session_id

    def resume(self, project: Path, session_id: str) -> dict[str, Any]:
        resumed = self.request("session/resume", {"sessionId": session_id, "cwd": str(project), "mcpServers": []})
        if "error" in resumed:
            raise RuntimeError(f"session/resume failed: {resumed}")
        self.case.set_state(candidate_session_id=session_id, phase="session-resumed", last_checkpoint="candidate-session-resumed")
        return resumed

    def prompt(self, session_id: str, text: str, *, wait: bool = True, timeout: float = 60.0) -> tuple[int, dict[str, Any] | None]:
        request_id = self.request_id("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]})
        self.prompt_request_id = request_id
        self.case.set_state(adapter_turn_id=f"{self.case.run_id}:prompt-{request_id}", phase="prompt-started", last_checkpoint="prompt-started")
        if not wait:
            return request_id, None
        response = self.wait_response(request_id, timeout)
        return request_id, response

    def close_session(self, session_id: str) -> dict[str, Any]:
        return self.request("session/close", {"sessionId": session_id})

    def close(self) -> dict[str, Any]:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        return self._finish()

    def kill(self) -> dict[str, Any]:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        return self._finish()

    def _finish(self) -> dict[str, Any]:
        if not self.transcript_handle.closed:
            self.transcript_handle.close()
        stderr = ""
        if self.process.stderr is not None:
            try:
                stderr = self.process.stderr.read()[-12000:].decode("utf-8", errors="replace")
            except OSError:
                pass
        (self.case.case_dir / "acp-stderr.log").write_text(stderr, encoding="utf-8")
        return {"returncode": self.process.returncode, "stderr": stderr}


def start_provider(case_dir: Path, mode: str, command: str, retry_command: str) -> dict[str, Any]:
    root = case_dir / "provider"
    root.mkdir(parents=True, exist_ok=True)
    request_log = root / "requests.jsonl"
    ready_file = root / "ready.json"
    log_file = root / "provider.log"
    handle = log_file.open("w", encoding="utf-8")
    process = subprocess.Popen([
        sys.executable,
        str(FIXTURE / "fake-provider.py"),
        "--host", "127.0.0.1", "--port", "0",
        "--provider-id", "w8-deepseek-fake",
        "--mode", mode,
        "--command", command,
        "--retry-command", retry_command,
        "--request-log", str(request_log),
        "--ready-file", str(ready_file),
    ], stdout=handle, stderr=subprocess.STDOUT, text=True)
    ok = wait_until(lambda: ready_file.exists() and process.poll() is None, timeout=8)
    if not ok:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
        handle.close()
        raise RuntimeError("DeepSeek parity fake Provider did not become ready")
    payload = json.loads(ready_file.read_text(encoding="utf-8"))
    return {"process": process, "log_handle": handle, "request_log": request_log, "base_url": f"http://127.0.0.1:{payload['port']}"}


def stop_provider(server: dict[str, Any] | None) -> None:
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
    server["log_handle"].close()


def provider_requests(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def tool_command(case: CaseLedger, tool_class: str, *, sleep_ms: int = 0) -> str:
    parts = [
        "python3", "effect-sink.py",
        "--ledger", "effects.jsonl",
        "--result-ledger", "tool-results.jsonl",
        "--operation-id", f"{case.run_id}:operation-1",
        "--idempotency-key", case.idempotency_key,
        "--run-id", case.run_id,
        "--side-effect-class", tool_class,
    ]
    if sleep_ms:
        parts.extend(["--sleep-before-ms", str(sleep_ms)])
    return " ".join(shlex_quote(part) for part in parts)


def shlex_quote(value: str) -> str:
    import shlex
    return shlex.quote(value)


def prepare_case(case_dir: Path, run_id: str, scenario: str, *, tool_class: str | None = None, fault: str | None = None) -> CaseLedger:
    case_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_FIXTURE / "code-project", case_dir, dirs_exist_ok=True)
    shutil.copyfile(EFFECT_SINK, case_dir / "effect-sink.py")
    case = CaseLedger(case_dir, run_id, scenario, tool_class=tool_class, fault=fault)
    write_json(case_dir / "case-manifest.json", {
        "schema": SCHEMA,
        "run_id": run_id,
        "scenario": scenario,
        "tool_class": tool_class,
        "fault": fault,
        "fixture": "w6-0.1 + exact w7-codex-c3-c4 effect-sink",
        "candidate": "DeepSeek Harness",
        "candidate_version": DEEPSEEK_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "provider": "w8-deepseek-fake via loopback Chat Completions",
    })
    return case


def wait_provider(path: Path, predicate: Callable[[dict[str, Any]], bool], timeout: float = 15.0) -> bool:
    return wait_until(lambda: any(predicate(row) for row in provider_requests(path)), timeout)


def initialize_and_prompt(client: AcpClient, project: Path, prompt: str) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    initialized, created, session_id = client.initialize_new(project)
    _, response = client.prompt(session_id, prompt)
    assert response is not None
    return session_id, initialized, created, response


def recover_candidate(case: CaseLedger, project: Path, home: Path, entrypoint: Path, provider: dict[str, Any], *, reason: str, tool_class: str) -> tuple[AcpClient, dict[str, Any]]:
    case.refresh()
    session_id = case.state.get("candidate_session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("missing candidate session id before recovery")
    client = AcpClient(entrypoint, project, home, provider["base_url"], case, tool_class=tool_class)
    resumed = client.resume(project, session_id)
    effects, results = case.update_effect_status()
    if effects or results:
        case.event("side_effect.reconciled", source="deepseek-acp-effect-and-tool-result-ledger", effect_count=len(effects), tool_result_count=len(results), decision="no-reexecution", reason=reason)
        _, response = client.prompt(session_id, "RECONCILE_NO_TOOL Reconcile durable ledgers; do not call any tool; report fixture-ok.")
        assert response is not None
        case.set_state(status="completed", phase="completed", last_checkpoint="reconciled")
        case.finish_result("completed-after-reconcile", effect_count=len(effects), tool_result_count=len(results))
        return client, response
    if reason == "tool_timeout" and tool_class == "approval-required":
        case.set_state(status="safe_stopped", phase="safe-stopped", last_checkpoint="safe-stopped", safe_stop_reason="approval-required tool outcome unknown after timeout")
        case.event("run.safe_stopped", reason=case.state["safe_stop_reason"])
        return client, {"result": {"stopReason": "safe_stopped"}}
    case.set_state(retry_count=case.state.get("retry_count", 0) + 1, phase="retry-decided", last_checkpoint="retry-decided")
    case.event("retry.decided", retry_number=case.state["retry_count"], scope="tool-or-turn", reason="no durable tool result; one bounded retry")
    _, response = client.prompt(session_id, "RETRY_TOOL Retry the allow-listed case-local effect command once and report fixture-ok.")
    assert response is not None
    effects, results = case.update_effect_status()
    if tool_class != "read-only" and len(effects) != 1:
        raise RuntimeError(f"bounded retry did not produce one effect: {len(effects)}")
    case.event("side_effect.reconciled", source="post-retry-deepseek-acp-ledger", effect_count=len(effects), tool_result_count=len(results), decision="one-bounded-retry")
    case.set_state(status="completed", phase="completed", last_checkpoint="retry-completed")
    case.finish_result("completed-after-retry", effect_count=len(effects), tool_result_count=len(results))
    return client, response


def run_candidate_once(case: CaseLedger, provider: dict[str, Any], entrypoint: Path, *, fault: str | None, tool_class: str) -> tuple[AcpClient, dict[str, Any], bool]:
    client = AcpClient(entrypoint, case.case_dir, case.case_dir / "dsh-home", provider["base_url"], case, tool_class=tool_class)
    initialized, created, session_id = client.initialize_new(case.case_dir)
    case.event("candidate.initialized", protocol_version=initialized.get("result", {}).get("protocolVersion"), session_id=session_id)
    prompt_text = "INITIAL Execute the allow-listed case-local effect command once and report fixture-ok."
    prompt_id, response = client.prompt(session_id, prompt_text, wait=False)
    interrupted = False

    if fault in {"turn_interrupt", "provider_timeout"}:
        if not wait_provider(provider["request_log"], lambda row: row.get("tool_result_count") == 0):
            raise RuntimeError("provider request was not observed before cancellation")
        case.event("fault.injected", fault=fault, injection_point="provider-request-before-tool", control="session/cancel")
        client.notify("session/cancel", {"sessionId": session_id})
        interrupted = True
        response = client.wait_response(prompt_id, timeout=20)
    elif fault == "tool_timeout":
        client.wait_frame(lambda frame: frame.get("method") == "session/update" and frame.get("params", {}).get("update", {}).get("sessionUpdate") == "tool_call", timeout=30)
        time.sleep(0.15)
        case.event("fault.injected", fault=fault, injection_point="tool-call-in-progress", control="session/cancel")
        client.notify("session/cancel", {"sessionId": session_id})
        interrupted = True
        response = client.wait_response(prompt_id, timeout=30)
    elif fault == "process_interrupt":
        client.wait_frame(lambda frame: frame.get("method") == "session/update" and frame.get("params", {}).get("update", {}).get("sessionUpdate") == "tool_call_update" and frame.get("params", {}).get("update", {}).get("status") == "completed", timeout=30)
        if not wait_provider(provider["request_log"], lambda row: row.get("tool_result_count", 0) >= 1, timeout=20):
            raise RuntimeError("post-tool Provider request was not observed before process kill")
        case.event("fault.injected", fault=fault, injection_point="after-tool-result-before-turn-completion", control="process.kill")
        client.kill()
        interrupted = True
        return client, {"result": {"stopReason": "process_killed"}}, interrupted
    else:
        response = client.wait_response(prompt_id, timeout=60)

    if response is None:
        raise RuntimeError("missing ACP prompt response")
    if "error" in response:
        raise RuntimeError(f"ACP prompt failed: {response}")
    return client, response, interrupted


def close_client(client: AcpClient | None, case: CaseLedger, *, session_id: str | None = None) -> None:
    if client is None:
        return
    if session_id and client.process.poll() is None:
        try:
            closed = client.close_session(session_id)
            case.event("candidate.session.closed", ok="error" not in closed)
        except Exception as error:
            case.event("candidate.session.close_error", error=repr(error))
    if client.process.poll() is None:
        client.close()


def verify_c3(case: CaseLedger, invocation_count: int, expected_duplicates: int, client: AcpClient | None) -> dict[str, Any]:
    case.refresh()
    schedule = read_jsonl(case.schedule_path)
    attempts = read_jsonl(case.attempts_path)
    events = read_jsonl(case.events_path)
    effects, tool_results = case.update_effect_status()
    results = read_jsonl(case.results_path)
    duplicate_count = sum(item.get("type") == "idempotency.duplicate" for item in events)
    required_ids = all(item.get("run_id") == case.run_id and item.get("schedule_id") == case.schedule_id and item.get("idempotency_key") == case.idempotency_key for item in events)
    passed = all([
        case.state.get("candidate_session_id") is not None,
        case.state.get("adapter_turn_id") is not None,
        len(schedule) == invocation_count,
        len(attempts) == invocation_count * 2,
        duplicate_count == expected_duplicates,
        len(effects) == 1,
        len(tool_results) >= 1,
        len(results) == 1,
        case.state.get("status") == "completed",
        case.state.get("effect_status") == "applied",
        required_ids,
        case.state.get("candidate_tool_call_observed", False),
    ])
    return {
        "scenario": case.state["scenario"],
        "status": "pass" if passed else "fail",
        "observed": {"schedule_records": len(schedule), "attempt_records": len(attempts), "duplicate_events": duplicate_count, "effect_records": len(effects), "tool_result_records": len(tool_results), "result_records": len(results), "candidate_session_id": case.state.get("candidate_session_id"), "adapter_turn_id": case.state.get("adapter_turn_id"), "candidate_tool_calls": len(client.tool_calls) if client else 0},
        "checks": {"one_effect_per_key": len(effects) == 1, "duplicate_delivery_suppressed": duplicate_count == expected_duplicates, "attempt_history_complete": len(attempts) == invocation_count * 2, "ids_correlated": required_ids, "durable_result": len(results) == 1, "candidate_tool_call_observed": case.state.get("candidate_tool_call_observed", False)},
        "evidence_dir": str(case.case_dir),
    }


def run_c3_case(output_dir: Path, scenario: str, repeat: int, entrypoint: Path) -> dict[str, Any]:
    case_dir = output_dir / scenario / f"repeat-{repeat:02d}"
    case = prepare_case(case_dir, f"w8-deepseek-c3-{scenario}-{repeat:02d}", scenario, tool_class="idempotent")
    provider = None
    client: AcpClient | None = None
    session_id: str | None = None
    try:
        command = tool_command(case, "idempotent")
        provider = start_provider(case.case_dir, "process_interrupt" if scenario == "interrupted_retry" else "normal", command, command)
        for spec in C3_SCENARIOS[scenario]:
            mode, kind = spec.split(":", 1)
            case.schedule(kind, missed=kind == "missed", late=kind == "delayed")
            attempt_id = f"{case.run_id}:attempt-{len(read_jsonl(case.attempts_path)) // 2 + 1:03d}"
            case.attempt(attempt_id, mode, "started", "claimed")
            case.refresh()
            if case.state.get("status") == "completed":
                if mode == "resume":
                    case.event("recovery.already-completed", trigger_kind=kind, decision="no-candidate-dispatch")
                    outcome = "already-completed"
                else:
                    case.event("idempotency.duplicate", trigger_kind=kind, decision="no-candidate-dispatch")
                    outcome = "deduplicated"
                case.attempt(attempt_id, mode, "terminal", outcome)
                continue
            case.set_state(phase="claimed", last_checkpoint="idempotency-claimed", effect_status="pending")
            fault = "process_interrupt" if scenario == "interrupted_retry" and mode == "trigger" and kind == "interrupted" else None
            client, response, interrupted = run_candidate_once(case, provider, entrypoint, fault=fault, tool_class="idempotent")
            case.update_effect_status()
            session_id = case.state.get("candidate_session_id")
            if interrupted:
                client.close()
                client, _ = recover_candidate(case, case.case_dir, case.case_dir / "dsh-home", entrypoint, provider, reason=fault or "interrupted", tool_class="idempotent")
                session_id = case.state.get("candidate_session_id")
            else:
                case.set_state(status="completed", phase="completed", last_checkpoint="turn-completed")
                case.finish_result("completed", effect_count=len(read_jsonl(case.effects_path)), tool_result_count=len(read_jsonl(case.tool_results_path)))
            case.attempt(attempt_id, mode, "terminal", response.get("result", {}).get("stopReason", "completed"))
        result = verify_c3(case, len(C3_SCENARIOS[scenario]), 1 if scenario == "interrupted_retry" else len(C3_SCENARIOS[scenario]) - 1, client)
        write_json(case_dir / "result.json", result)
        return result
    except Exception as error:
        case.event("run.error", error=repr(error))
        case.set_state(status="unknown", phase="stop", last_checkpoint="error", safe_stop_reason=repr(error))
        return {"scenario": scenario, "status": "unknown", "error": repr(error), "evidence_dir": str(case_dir)}
    finally:
        close_client(client, case, session_id=session_id)
        stop_provider(provider)


def verify_c4(case: CaseLedger, fault: str, tool_class: str, initial: dict[str, Any], client: AcpClient | None) -> dict[str, Any]:
    case.refresh()
    events = read_jsonl(case.events_path)
    effects, tool_results = case.update_effect_status()
    results = read_jsonl(case.results_path)
    approvals = [item for item in events if item.get("type") == "candidate.permission.request"]
    faults = [item for item in events if item.get("type") == "fault.injected"]
    reconciled = [item for item in events if item.get("type") == "side_effect.reconciled"]
    physical_effects = sum(item.get("physical_effect_count", 0) for item in effects)
    retry_count = case.state.get("retry_count", 99)
    expected_approval = tool_class == "approval-required"
    approval_observed = bool(approvals)
    recovery_controls_pass = all([
        initial.get("interrupted") is True,
        case.state.get("candidate_session_id") is not None,
        case.state.get("adapter_turn_id") is not None,
        bool(faults),
        case.state.get("status") in {"completed", "safe_stopped"},
        case.state.get("status") != "unknown",
        retry_count <= 1,
        physical_effects <= 1,
        len(effects) <= 1,
        len(results) <= 1,
        bool(reconciled) or case.state.get("status") == "safe_stopped",
        case.state.get("candidate_tool_call_observed", False),
    ])
    status = "unknown" if recovery_controls_pass and expected_approval and not approval_observed else ("pass" if recovery_controls_pass and (not expected_approval or approval_observed) else "fail")
    return {
        "case_id": case.case_dir.name,
        "fault": fault,
        "tool_class": tool_class,
        "status": status,
        **({"unknown_reason": "DeepSeek ACP did not emit candidate permission request for approval-required tool"} if status == "unknown" else {}),
        "observed": {"final_status": case.state.get("status"), "retry_count": retry_count, "effect_records": len(effects), "tool_result_records": len(tool_results), "physical_effects": physical_effects, "result_records": len(results), "permission_requests": len(approvals), "fault_records": len(faults), "reconcile_events": len(reconciled), "candidate_session_id": case.state.get("candidate_session_id"), "adapter_turn_id": case.state.get("adapter_turn_id"), "candidate_turn_id_observed": case.state.get("candidate_turn_id_observed", False)},
        "checks": {"real_deepseek_interruption_or_timeout": initial.get("interrupted") is True, "state_not_lost": case.state.get("candidate_session_id") is not None, "retry_bounded": retry_count <= 1, "unsafe_effect_duplicate_free": physical_effects <= 1, "reconcile_or_safe_stop": bool(reconciled) or case.state.get("status") == "safe_stopped", "candidate_tool_call_observed": case.state.get("candidate_tool_call_observed", False), "candidate_native_approval_observed": approval_observed, "candidate_turn_id_observed": case.state.get("candidate_turn_id_observed", False)},
        "evidence_dir": str(case.case_dir),
    }


def run_c4_case(output_dir: Path, fault: str, tool_class: str, repeat: int, entrypoint: Path) -> dict[str, Any]:
    case_dir = output_dir / fault / tool_class / f"repeat-{repeat:02d}"
    case = prepare_case(case_dir, f"w8-deepseek-c4-{fault}-{tool_class}-{repeat:02d}", f"c4:{fault}", tool_class=tool_class, fault=fault)
    provider = None
    client: AcpClient | None = None
    session_id: str | None = None
    try:
        initial_sleep = 700 if fault == "tool_timeout" else 0
        provider_mode = fault
        initial_command = tool_command(case, tool_class, sleep_ms=initial_sleep)
        retry_command = tool_command(case, tool_class)
        provider = start_provider(case.case_dir, provider_mode, initial_command, retry_command)
        client, response, interrupted = run_candidate_once(case, provider, entrypoint, fault=fault, tool_class=tool_class)
        session_id = case.state.get("candidate_session_id")
        case.update_effect_status()
        if interrupted:
            client.close()
            client, response = recover_candidate(case, case.case_dir, case.case_dir / "dsh-home", entrypoint, provider, reason=fault, tool_class=tool_class)
            session_id = case.state.get("candidate_session_id")
        result = verify_c4(case, fault, tool_class, {"interrupted": interrupted, "stop_reason": response.get("result", {}).get("stopReason")}, client)
        write_json(case_dir / "result.json", result)
        return result
    except Exception as error:
        case.event("run.error", error=repr(error))
        case.set_state(status="unknown", phase="stop", last_checkpoint="error", safe_stop_reason=repr(error))
        return {"case_id": case_dir.name, "fault": fault, "tool_class": tool_class, "status": "unknown", "error": repr(error), "evidence_dir": str(case_dir)}
    finally:
        close_client(client, case, session_id=session_id)
        stop_provider(provider)


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def preflight(candidate_repo: Path, entrypoint: Path) -> dict[str, Any]:
    from evaluation.runner.run_deepseek_challenger import candidate_preflight
    return candidate_preflight(candidate_repo, entrypoint, load_manifest())


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest()
    candidate_repo = args.candidate_repo.resolve()
    entrypoint = (args.candidate_entry or (candidate_repo / manifest["runtime"]["entrypoint"])).resolve()
    check = preflight(candidate_repo, entrypoint)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "preflight.json", check)
    if check["status"] != "pass":
        summary = {"schema": SCHEMA, "status": "blocked", "classification": "acceptance/evaluation", "candidate": manifest, "preflight": check, "candidate_status": "unknown/stop"}
        write_json(output / "summary.json", summary)
        return summary

    if args.mode == "c3":
        cases = [run_c3_case(output, scenario, repeat, entrypoint) for scenario in C3_SCENARIOS for repeat in range(1, args.repeats + 1)]
        passed = sum(case.get("status") == "pass" for case in cases)
        summary = {
            "schema": SCHEMA,
            "mode": "c3",
            "classification": "acceptance/evaluation",
            "candidate": {"name": "DeepSeek Harness", "version": DEEPSEEK_VERSION, "entrypoint": str(entrypoint), "acp": True},
            "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE), "effect_sink_reused_from": str(EFFECT_SINK)},
            "threshold": {"scenarios": list(C3_SCENARIOS), "repeats_per_scenario": args.repeats, "same_key_effective_side_effects": 1, "duplicate_extra_effects": 0, "native_scheduler": "not measured; external deterministic trigger"},
            "status": "pass-with-composition" if passed == len(cases) else "unknown/stop",
            "cases_passed": passed,
            "cases_total": len(cases),
            "checks": {"all_cases_pass": passed == len(cases), "one_effect_per_key": all(case.get("checks", {}).get("one_effect_per_key") for case in cases if case.get("status") == "pass"), "missing_evidence_stops": True},
            "native_capability_boundary": {"scheduler": "not measured", "durable_owner": "composition adapter", "candidate_turn_identity": "not exposed by ACP; adapter prompt id recorded"},
            "cases": cases,
        }
    else:
        cases = [run_c4_case(output, fault, tool_class, repeat, entrypoint) for fault in C4_FAULTS for tool_class in C4_TOOL_CLASSES for repeat in range(1, args.repeats + 1)]
        passed = sum(case.get("status") == "pass" for case in cases)
        unknown = sum(case.get("status") == "unknown" for case in cases)
        summary = {
            "schema": SCHEMA,
            "mode": "c4",
            "classification": "acceptance/evaluation",
            "candidate": {"name": "DeepSeek Harness", "version": DEEPSEEK_VERSION, "entrypoint": str(entrypoint), "acp": True},
            "adapter": {"version": ADAPTER_VERSION, "fixture": str(FIXTURE), "effect_sink_reused_from": str(EFFECT_SINK)},
            "threshold": {"faults": list(C4_FAULTS), "tool_classes": list(C4_TOOL_CLASSES), "repeats_per_fault_tool_class": args.repeats, "critical_state_loss": 0, "unsafe_side_effect_duplicate": 0, "max_retry_count": 1, "reconcile_before_resume_or_retry": True},
            "status": "pass-with-composition" if passed == len(cases) else "unknown/stop",
            "cases_passed": passed,
            "cases_total": len(cases),
            "unknown_cases": unknown,
            "failed_cases": sum(case.get("status") == "fail" for case in cases),
            "checks": {"all_cases_pass": passed == len(cases), "recovery_controls_pass": all(case.get("checks", {}).get("reconcile_or_safe_stop") for case in cases), "critical_state_loss_zero": all(case.get("checks", {}).get("state_not_lost") for case in cases), "unsafe_side_effect_duplicates_zero": all(case.get("checks", {}).get("unsafe_effect_duplicate_free") for case in cases), "retry_bounded": all(case.get("checks", {}).get("retry_bounded") for case in cases), "candidate_turn_identity_observed": False, "missing_evidence_stops": True},
            "native_capability_boundary": {"candidate_session_resume": "measured", "candidate_turn_id": "not exposed in ACP v1 updates", "candidate_permission_request": "measured per case; absent remains unknown for approval-required", "durable_effect_owner": "composition adapter"},
            "cases": cases,
        }
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("c3", "c4"), required=True)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--candidate-entry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    summary = run(args)
    print(json.dumps({"status": summary["status"], "output": str(args.output.resolve()), "mode": args.mode, "cases": f"{summary.get('cases_passed', 0)}/{summary.get('cases_total', 0)}", "unknown_cases": summary.get("unknown_cases", 0)}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"pass-with-composition", "pass"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
