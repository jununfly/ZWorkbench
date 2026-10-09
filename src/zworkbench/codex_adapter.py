"""Codex app-server adapter for the ZWorkbench composition owner.

The adapter owns the process and JSON-RPC transport seam only.  It does not
implement an agent loop, execute a tool, or make the Codex thread database the
composition source of truth.  A caller supplies a :class:`CompositionOwner`;
each successful ``execute`` call creates one owner run and records the
Codex thread/turn identity, provider identity, environment identity and raw
event-stream digest in that owner.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import time
import tomllib
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from .composition import (
    CompositionOwner,
    EVIDENCE_SOURCE_OUTER_COMPOSED,
    InvalidTransition,
)
from .provider_vocabulary import TRANSPORT_LOOPBACK_ONLY
from .subprocess_supervisor import terminate_process


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


# ----------------------------------------------------------------------
# Failure classification (issue #39 S1 / node 1-6-4)
# ----------------------------------------------------------------------

FAILURE_NETWORK = "network"
FAILURE_RATE_LIMIT = "rate_limit"
FAILURE_UNKNOWN = "unknown"

# S1 is single-Provider with no failover: a network / rate-limit / unknown
# provider failure is terminal and fail-closed here.  The recorded bucket is
# the durable signal a future S2 failover would consume to choose policy
# (network -> try a second Provider, rate_limit -> backoff, unknown -> stop).
SAFE_STOP_CATEGORIES = frozenset({FAILURE_NETWORK, FAILURE_RATE_LIMIT, FAILURE_UNKNOWN})

# errno values that signal a transient transport/network failure rather than a
# local filesystem or programming error.
_NETWORK_ERRNOS = frozenset({
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ETIMEDOUT,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    errno.ENETDOWN,
    errno.ENETRESET,
    errno.EPIPE,
})


def classify_provider_failure(exc: BaseException) -> str:
    """Map a provider/transport exception to a coarse failure bucket.

    Buckets:

    * ``network``    — transport timeouts, dropped/refused connections, broken
                       pipes, and DNS resolution failures.
    * ``rate_limit`` — the Provider signalled throttling (HTTP 429 or rate-limit
                       phrasing in the JSON-RPC error payload).
    * ``unknown``    — anything else (protocol errors, unexpected exceptions,
                       process death).  Unclassified == not safely retryable.

    The owner records this bucket so the failure is observable and a future S2
    failover can route on it; see
    :meth:`CodexAppServerAdapter._handle_owner_failure` for the S1 terminal
    policy.
    """

    message = str(exc).lower()
    if "429" in message or ("rate" in message and ("limit" in message or "throttl" in message)):
        return FAILURE_RATE_LIMIT

    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return FAILURE_NETWORK

    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) in _NETWORK_ERRNOS:
            return FAILURE_NETWORK
        # socket.gaierror / herror are DNS resolution failures (OSError subclass).
        if isinstance(exc, (socket.gaierror, socket.herror)):
            return FAILURE_NETWORK

    return FAILURE_UNKNOWN


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
        provider_config_path: Optional[os.PathLike[str] | str] = None,
        host_enforcement: bool = False,
    ) -> None:
        self.owner = owner
        self.executable = self._resolve_executable(executable)
        self.code_home = Path(code_home).expanduser().resolve()
        self.cwd = Path(cwd).expanduser().resolve()
        self.sandbox = self._require_text(sandbox, "sandbox")
        self.approval_policy = self._require_text(approval_policy, "approval_policy")
        self.config_overrides = tuple(self._require_text(item, "config_override") for item in config_overrides)
        self.disabled_features = tuple(self._require_text(item, "disabled_feature") for item in disabled_features)
        # Identity↔transport single-source binding (issue #39, S1 step-0 gate).
        # provider_identity is the sole source of truth: the transport-facing
        # model/model_provider are DERIVED from it and are never back-filled in.
        # An incomplete identity fails closed instead of being silently defaulted.
        # The historical loopback default is used only when no identity is given
        # (no real provider receipt is produced on that path).
        identity = dict(provider_identity or {})
        if not identity:
            identity = {
                "provider": model_provider,
                "model": model,
                "endpoint": "loopback",
                "transport": TRANSPORT_LOOPBACK_ONLY,
            }
        else:
            # The adapter binds transport to provider/model and records endpoint,
            # so these three are required. ``transport`` itself is validated
            # upstream by the DSH runtime (issue #39 / #40 are kept orthogonal),
            # not re-checked here. ``model_provider`` is sourced from the identity
            # when present (see the assignment below) and is not part of this
            # completeness gate, because the loopback-default path builds the
            # identity from the constructor argument instead.
            missing = {"provider", "model", "endpoint"} - set(identity)
            if missing:
                raise CodexAdapterError(
                    "provider_identity must include {0} "
                    "(identity↔transport single-source binding, issue #39)".format(
                        ", ".join(sorted(missing))
                    )
                )
        self.provider_identity = identity
        self.model = self._require_text(str(identity["model"]), "model")
        # #39 single-source binding (S1 step-0 gate): model_provider is sourced from
        # provider_identity when present, otherwise from the explicit constructor
        # argument (which is what built the loopback-default identity). It is NEVER
        # silently derived from identity["provider"]: doing so conflates the
        # profile/provider NAME with the model-provider CATEGORY and breaks the
        # identity<->transport binding. E.g. a profile named "ark-test" with
        # model_provider "custom" must record model_provider "custom", not "ark-test".
        model_provider_value = identity.get("model_provider")
        if model_provider_value is None:
            model_provider_value = model_provider
        self.model_provider = self._require_text(str(model_provider_value), "model_provider")
        self.event_log = Path(event_log).expanduser().resolve() if event_log else self.code_home.parent / "codex-events.jsonl"
        self.client_name = self._require_text(client_name, "client_name")
        self.client_version = self._require_text(client_version, "client_version")
        self.extra_environment = dict(extra_environment or {})
        # Explicit Codex config path (the real Provider's config.toml). When set,
        # start() stages it into CODEX_HOME (the case-local code_home dir) so Codex
        # discovers the [model_providers.<name>] table. Codex has no --config <file>
        # flag (its -c is key=value only); it reads $CODEX_HOME/config.toml. So we
        # must place the provider config there. Without this, a custom
        # model_provider is unknown to Codex and the turn fails closed
        # (CodexProtocolError -> safe_stopped). See roadmap node 1-9-1.
        self.provider_config_path = Path(provider_config_path).expanduser().resolve() if provider_config_path else None
        # ADR 0008 host enforcement (roadmap 1-9-2 / 1-9-3 direction b): when set,
        # ZWorkbench's intent is to be the single sandbox authority. In practice
        # (1-9-3 direction b) this means command() prepends the
        # --dangerously-bypass-approvals-and-sandbox flag and ZWorkbench does NOT
        # wrap Codex in a macOS seatbelt — a nested sandbox_apply always fails with
        # EPERM and blocks workspace reads. Read-only enforcement then relies on
        # Codex's own sandbox (non-sandboxed hosts) or the external host seatbelt
        # (sandboxed hosts). This diverges from ADR 0008's wrap model but is the
        # documented, accepted decision; the residual risk (no in-process
        # refuse-to-start) is tracked there.
        self.host_enforcement = bool(host_enforcement)
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.selector = selectors.DefaultSelector()
        self.stdout_buffer = bytearray()
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
        # Resident runtime registry: claim a slot before spawning the long-lived
        # app-server process (sub-07 Backlog #3). Released in close(). Fail-closed
        # if the ≤3 cap is exceeded.
        self.owner.resident_registry.acquire(f"codex-app-server:{self.code_home}", "codex-app-server")
        self.code_home.mkdir(parents=True, exist_ok=True)
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        # Stage the real Provider's config into CODEX_HOME so Codex can discover
        # [model_providers.<name>]. Codex reads $CODEX_HOME/config.toml; it has no
        # --config <file> flag. Keeps CODEX_HOME case-local (state isolation) while
        # still giving Codex the provider config + inline token. See node 1-9-1.
        if self.provider_config_path is not None:
            self._stage_provider_config()
        environment = self._build_environment()
        command = self._build_spawn_argv()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.cwd),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
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

    def _stage_provider_config(self) -> None:
        """Copy the resolved provider config into CODEX_HOME/config.toml.

        Codex reads its base config from ``$CODEX_HOME/config.toml``; there is no
        ``--config <file>`` flag, so the only way to hand Codex a custom provider
        (and its inline bearer token) while keeping CODEX_HOME case-local is to
        stage the file there. Idempotent: never clobbers an existing staged file.
        Relative sibling files referenced by the config (e.g. ``model_catalog_json``)
        are copied alongside so Codex does not error on a missing path.
        """

        assert self.provider_config_path is not None
        staged = self.code_home / "config.toml"
        if staged.exists():
            return
        shutil.copyfile(self.provider_config_path, staged)
        try:
            with self.provider_config_path.open("rb") as handle:
                data = tomllib.load(handle)
            catalog = data.get("model_catalog_json")
            if isinstance(catalog, str) and not os.path.isabs(catalog):
                src = self.provider_config_path.parent / catalog
                if src.is_file():
                    shutil.copyfile(src, self.code_home / catalog)
        except Exception:
            # Staging the catalog is best-effort; a missing catalog is non-fatal
            # for the read-only coding task and Codex will warn, not abort.
            pass

    def command(self) -> list[str]:
        """Return the exact argv used to launch the fixed app-server."""

        command = [str(self.executable)]
        if self.host_enforcement:
            # Roadmap node 1-9-2 / 1-9-3 direction (b): make ZWorkbench the single
            # sandbox authority in intent. This global flag tells Codex it is
            # externally sandboxed so it should not re-seatbelt its own shell
            # children via ``sandbox-exec`` (which fails with EPERM when the Codex
            # process tree is already seatbelt-sandboxed). It additionally bypasses
            # approvals. NOTE: in app-server mode the sandbox policy is NOT
            # overridable with a ``-s/--sandbox`` flag (unexpected argument) and
            # there is no ``sandbox_mode="dangerously-disable"`` value — this
            # global bypass flag is the only lever. Empirically the flag is
            # necessary but not sufficient to restore shell file reads when Codex
            # itself is launched under a host seatbelt (macOS forbids nested
            # ``sandbox_apply``); ZWorkbench does NOT wrap Codex in a macOS
            # seatbelt (see _build_spawn_argv).
            command.append("--dangerously-bypass-approvals-and-sandbox")
        command.extend(("app-server", "--listen", "stdio://"))
        for value in self.config_overrides:
            command.extend(("-c", value))
        for feature in self.disabled_features:
            command.extend(("--disable", feature))
        return command

    def _build_spawn_argv(self) -> list[str]:
        """Return the argv used to launch the app-server process.

        When ``host_enforcement`` is set, :meth:`command` already prepends the
        ``--dangerously-bypass-approvals-and-sandbox`` flag. ZWorkbench does NOT
        wrap Codex in a macOS seatbelt (roadmap 1-9-3 direction b): macOS forbids
        nested ``sandbox_apply``, so wrapping Codex — which then runs its own
        internal ``sandbox-exec`` around shell tools — always fails with EPERM and
        blocks workspace reads. Instead Codex applies its own sandbox internally
        on non-sandboxed hosts; on a sandboxed host the external host seatbelt is
        the boundary. This diverges from ADR 0008's "ZWorkbench is the single
        sandbox authority" wrap model, but is the documented, accepted decision;
        the residual risk (no in-process refuse-to-start if no enforcer applies)
        is tracked in ADR 0008 / roadmap 1-9-3.
        """

        command = self.command()
        if not self.host_enforcement:
            return command
        # Roadmap 1-9-3 (direction b): do NOT wrap Codex in a macOS seatbelt.
        # macOS forbids nested ``sandbox_apply``; wrapping Codex (which then runs
        # its own internal ``sandbox-exec`` around shell tools) always fails with
        # EPERM and blocks workspace reads. Codex applies its own sandbox
        # internally (no nesting) so it can read files; on a sandboxed host the
        # external host seatbelt is the boundary.
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
                return None
            self.stdout_buffer.extend(data)
        try:
            item = json.loads(line.decode("utf-8"))
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
        if item.get("method") == "item/completed":
            self._record_completed_agent_message(item)
        return item

    def _record_completed_agent_message(self, item: Mapping[str, Any]) -> None:
        """Capture a final agent message when the server omits text deltas.

        Some real Provider/app-server combinations complete an agentMessage
        item without emitting item/agentMessage/delta notifications.  The
        completed item is the authoritative final text and must not be lost.
        """

        params = item.get("params") or {}
        message = params.get("item") or {}
        if not isinstance(message, Mapping) or message.get("type") != "agentMessage":
            return
        turn_id = params.get("turnId")
        if not isinstance(turn_id, str) or not turn_id:
            return
        text = message.get("text")
        if not isinstance(text, str):
            content = message.get("content")
            if isinstance(content, list):
                text = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, Mapping) and isinstance(part.get("text"), str)
                )
        if isinstance(text, str) and text:
            self._agent_text[turn_id] = text

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
        self.process.stdin.write((json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
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
        run_claim: str = "create",
    ) -> CodexExecution:
        """Run one Codex turn and persist its identity in the owner.

        ``run_claim`` controls who owns the run's create + start lifecycle:

        * ``"create"`` (default): this adapter is the sole creator of the run
          identity. Used by the one-shot ``run`` command, which hands the
          orchestrator a run_id that does not yet exist in the owner.
        * ``"assume"``: the run identity was created + started by an external
          facade (e.g. the dogfood UI ``CommandFacade``) before execution. The
          adapter must NOT re-create the run -- ``create_run`` raises on a
          duplicate run_id -- so it skips straight to the live Codex turn. The
          run is expected to already be in the ``running`` state.
        """

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
        if run_claim == "create":
            self.owner.create_run(
                run_id,
                task_type,
                input_value if input_value is not None else {"prompt": prompt},
                run_metadata,
            )
            self.owner.start_run(run_id)
        elif run_claim == "assume":
            # The run identity already exists (created + started by the caller's
            # facade). Re-creating it would raise CompositionError on the
            # duplicate run_id, so skip create/start and run the live turn.
            pass
        else:
            raise ValueError("run_claim must be 'create' or 'assume', got {0!r}".format(run_claim))
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
            # Symmetric Provider-side ledger: recorded at the same terminal
            # boundary as the local result above, exactly once per run.
            try:
                self.owner.record_provider_exit_ledger_once(run_id, dict(self.provider_identity))
            except Exception:
                # Local result + terminal status are authoritative; a
                # Provider-ledger write failure must never mask them.
                pass
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
            self._handle_owner_failure(run_id, exc)
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

    def _handle_owner_failure(self, run_id: str, error: Exception) -> None:
        """Classify a provider/transport failure, record it, and fail-closed.

        In S1 (single Provider, no failover) a network / rate-limit / unknown
        failure is terminal: the run is safe-stopped with a
        ``provider_failure:<category>`` reason and the classification is recorded
        as a durable ``failure_classification`` result (category + raw
        ``exc_type`` + message) so the failure is observable and a future S2
        failover can route on it.  Anything outside the three buckets falls back
        to the historical ``fail_run`` (recorded error, ``failed`` status).

        The original exception is re-raised by the caller so the CLI/UI still
        observe the error; recording here must never mask it.
        """

        category = classify_provider_failure(error)
        try:
            self.owner.record_provider_exit_ledger_once(run_id, dict(self.provider_identity))
        except Exception:
            # Provider-ledger write must never mask the original provider failure.
            pass
        try:
            self.owner.record_result(
                run_id,
                "failure_classification",
                {
                    "category": category,
                    "exc_type": type(error).__name__,
                    "message": str(error),
                    "provider_identity": dict(self.provider_identity),
                    "safe_stopped": category in SAFE_STOP_CATEGORIES,
                },
                f"{run_id}:failure_classification",
                evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED,
            )
        except Exception:
            # Recording must never mask the original provider failure.
            return
        try:
            run = self.owner.get_run(run_id)
        except Exception:
            return
        if run["status"] not in {"created", "running", "waiting_approval", "recovering"}:
            # Already terminal (e.g. safe-stopped by an effect rule); do not override.
            return
        try:
            if category in SAFE_STOP_CATEGORIES:
                self.owner.safe_stop_run(run_id, f"provider_failure:{category}")
            else:
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
            self.owner.record_result(
                self.active_run_id, kind, dict(value), source_id, evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED
            )

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

        # Release the resident-service slot claimed in start(). Idempotent: a
        # close before any successful start (or a no-op start) is harmless.
        self.owner.resident_registry.release(f"codex-app-server:{self.code_home}")
        process = self.process
        if process is None:
            return
        stderr = ""
        try:
            if process.poll() is None:
                terminate_process(process, term_timeout=6.0, kill_timeout=6.0)
            stderr_bytes = process.stderr.read() if process.stderr else b""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if isinstance(stderr_bytes, bytes) else stderr_bytes
            stderr_path = self.event_log.with_name("codex-stderr.log")
            stderr_path.write_text(stderr, encoding="utf-8")
        finally:
            if process.stdout is not None:
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
