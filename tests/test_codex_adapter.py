from __future__ import annotations

from pathlib import Path
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
        workspace.mkdir(exist_ok=True)
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


if __name__ == "__main__":
    unittest.main()
