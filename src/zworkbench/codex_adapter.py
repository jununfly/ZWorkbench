"""Codex app-server adapter for the ZWorkbench composition owner.

The adapter owns the process and JSON-RPC transport seam only.  It does not
implement an agent loop, execute a tool, or make the Codex thread database the
composition source of truth.  A caller supplies a :class:`CompositionOwner`;
each successful ``execute`` call creates one owner run and records the
Codex thread/turn identity, provider identity, environment identity and raw
event-stream digest in that owner.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from .composition import CompositionOwner, InvalidTransition


ADAPTER_SCHEMA = "zworkbench-codex-app-server-adapter/v1"
DEFAULT_CONFIG_OVERRIDES = (
    'oss_provider="ollama"',
    'model_provider="ollama"',
    'model="fake-model"',
)
DEFAULT_DISABLED_FEATURES = ("plugins", "apps")


class CodexAdapterError(RuntimeError):
    """Base error for the Codex adapter."""


class CodexProtocolError(CodexAdapterError):
    """The app-server returned an invalid or unsuccessful JSON-RPC result."""


@dataclass(frozen=True)
class CodexExecution:
    """The bounded result returned after one owner-backed Codex turn."""

    run_id: str
    thread_id: str
    turn_id: str
    status: str
    text: str
    provider_identity: Dict[str, Any]
    event_digest: str
    environment_digest: str
    raw_event_count: int


class CodexAppServerAdapter:
    """A thin, case-local Codex app-server adapter.

    The public interface is deliberately small: construct it with an owner,
    call ``execute`` for one logical run, and close it.  The adapter defaults
    to a minimal inherited environment and an explicit case-local
    ``CODEX_HOME``.  Provider configuration is passed as argv values rather
    than shell text, so the adapter never invokes a shell.
    """

    def __init__(
        self,
        owner: CompositionOwner,
        executable: os.PathLike[str] | str,
        code_home: os.PathLike[str] | str,
        cwd: os.PathLike[str] | str,
        *,
        model: str = "fake-model",
        model_provider: str = "ollama",
        provider_identity: Optional[Mapping[str, Any]] = None,
        sandbox: str = "read-only",
        approval_policy: str = "never",
        config_overrides: Sequence[str] = DEFAULT_CONFIG_OVERRIDES,
        disabled_features: Sequence[str] = DEFAULT_DISABLED_FEATURES,
        event_log: Optional[os.PathLike[str] | str] = None,
        client_name: str = "zworkbench-codex-adapter",
        client_version: str = ADAPTER_SCHEMA,
        extra_environment: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.owner = owner
        self.executable = self._resolve_executable(executable)
        self.code_home = Path(code_home).expanduser().resolve()
        self.cwd = Path(cwd).expanduser().resolve()
        self.model = self._require_text(model, "model")
        self.model_provider = self._require_text(model_provider, "model_provider")
        self.sandbox = self._require_text(sandbox, "sandbox")
        self.approval_policy = self._require_text(approval_policy, "approval_policy")
        self.config_overrides = tuple(self._require_text(item, "config_override") for item in config_overrides)
        self.disabled_features = tuple(self._require_text(item, "disabled_feature") for item in disabled_features)
        self.provider_identity = dict(provider_identity or {})
        self.provider_identity.setdefault("provider", self.model_provider)
        self.provider_identity.setdefault("model", self.model)
        self.event_log = Path(event_log).expanduser().resolve() if event_log else self.code_home.parent / "codex-events.jsonl"
        self.client_name = self._require_text(client_name, "client_name")
        self.client_version = self._require_text(client_version, "client_version")
        self.extra_environment = dict(extra_environment or {})
        self.process: Optional[subprocess.Popen[str]] = None
        self.selector = selectors.DefaultSelector()
        self.messages: list[Dict[str, Any]] = []
        self.next_id = 1
        self.active_run_id: Optional[str] = None
        self._agent_text: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Process and JSON-RPC transport
    # ------------------------------------------------------------------

    def start(self) -> Dict[str, Any]:
        """Start app-server and complete the protocol initialization."""

        if self.process is not None and self.process.poll() is None:
            return {"result": {"already_started": True}}
        self.code_home.mkdir(parents=True, exist_ok=True)
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        environment = self._build_environment()
        command = self.command()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.cwd),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if self.process.stdout is None:
                raise CodexAdapterError("Codex app-server stdout is unavailable")
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            response = self.request(
                "initialize",
                {"clientInfo": {"name": self.client_name, "version": self.client_version}},
            )
            self._require_result(response, "initialize")
            self.notify("initialized", {})
            self._record("adapter.initialized", "app-server", {"command": command})
            return response
        except Exception:
            self.close()
            raise

    def command(self) -> list[str]:
        """Return the exact argv used to launch the fixed app-server."""

        command = [str(self.executable), "app-server", "--listen", "stdio://"]
        for value in self.config_overrides:
            command.extend(("-c", value))
        for feature in self.disabled_features:
            command.extend(("--disable", feature))
        return command

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        message = {"jsonrpc": "2.0", "method": method, "params": dict(params)}
        self._write_message(message)

    def request(self, method: str, params: Mapping[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
        self._write_message(message)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = self.read_one(max(0.01, deadline - time.monotonic()))
            if item is not None and item.get("id") == request_id:
                return item
        raise TimeoutError(f"Codex request timed out: {method}")

    def read_one(self, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        if self.process is None or self.process.stdout is None:
            raise CodexAdapterError("Codex app-server is not running")
        ready = self.selector.select(timeout)
        if not ready:
            return None
        line = self.process.stdout.readline()
        if not line:
            return None
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexProtocolError(f"invalid app-server JSON: {line!r}") from exc
        if not isinstance(item, dict):
            raise CodexProtocolError("app-server JSON-RPC message must be an object")
        self.messages.append(item)
        self._append_event({"direction": "inbound", "message": item})
        if "method" in item and "id" in item:
            self._handle_server_request(item)
        if item.get("method") == "item/agentMessage/delta":
            params = item.get("params") or {}
            turn_id = params.get("turnId")
            if turn_id:
                self._agent_text[turn_id] = self._agent_text.get(turn_id, "") + str(params.get("delta", ""))
        return item

    def wait_for(self, predicate, timeout: float = 30.0) -> Dict[str, Any]:
        for item in self.messages:
            if predicate(item):
                return item
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = self.read_one(min(0.1, max(0.01, deadline - time.monotonic())))
            if item is not None and predicate(item):
                return item
        raise TimeoutError("Codex event wait timed out")

    def _write_message(self, message: Mapping[str, Any]) -> None:
        if self.process is None or self.process.stdin is None or self.process.poll() is not None:
            raise CodexAdapterError("Codex app-server is not running")
        self._append_event({"direction": "outbound", "message": dict(message)})
        self.process.stdin.write(json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _handle_server_request(self, item: Mapping[str, Any]) -> None:
        """Deny unknown/interactive server requests at the transport seam."""

        request_id = item.get("id")
        method = item.get("method")
        decision = {"method": method, "request_id": request_id, "decision": "deny", "reason": "adapter_default_deny"}
        self._record("adapter.server_request.denied", f"server-request-{request_id}", decision)
        if self.active_run_id:
            try:
                self.owner.safe_stop_run(self.active_run_id, f"unsupported Codex server request: {method}")
            except InvalidTransition:
                pass
        self._write_message(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": f"unsupported server request: {method}"}}
        )

    # ------------------------------------------------------------------
    # Owner-backed execution
    # ------------------------------------------------------------------

    def execute(
        self,
        run_id: str,
        prompt: str,
        *,
        task_type: str = "codex.turn",
        input_value: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        timeout: float = 45.0,
    ) -> CodexExecution:
        """Run one Codex turn and persist its identity in the owner."""

        prompt = self._require_text(prompt, "prompt")
        run_metadata = dict(metadata or {})
        run_metadata.update(
            {
                "adapter_schema": ADAPTER_SCHEMA,
                "codex_executable": str(self.executable),
                "codex_home": str(self.code_home),
                "cwd": str(self.cwd),
                "model": self.model,
                "model_provider": self.model_provider,
            }
        )
        self.owner.create_run(
            run_id,
            task_type,
            input_value if input_value is not None else {"prompt": prompt},
            run_metadata,
        )
        self.owner.start_run(run_id)
        self.active_run_id = run_id
        try:
            self.start()
            thread_id = self._thread_start()
            turn_id = self._turn_start(thread_id, prompt)
            completed = self._wait_turn_completed(thread_id, turn_id, timeout)
            status = str(completed.get("status", "unknown"))
            if status != "completed":
                raise CodexProtocolError(f"Codex turn did not complete: {status}")
            event_digest = self.event_digest()
            environment_digest = self.environment_digest()
            text = self._agent_text.get(turn_id, "")
            self._record(
                "adapter.thread",
                f"{run_id}:thread:{thread_id}",
                {"thread_id": thread_id, "provider_identity": self.provider_identity},
            )
            self._record(
                "adapter.turn",
                f"{run_id}:turn:{turn_id}",
                {"thread_id": thread_id, "turn_id": turn_id, "status": status, "text": text},
            )
            self.owner.record_replay_metadata(
                run_id,
                f"{run_id}:recorded-view",
                "recorded_view",
                event_digest,
                environment_digest,
                self.provider_identity,
                {"adapter_schema": ADAPTER_SCHEMA, "thread_id": thread_id, "turn_id": turn_id},
            )
            semantic = {
                "status": status,
                "text": text,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "provider_identity": self.provider_identity,
                "event_digest": event_digest,
                "environment_digest": environment_digest,
            }
            self.owner.complete_run(run_id, semantic)
            return CodexExecution(
                run_id,
                thread_id,
                turn_id,
                status,
                text,
                dict(self.provider_identity),
                event_digest,
                environment_digest,
                len(self.messages),
            )
        except Exception as exc:
            self._fail_owner_run(run_id, exc)
            raise
        finally:
            self.active_run_id = None

    def _thread_start(self) -> str:
        response = self.request(
            "thread/start",
            {
                "cwd": str(self.cwd),
                "model": self.model,
                "modelProvider": self.model_provider,
                "sandbox": self.sandbox,
                "approvalPolicy": self.approval_policy,
                "ephemeral": False,
            },
        )
        result = self._require_result(response, "thread/start")
        thread = result.get("thread") or {}
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexProtocolError("thread/start did not return thread.id")
        return thread_id

    def _turn_start(self, thread_id: str, prompt: str) -> str:
        response = self.request("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]})
        result = self._require_result(response, "turn/start")
        turn = result.get("turn") or {}
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexProtocolError("turn/start did not return turn.id")
        return turn_id

    def _wait_turn_completed(self, thread_id: str, turn_id: str, timeout: float) -> Dict[str, Any]:
        predicate = lambda item: item.get("method") == "turn/completed" and item.get("params", {}).get("threadId") == thread_id and item.get("params", {}).get("turn", {}).get("id") == turn_id
        started = time.monotonic()
        try:
            event = self.wait_for(predicate, timeout=min(timeout, 0.5))
        except TimeoutError:
            try:
                self.request("thread/read", {"threadId": thread_id}, timeout=5)
            except (TimeoutError, CodexAdapterError, CodexProtocolError):
                pass
            event = self.wait_for(predicate, timeout=max(0.1, timeout - (time.monotonic() - started)))
        return dict(event.get("params", {}).get("turn") or {})

    def _fail_owner_run(self, run_id: str, error: Exception) -> None:
        try:
            run = self.owner.get_run(run_id)
            if run["status"] in {"created", "running", "waiting_approval", "recovering"}:
                self.owner.fail_run(run_id, {"type": type(error).__name__, "message": str(error)})
        except Exception:
            # Preserve the original adapter failure.  The owner is fail-closed
            # and its persisted status remains the evidence to inspect.
            return

    # ------------------------------------------------------------------
    # Evidence and lifecycle helpers
    # ------------------------------------------------------------------

    def _record(self, kind: str, source_id: str, value: Mapping[str, Any]) -> None:
        if self.active_run_id:
            self.owner.record_result(self.active_run_id, kind, dict(value), source_id)

    def _append_event(self, value: Mapping[str, Any]) -> None:
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def event_digest(self) -> str:
        if not self.event_log.exists():
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(self.event_log.read_bytes()).hexdigest()

    def environment_digest(self) -> str:
        identity = {
            "adapter_schema": ADAPTER_SCHEMA,
            "executable": str(self.executable),
            "code_home": str(self.code_home),
            "cwd": str(self.cwd),
            "model": self.model,
            "model_provider": self.model_provider,
            "sandbox": self.sandbox,
            "approval_policy": self.approval_policy,
            "config_overrides": list(self.config_overrides),
            "disabled_features": list(self.disabled_features),
            "provider_identity": self.provider_identity,
        }
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def close(self) -> None:
        """Stop app-server and persist stderr without deleting case state."""

        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=6)
            stderr = process.stderr.read() if process.stderr else ""
            stderr_path = self.event_log.with_name("codex-stderr.log")
            stderr_path.write_text(stderr, encoding="utf-8")
        finally:
            if process.stdout is not None:
                try:
                    self.selector.unregister(process.stdout)
                except Exception:
                    pass
            self.process = None

    def __enter__(self) -> "CodexAppServerAdapter":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def _build_environment(self) -> Dict[str, str]:
        allowed = {"PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ"}
        environment = {key: value for key, value in os.environ.items() if key in allowed}
        environment.update({"CODEX_HOME": str(self.code_home), "CODEX_CI": "1"})
        environment.update(self.extra_environment)
        return environment

    @staticmethod
    def _resolve_executable(executable: os.PathLike[str] | str) -> Path:
        value = os.fspath(executable)
        resolved = Path(value).expanduser().resolve() if os.sep in value else Path(shutil.which(value) or value).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Codex executable not found: {executable}")
        return resolved

    @staticmethod
    def _require_text(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _require_result(response: Mapping[str, Any], method: str) -> Dict[str, Any]:
        if "error" in response:
            raise CodexProtocolError(f"{method} failed: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise CodexProtocolError(f"{method} returned no result")
        return result
