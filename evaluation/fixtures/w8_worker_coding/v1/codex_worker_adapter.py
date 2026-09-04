#!/usr/bin/env python3
"""Run one real Codex app-server turn behind the H3 Worker wire.

This process is intentionally a transport worker, not a second durable owner:
it receives one bridge request, supervises one Codex app-server process, emits
reviewable case-local artifacts, and returns one ``result`` envelope.  The
outer WorkerBridge remains responsible for owner state and safe-stop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional


SCHEMA = "zworkbench.worker.v1"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class CodexProcess:
    """Small JSON-RPC client that never writes CompositionOwner state."""

    def __init__(self, executable: Path, code_home: Path, provider_endpoint: str) -> None:
        self.executable = executable
        self.code_home = code_home
        self.provider_endpoint = provider_endpoint.rstrip("/")
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.selector = selectors.DefaultSelector()
        self.stdout_buffer = bytearray()
        self.next_id = 1
        self.messages: list[Dict[str, Any]] = []
        self.agent_text: Dict[str, str] = {}

    def start(self) -> None:
        self.code_home.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable),
            "app-server",
            "--listen",
            "stdio://",
            "-c",
            'model_provider="h3-loopback"',
            "-c",
            'model="fake-model"',
            "-c",
            'model_providers.h3-loopback.name="H3 Loopback"',
            "-c",
            'model_providers.h3-loopback.wire_api="responses"',
            "-c",
            f'model_providers.h3-loopback.base_url="{self.provider_endpoint}/v1"',
            "--disable",
            "plugins",
            "--disable",
            "apps",
        ]
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ"}
        }
        environment.update({"CODEX_HOME": str(self.code_home), "CODEX_CI": "1"})
        self.process = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=False,
            close_fds=True,
        )
        if self.process.stdout is None:
            raise RuntimeError("Codex app-server stdout is unavailable")
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.request("initialize", {"clientInfo": {"name": "zworkbench-h3-worker", "version": "v1"}})
        self.notify("initialized", {})

    def request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = self.read_one(max(0.01, deadline - time.monotonic()))
            if item is not None and item.get("id") == request_id:
                if "error" in item:
                    raise RuntimeError(f"Codex {method} failed: {item['error']}")
                result = item.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError(f"Codex {method} returned no result")
                return result
        raise TimeoutError(f"Codex request timed out: {method}")

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def send(self, message: Dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None or self.process.poll() is not None:
            raise RuntimeError("Codex app-server is not running")
        self.process.stdin.write((canonical(message) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def read_one(self, timeout: float) -> Optional[Dict[str, Any]]:
        if self.process is None or self.process.stdout is None:
            return None
        deadline = time.monotonic() + timeout
        line = None
        while line is None:
            if b"\n" in self.stdout_buffer:
                line, _, remainder = self.stdout_buffer.partition(b"\n")
                self.stdout_buffer = bytearray(remainder)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                return None
            data = os.read(self.process.stdout.fileno(), 64 * 1024)
            if not data:
                raise RuntimeError("Codex app-server closed stdout")
            self.stdout_buffer.extend(data)
        item = json.loads(line.decode("utf-8"))
        if not isinstance(item, dict):
            raise RuntimeError("Codex app-server emitted a non-object message")
        self.messages.append(item)
        method = item.get("method")
        params = item.get("params") or {}
        if method == "item/agentMessage/delta":
            turn_id = params.get("turnId")
            if isinstance(turn_id, str):
                self.agent_text[turn_id] = self.agent_text.get(turn_id, "") + str(params.get("delta", ""))
        if method == "item/completed":
            message = params.get("item") or {}
            turn_id = params.get("turnId")
            if isinstance(message, dict) and message.get("type") == "agentMessage" and isinstance(turn_id, str):
                text = message.get("text")
                if not isinstance(text, str):
                    content = message.get("content")
                    if isinstance(content, list):
                        text = "".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and isinstance(part.get("text"), str)
                        )
                if isinstance(text, str) and text:
                    self.agent_text[turn_id] = text
        if "method" in item and "id" in item:
            # The H3 read-only slice has no interactive capability.  Deny it
            # explicitly so it cannot turn into an unrecorded side effect.
            self.send({
                "jsonrpc": "2.0",
                "id": item["id"],
                "error": {"code": -32001, "message": "H3 Worker denies interactive server requests"},
            })
            raise RuntimeError(f"unexpected Codex server request: {method}")
        return item

    def start_turn(self, prompt: str) -> tuple[str, str]:
        thread = self.request(
            "thread/start",
            {
                "cwd": str(Path.cwd()),
                "model": "fake-model",
                "modelProvider": "h3-loopback",
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "ephemeral": False,
            },
        ).get("thread") or {}
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise RuntimeError("Codex thread/start did not return an id")
        turn = self.request(
            "turn/start",
            {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
        ).get("turn") or {}
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not turn_id:
            raise RuntimeError("Codex turn/start did not return an id")
        return thread_id, turn_id

    def wait_turn(self, thread_id: str, turn_id: str) -> Dict[str, Any]:
        # Notifications are independent of request responses.  The app-server
        # may send turn/completed before the turn/start response, in which case
        # request() has already buffered it in self.messages.  Check the
        # ordered buffer before waiting for new output so an already-completed
        # turn cannot be mistaken for a hung Worker.
        for item in self.messages:
            if item.get("method") != "turn/completed":
                continue
            params = item.get("params") or {}
            if params.get("threadId") == thread_id and (params.get("turn") or {}).get("id") == turn_id:
                completed = dict(params.get("turn") or {})
                if completed.get("status") != "completed":
                    raise RuntimeError(f"Codex turn did not complete: {completed.get('status')}")
                return completed
        deadline = time.monotonic() + 60.0
        completed: Optional[Dict[str, Any]] = None
        while time.monotonic() < deadline:
            item = self.read_one(min(0.25, max(0.01, deadline - time.monotonic())))
            if item and item.get("method") == "turn/completed":
                params = item.get("params") or {}
                if params.get("threadId") == thread_id and (params.get("turn") or {}).get("id") == turn_id:
                    completed = dict(params.get("turn") or {})
                    break
        if completed is None:
            raise TimeoutError("Codex turn/completed was not observed")
        if completed.get("status") != "completed":
            raise RuntimeError(f"Codex turn did not complete: {completed.get('status')}")
        return completed

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    os.kill(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.kill(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
        finally:
            try:
                self.selector.unregister(process.stdout)
            except Exception:
                pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            self.process = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--provider-endpoint", required=True)
    args = parser.parse_args()
    request = json.loads(input())
    if request.get("message_type") != "handshake.request":
        raise RuntimeError("H3 Worker requires handshake.request")
    payload = request.get("payload") or {}
    if payload.get("operation") != "read_only_coding":
        raise RuntimeError("H3 Worker requires read_only_coding")
    artifact_root = Path(os.environ["ZWORKBENCH_ARTIFACT_ROOT"]).resolve()
    code_home = artifact_root.parent / "codex-home"
    client = CodexProcess(args.codex.resolve(), code_home, args.provider_endpoint)
    try:
        client.start()
        thread_id, turn_id = client.start_turn(str(payload["prompt"]))
        identity = dict(request["identity"])
        identity.update({"codex_thread_id": thread_id, "codex_turn_id": turn_id, "event_id": "h3-handshake"})
        handshake = dict(request)
        handshake.update({"message_type": "handshake.response", "identity": identity, "payload": {"status": "ready"}})
        print(canonical(handshake), flush=True)
        turn = client.wait_turn(thread_id, turn_id)
        identity.update({"codex_thread_id": thread_id, "codex_turn_id": turn_id, "event_id": "h3-result", "artifact_id": "h3-coding-artifact"})
        diff = artifact_root / "diff.patch"
        tests = artifact_root / "tests.txt"
        semantic = artifact_root / "semantic-result.json"
        runtime_events = artifact_root / "runtime-events.jsonl"
        diff.write_text("", encoding="utf-8")
        command_results = []
        for item in client.messages:
            method = item.get("method")
            event_params = item.get("params") or {}
            event_item = event_params.get("item") or {}
            if method == "item/completed" and event_item.get("type") == "commandExecution":
                command_results.append({"status": event_item.get("status"), "exit_code": event_item.get("exitCode")})
        tests.write_text(
            "Codex app-server read-only turn completed\n"
            + json.dumps({"command_results": command_results}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        semantic_value = {"status": "completed", "text": client.agent_text.get(turn_id, ""), "turn_status": turn.get("status")}
        semantic.write_text(canonical(semantic_value) + "\n", encoding="utf-8")
        runtime_events.write_text(
            "".join(canonical({"method": item.get("method"), "id": item.get("id")}) + "\n" for item in client.messages),
            encoding="utf-8",
        )
        artifacts = {
            "diff": {"path": "diff.patch", "digest": digest(diff), "bytes": diff.stat().st_size},
            "tests": {"path": "tests.txt", "digest": digest(tests), "bytes": tests.stat().st_size},
            "semantic": {"path": "semantic-result.json", "digest": digest(semantic), "bytes": semantic.stat().st_size},
            "runtime_events": {"path": "runtime-events.jsonl", "digest": digest(runtime_events), "bytes": runtime_events.stat().st_size},
        }
        result = {
            "schema": SCHEMA,
            "message_type": "result",
            "identity": identity,
            "provider_identity": request["provider_identity"],
            "replay_mode": request["replay_mode"],
            "policy_digest": request["policy_digest"],
            "environment_digest": request["environment_digest"],
            "workspace_digest": request["workspace_digest"],
            "worker_artifact_identity": request["worker_artifact_identity"],
            "worker_schema_identity": request["worker_schema_identity"],
            "capability_request": None,
            "payload": {
                "status": "completed",
                "operation": "read_only_coding",
                "semantic_result": semantic_value,
                "artifacts": artifacts,
            },
        }
        print(canonical(result), flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
