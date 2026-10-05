from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import tempfile
import textwrap
import unittest

from zworkbench.codex_adapter import (
    CodexAppServerAdapter,
    CodexAdapterError,
    CodexProtocolError,
    FAILURE_NETWORK,
    FAILURE_RATE_LIMIT,
    FAILURE_UNKNOWN,
    SAFE_STOP_CATEGORIES,
    classify_provider_failure,
)
from zworkbench.composition import CompositionOwner


class CodexAdapterShapeTests(unittest.TestCase):
    def test_command_and_environment_are_explicit_and_shell_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    root / "workspace",
                    provider_identity={"provider": "fake-loopback", "model": "fake-model", "endpoint": "http://127.0.0.1:11434", "transport": "loopback-only"},
                    event_log=root / "events.jsonl",
                )
                self.assertEqual(adapter.command()[:4], [str(executable.resolve()), "app-server", "--listen", "stdio://"])
                self.assertIn("--disable", adapter.command())
                environment = adapter._build_environment()
                self.assertEqual(environment["CODEX_HOME"], str((root / "codex-home").resolve()))
                self.assertEqual(environment["CODEX_CI"], "1")
                self.assertNotIn("OPENAI_API_KEY", environment)

    def test_owner_metadata_is_not_written_until_an_owner_backed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(owner, executable, root / "codex-home", root / "workspace")
                self.assertEqual(owner.snapshot()["runs"], [])
                self.assertTrue(adapter.environment_digest())

    def test_binary_jsonl_transport_consumes_completion_buffered_with_turn_response(self) -> None:
        fake_codex = """
        import json
        import sys

        THREAD_ID = "adapter-buffered-thread"
        TURN_ID = "adapter-buffered-turn"

        def send(message):
            sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
            sys.stdout.flush()

        for line in sys.stdin:
            message = json.loads(line)
            if "id" not in message:
                continue
            request_id = message["id"]
            method = message.get("method")
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "thread/start":
                send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
            elif method == "turn/start":
                # Force notifications and the matching RPC response into the
                # same pipe batch, with completion arriving first.
                send({"jsonrpc": "2.0", "method": "item/completed", "params": {"threadId": THREAD_ID, "turnId": TURN_ID, "item": {"type": "agentMessage", "text": "fixture-ok"}}})
                send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
                send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake-codex"
            executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(fake_codex)), encoding="utf-8")
            executable.chmod(0o755)
            workspace = root / "workspace"
            workspace.mkdir()
            with CompositionOwner(root / "owner.sqlite3") as owner:
                with CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    workspace,
                    provider_identity={"provider": "fake-loopback", "model": "fake-model", "endpoint": "http://127.0.0.1:11434", "transport": "loopback-only"},
                    event_log=root / "events.jsonl",
                ) as adapter:
                    execution = adapter.execute("run-buffered", "return fixture-ok", timeout=2.0)
                self.assertEqual(execution.status, "completed")
                self.assertEqual(execution.text, "fixture-ok")
                self.assertEqual(owner.get_run("run-buffered")["status"], "completed")


class CodexIdentityTransportBindingTests(unittest.TestCase):
    """issue #39 (S1 step-0 gate): identity↔transport single-source binding.

    These are fail-closed assertions: an incomplete or ambiguous identity must
    raise rather than be silently back-filled, and the recorded provider_identity
    must never be mutated by the transport-facing constructor arguments.
    """

    def _new_adapter(self, *, provider_identity=None, model="fake-model", model_provider="ollama"):
        temporary = tempfile.mkdtemp()
        root = Path(temporary)
        executable = root / "codex"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        owner = CompositionOwner(root / "owner.sqlite3")
        adapter = CodexAppServerAdapter(
            owner,
            executable,
            root / "codex-home",
            root / "workspace",
            model=model,
            model_provider=model_provider,
            provider_identity=provider_identity,
            event_log=root / "events.jsonl",
        )
        return adapter

    def test_missing_endpoint_fails_closed(self) -> None:
        # Binding completeness: endpoint is required for the identity↔transport
        # record and must not be silently defaulted.
        with self.assertRaises(CodexAdapterError):
            self._new_adapter(
                provider_identity={"provider": "p", "model": "m", "transport": "loopback-only"}
            )

    def test_missing_model_fails_closed(self) -> None:
        # Binding completeness: model is transport-critical; absence fails closed.
        with self.assertRaises(CodexAdapterError):
            self._new_adapter(
                provider_identity={"provider": "p", "endpoint": "http://127.0.0.1:11434", "transport": "loopback-only"}
            )

    def test_missing_provider_fails_closed(self) -> None:
        # Binding completeness: provider is the transport source; absence fails closed.
        with self.assertRaises(CodexAdapterError):
            self._new_adapter(
                provider_identity={"model": "m", "endpoint": "http://127.0.0.1:11434", "transport": "loopback-only"}
            )

    def test_model_provider_sourced_from_ctor_arg_not_silently_from_provider_name(self) -> None:
        # #39 single-source binding: model_provider is taken from the explicit
        # constructor argument when provider_identity carries none, and is NEVER
        # silently derived from provider_identity["provider"] (the profile NAME).
        # Doing so would conflate name with the model-provider CATEGORY. The ctor
        # arg is never injected into the recorded identity.
        adapter = self._new_adapter(
            model="injected-model",
            model_provider="injected-provider",
            provider_identity={
                "provider": "real-provider",
                "model": "real-model",
                "endpoint": "http://127.0.0.1:11434",
                "transport": "loopback-only",
            },
        )
        self.assertEqual(adapter.provider_identity["provider"], "real-provider")
        self.assertEqual(adapter.provider_identity["model"], "real-model")
        self.assertEqual(adapter.provider_identity["endpoint"], "http://127.0.0.1:11434")
        self.assertNotIn("injected", adapter.provider_identity.get("provider", ""))
        self.assertNotIn("injected", adapter.provider_identity.get("model", ""))
        self.assertEqual(adapter.model, "real-model")
        # identity carries no model_provider, so the explicit ctor arg is the
        # legitimate source -- NOT identity["provider"] ("real-provider").
        self.assertEqual(adapter.model_provider, "injected-provider")

    def test_model_provider_prefers_identity_when_present(self) -> None:
        # When provider_identity carries model_provider, it is the single source
        # and overrides the constructor argument.
        adapter = self._new_adapter(
            model_provider="ctor-ignored",
            provider_identity={
                "provider": "real-provider",
                "model": "real-model",
                "model_provider": "identity-provider",
                "endpoint": "http://127.0.0.1:11434",
                "transport": "loopback-only",
            },
        )
        self.assertEqual(adapter.model_provider, "identity-provider")


class CodexFailureClassificationTests(unittest.TestCase):
    """node 1-6-4: owner records a failure classification and safe-stops on
    network / rate-limit / unknown provider failures (S1, no failover).
    """

    PROVIDER_IDENTITY = {
        "provider": "fake-loopback",
        "model": "fake-model",
        "endpoint": "http://127.0.0.1:11434",
        "transport": "loopback-only",
    }

    # -- classifier unit tests --------------------------------------------

    def test_timeout_is_network(self) -> None:
        self.assertEqual(classify_provider_failure(TimeoutError("request timed out")), FAILURE_NETWORK)

    def test_connection_reset_is_network(self) -> None:
        self.assertEqual(classify_provider_failure(ConnectionResetError("reset")), FAILURE_NETWORK)

    def test_broken_pipe_is_network(self) -> None:
        self.assertEqual(classify_provider_failure(BrokenPipeError("pipe")), FAILURE_NETWORK)

    def test_oserror_with_network_errno_is_network(self) -> None:
        import errno

        exc = OSError(errno.ECONNREFUSED, "connection refused")
        self.assertEqual(classify_provider_failure(exc), FAILURE_NETWORK)

    def test_dns_resolution_is_network(self) -> None:
        import socket

        self.assertEqual(classify_provider_failure(socket.gaierror("name resolution failed")), FAILURE_NETWORK)

    def test_rate_limit_message_is_rate_limit(self) -> None:
        exc = CodexProtocolError("turn/start failed: {'error': {'message': 'Rate limit exceeded, throttle back'}}")
        self.assertEqual(classify_provider_failure(exc), FAILURE_RATE_LIMIT)

    def test_http_429_phrase_is_rate_limit(self) -> None:
        self.assertEqual(classify_provider_failure(CodexProtocolError("429 Too Many Requests")), FAILURE_RATE_LIMIT)

    def test_protocol_error_without_rate_phrase_is_unknown(self) -> None:
        # A provider-returned protocol error that is not throttling is unknown:
        # unclassified == not safely retryable in S1.
        exc = CodexProtocolError("turn did not complete: cancelled")
        self.assertEqual(classify_provider_failure(exc), FAILURE_UNKNOWN)

    def test_generic_exception_is_unknown(self) -> None:
        self.assertEqual(classify_provider_failure(RuntimeError("boom")), FAILURE_UNKNOWN)

    def test_safe_stop_categories_are_the_three_named_buckets(self) -> None:
        self.assertEqual(SAFE_STOP_CATEGORIES, {FAILURE_NETWORK, FAILURE_RATE_LIMIT, FAILURE_UNKNOWN})

    # -- integration: classification is recorded and the run safe-stops -----

    def _spawn_fake_codex(self, root: Path, source: str) -> Path:
        executable = root / "fake-codex"
        executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(source)), encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def _build_adapter(self, owner: CompositionOwner, root: Path, executable: Path) -> CodexAppServerAdapter:
        workspace = root / "workspace"
        # Brokered sandbox returns EEXIST as PermissionError; see _base_adapter.
        try:
            workspace.mkdir(exist_ok=True)
        except PermissionError as exc:
            if "EEXIST" not in str(exc):
                raise
        return CodexAppServerAdapter(
            owner,
            executable,
            root / "codex-home",
            workspace,
            provider_identity=dict(self.PROVIDER_IDENTITY),
            event_log=root / "events.jsonl",
        )

    def _assert_classification(self, owner: CompositionOwner, run_id: str, expected_category: str) -> None:
        run = owner.get_run(run_id)
        self.assertEqual(run["status"], "safe_stopped")
        classifications = [r for r in run["results"] if r["kind"] == "failure_classification"]
        self.assertEqual(len(classifications), 1)
        classification = classifications[0]["value"]
        self.assertEqual(classification["category"], expected_category)
        self.assertIs(classification["safe_stopped"], True)
        self.assertEqual(classification["provider_identity"], self.PROVIDER_IDENTITY)
        safe_stop_events = [
            e for e in owner.events(run_id) if e["type"] == "run.safe_stopped"
        ]
        self.assertTrue(safe_stop_events, "expected a run.safe_stopped event")
        self.assertEqual(safe_stop_events[-1]["payload"]["reason"], f"provider_failure:{expected_category}")

    def test_network_failure_is_classified_and_safe_stopped(self) -> None:
        # A simulated transport timeout reaches _handle_owner_failure through the
        # real execute() except path without a 20s hang.
        def _boom(method, params, timeout=20.0):
            raise TimeoutError("simulated network timeout")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._spawn_fake_codex(root, "import sys\nsys.stdin.read()\n")
            owner = CompositionOwner(root / "owner.sqlite3")
            adapter = self._build_adapter(owner, root, executable)
            adapter.request = _boom  # type: ignore[method-assign]
            with adapter:
                with self.assertRaises(TimeoutError):
                    adapter.execute("run-net", "prompt", timeout=2.0)
            self._assert_classification(owner, "run-net", FAILURE_NETWORK)

    def test_rate_limit_failure_is_classified_and_safe_stopped(self) -> None:
        fake_codex = """
        import json
        import sys

        def send(message):
            sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
            sys.stdout.flush()

        for line in sys.stdin:
            message = json.loads(line)
            if "id" not in message:
                continue
            request_id = message["id"]
            method = message.get("method")
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "thread/start":
                send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": "t1"}}})
            elif method == "turn/start":
                send({"jsonrpc": "2.0", "id": request_id,
                      "error": {"code": 429, "message": "Rate limit exceeded, throttle back"}})
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._spawn_fake_codex(root, fake_codex)
            owner = CompositionOwner(root / "owner.sqlite3")
            adapter = self._build_adapter(owner, root, executable)
            with adapter:
                with self.assertRaises(CodexProtocolError):
                    adapter.execute("run-rl", "prompt", timeout=2.0)
            self._assert_classification(owner, "run-rl", FAILURE_RATE_LIMIT)

    def test_unknown_protocol_failure_is_classified_and_safe_stopped(self) -> None:
        # The fake app-server emits a non-JSON line so the adapter raises a
        # protocol error (unknown bucket) without waiting on a timeout.
        fake_codex = """
        import sys

        sys.stdout.write("not-json\\n")
        sys.stdout.flush()
        for _ in sys.stdin:
            pass
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._spawn_fake_codex(root, fake_codex)
            owner = CompositionOwner(root / "owner.sqlite3")
            adapter = self._build_adapter(owner, root, executable)
            with adapter:
                with self.assertRaises(CodexProtocolError):
                    adapter.execute("run-unk", "prompt", timeout=2.0)
            self._assert_classification(owner, "run-unk", FAILURE_UNKNOWN)


class CodexProviderConfigPassthroughTests(unittest.TestCase):
    """roadmap 1-9-1: a real Provider profile must reach Codex via --config.

    The historical bug: command() never passed --config and CODEX_HOME was a
    case-local empty dir, so Codex never discovered [model_providers.<name>];
    model_provider="custom" was unknown and the turn failed closed
    (CodexProtocolError -> safe_stopped). These tests prove the adapter now
    advertises --config and a spawned app-server actually receives it, and the
    turn completes without safe_stopped.
    """

    def _fake_codex(self, root: Path, marker: Path) -> Path:
        # The fake app-server records the argv it was launched with (so we can
        # assert --config reached the real spawn path) and completes a turn.
        source = textwrap.dedent(
            '''
            import json
            import sys
            from pathlib import Path

            Path({marker!r}).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")

            THREAD_ID = "cfg-thread"
            TURN_ID = "cfg-turn"

            def send(message):
                sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
                sys.stdout.flush()

            for line in sys.stdin:
                message = json.loads(line)
                if "id" not in message:
                    continue
                request_id = message["id"]
                method = message.get("method")
                if method == "initialize":
                    send({{"jsonrpc": "2.0", "id": request_id, "result": {{}}}})
                elif method == "thread/start":
                    send({{"jsonrpc": "2.0", "id": request_id, "result": {{"thread": {{"id": THREAD_ID}}}}}})
                elif method == "turn/start":
                    send({{"jsonrpc": "2.0", "id": request_id, "result": {{"turn": {{"id": TURN_ID}}}}}})
                    send({{"jsonrpc": "2.0", "method": "turn/completed",
                          "params": {{"threadId": THREAD_ID, "turn": {{"id": TURN_ID, "status": "completed"}}}}}})
            '''
        ).format(marker=str(marker))
        executable = root / "fake-codex"
        executable.write_text("#!{0}\n{1}".format(sys.executable, source), encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def test_command_omits_config_flag_without_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    root / "workspace",
                    provider_identity={
                        "provider": "fake-loopback",
                        "model": "fake-model",
                        "endpoint": "http://127.0.0.1:11434",
                        "transport": "loopback-only",
                    },
                    event_log=root / "events.jsonl",
                )
                self.assertNotIn("--config", adapter.command())

    def test_provider_config_staged_into_codex_home_and_turn_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "provider-config.toml"
            config_path.write_text('model = "ark-code-latest"\n', encoding="utf-8")
            marker = root / "received_argv.txt"
            executable = self._fake_codex(root, marker)
            workspace = root / "workspace"
            workspace.mkdir()
            with CompositionOwner(root / "owner.sqlite3") as owner:
                adapter = CodexAppServerAdapter(
                    owner,
                    executable,
                    root / "codex-home",
                    workspace,
                    provider_identity={
                        "provider": "custom",
                        "model": "ark-code-latest",
                        "endpoint": "https://ark.example.com/v1",
                        "transport": "remote",
                    },
                    provider_config_path=config_path,
                    event_log=root / "events.jsonl",
                )
                # Codex has no --config <file> flag, so command() must NOT emit it.
                self.assertNotIn("--config", adapter.command())
                with adapter:
                    execution = adapter.execute("run-cfg", "return fixture-ok", timeout=2.0)
                self.assertEqual(execution.status, "completed")
                self.assertEqual(owner.get_run("run-cfg")["status"], "completed")
                # The provider config was staged into CODEX_HOME so Codex would
                # discover [model_providers.<name>] (roadmap 1-9-1).
                staged = root / "codex-home" / "config.toml"
                self.assertTrue(staged.is_file())
                self.assertEqual(
                    staged.read_text(encoding="utf-8"),
                    config_path.read_text(encoding="utf-8"),
                )


class CodexHostEnforcementTests(unittest.TestCase):
    """roadmap 1-9-2: ZWorkbench becomes the single sandbox authority.

    ``host_enforcement`` disables Codex's internal nested sandbox (bypass flag)
    and wraps Codex in a macOS seatbelt when the OS enforcer can apply. The
    enforcer binary is overridable via ``ZWB_ENFORCER_BIN`` so the wrap/apply
    path is testable without OS seatbelt access (mirrors host_enforcer).
    """

    def _write_fake_enforcer(self, root: Path, *, applies: bool) -> Path:
        path = root / "fake-sandbox-exec"
        if applies:
            # Drop the "-p <profile>" prefix and exec the child: simulate a
            # successfully applied seatbelt under which the child runs.
            body = "#!/bin/sh\nshift 2\nexec \"$@\"\n"
        else:
            body = (
                "#!/bin/sh\n"
                'echo "sandbox-exec: sandbox_apply: Operation not permitted" >&2\n'
                "exit 1\n"
            )
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def _base_adapter(self, root: Path, *, host_enforcement: bool = False, **kw):
        workspace = root / "workspace"
        # The WorkBuddy brokered sandbox returns "EEXIST: file already exists"
        # as a ``PermissionError`` instead of the standard ``FileExistsError``
        # that ``mkdir(exist_ok=True)`` swallows. Treat the broker's EEXIST the
        # same as "already exists" so helper callers that reuse a temp dir do
        # not fail on the second call. Genuine broker denials (no EEXIST) still
        # propagate.
        try:
            workspace.mkdir(exist_ok=True)
        except PermissionError as exc:
            if "EEXIST" not in str(exc):
                raise
        owner = CompositionOwner(root / "owner.sqlite3")
        identity = kw.pop(
            "provider_identity",
            {
                "provider": "custom",
                "model": "ark-code-latest",
                "endpoint": "https://ark.example.com/v1",
                "transport": "remote",
            },
        )
        return CodexAppServerAdapter(
            owner,
            root / "codex",
            root / "codex-home",
            workspace,
            provider_identity=identity,
            event_log=root / "events.jsonl",
            host_enforcement=host_enforcement,
            **kw,
        )

    def test_command_includes_bypass_flag_only_when_host_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "codex").chmod(0o755)
            self.assertNotIn(
                "--dangerously-bypass-approvals-and-sandbox",
                self._base_adapter(root, host_enforcement=False).command(),
            )
            argv = self._base_adapter(root, host_enforcement=True).command()
            # Global flag must precede the subcommand.
            self.assertEqual(argv[0], str((root / "codex").resolve()))
            self.assertEqual(argv[1], "--dangerously-bypass-approvals-and-sandbox")
            self.assertEqual(argv[2], "app-server")
            # The global --dangerously-bypass-approvals-and-sandbox flag is the
            # "externally sandboxed" signal that tells Codex to stop re-seatbelting
            # its shell children (roadmap 1-9-2). Codex has no sandbox_mode value
            # that disables sandboxing, so this flag is the disable lever.
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_build_spawn_argv_skips_seatbelt_when_host_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "codex").chmod(0o755)
            enforcer = self._write_fake_enforcer(root, applies=True)
            old = os.environ.get("ZWB_ENFORCER_BIN")
            os.environ["ZWB_ENFORCER_BIN"] = str(enforcer)
            try:
                argv = self._base_adapter(root, host_enforcement=True)._build_spawn_argv()
            finally:
                if old is None:
                    os.environ.pop("ZWB_ENFORCER_BIN", None)
                else:
                    os.environ["ZWB_ENFORCER_BIN"] = old
            # Roadmap 1-9-3 (direction b): ZWorkbench must NOT wrap Codex in a
            # macOS seatbelt (nested sandbox_apply EPERM would block reads). Codex
            # applies its own sandbox; the enforcer must NOT prefix the command.
            self.assertNotEqual(argv[0], str(enforcer))
            self.assertEqual(argv[0], str((root / "codex").resolve()))
            self.assertEqual(argv[1], "--dangerously-bypass-approvals-and-sandbox")
            self.assertEqual(argv[2], "app-server")

    def test_build_spawn_argv_never_wraps_regardless_of_enforcer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "codex").chmod(0o755)
            enforcer = self._write_fake_enforcer(root, applies=False)
            old = os.environ.get("ZWB_ENFORCER_BIN")
            os.environ["ZWB_ENFORCER_BIN"] = str(enforcer)
            try:
                argv = self._base_adapter(root, host_enforcement=True)._build_spawn_argv()
            finally:
                if old is None:
                    os.environ.pop("ZWB_ENFORCER_BIN", None)
                else:
                    os.environ["ZWB_ENFORCER_BIN"] = old
            # Roadmap 1-9-3 (direction b): Codex is never wrapped, so the enforcer
            # (available or not) never prefixes the command. Codex 自带 sandbox 作边界.
            self.assertNotEqual(argv[0], str(enforcer))
            self.assertEqual(argv[0], str((root / "codex").resolve()))
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_host_enforcement_turn_completes_with_bypass_flag(self) -> None:
        # End-to-end: with host_enforcement, Codex launches with the bypass flag
        # and applies its own sandbox (no ZWorkbench seatbelt wrap); the turn
        # completes and the Codex child received the bypass flag.
        helper = CodexProviderConfigPassthroughTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            enforcer = self._write_fake_enforcer(root, applies=True)
            marker = root / "received_argv.txt"
            executable = helper._fake_codex(root, marker)
            old = os.environ.get("ZWB_ENFORCER_BIN")
            os.environ["ZWB_ENFORCER_BIN"] = str(enforcer)
            try:
                with CompositionOwner(root / "owner.sqlite3") as owner:
                    with CodexAppServerAdapter(
                        owner,
                        executable,
                        root / "codex-home",
                        root / "workspace",
                        provider_identity={
                            "provider": "custom",
                            "model": "ark-code-latest",
                            "endpoint": "https://ark.example.com/v1",
                            "transport": "remote",
                        },
                        event_log=root / "events.jsonl",
                        host_enforcement=True,
                    ) as adapter:
                        execution = adapter.execute("run-he", "return fixture-ok", timeout=2.0)
                self.assertEqual(execution.status, "completed")
                launched = json.loads(marker.read_text(encoding="utf-8"))
                self.assertIn("--dangerously-bypass-approvals-and-sandbox", launched)
                # The bypass flag is global and precedes the subcommand, so
                # app-server is now argv[1] of the Codex child.
                self.assertEqual(launched[0], "--dangerously-bypass-approvals-and-sandbox")
                self.assertEqual(launched[1], "app-server")
            finally:
                if old is None:
                    os.environ.pop("ZWB_ENFORCER_BIN", None)
                else:
                    os.environ["ZWB_ENFORCER_BIN"] = old


if __name__ == "__main__":
    unittest.main()
