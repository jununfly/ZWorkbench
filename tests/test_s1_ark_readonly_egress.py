"""End-to-end verification for the S1 single-Provider read-only egress path (1-6-3).

1-6-3 verifies that the Ark-style single-Provider read-only egress path already
wired into the default ``zworkbench run`` entry actually works end-to-end, and
that the prompt can be injected over stdin (so it never sits in the process
argument list). These tests exercise the real product wiring through the
default admission + adapter factory, using a fake adapter for the run path and
a stub orchestrator for the stdin path.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from zworkbench import (
    CodexExecution,
    CompositionOwner,
    HostCapabilityFacade,
    LocalReadOnlyRunConfig,
    LocalReadOnlyRunOrchestrator,
    PreflightResult,
    ProviderProfile,
)
from zworkbench import local_run
from zworkbench.cli import main


ARK_PROFILE = ProviderProfile(
    name="ark-test",
    model_provider="custom",
    model="coding-model",
    base_url="https://ark.example.com/api/coding/v3",
    wire_api="openai-compatible",
    requires_openai_auth=True,
    env_ref="ARK_API_KEY",
)


class RecordingAdapter:
    """Reuse the orchestration fake: record the call, drive the owner, return a result."""

    def __init__(self, owner: CompositionOwner, config: LocalReadOnlyRunConfig) -> None:
        self.owner = owner
        self.config = config
        self.closed = False
        self.calls = []

    def execute(self, run_id: str, prompt: str, **kwargs):
        self.calls.append((run_id, prompt, kwargs))
        provider_identity = dict(self.config.provider_identity)
        self.owner.create_run(run_id, kwargs["task_type"], {"prompt": prompt}, kwargs["metadata"])
        self.owner.start_run(run_id)
        self.owner.record_replay_metadata(
            run_id,
            f"{run_id}:recorded-view",
            "recorded_view",
            "event-digest",
            "environment-digest",
            provider_identity,
        )
        self.owner.complete_run(
            run_id,
            {
                "status": "completed",
                "text": "fixture-ok",
                "thread_id": "thread-1",
                "turn_id": "turn-1",
                "provider_identity": provider_identity,
            },
        )
        return CodexExecution(
            run_id,
            "thread-1",
            "turn-1",
            "completed",
            "fixture-ok",
            provider_identity,
            "event-digest",
            "environment-digest",
            2,
        )

    def close(self) -> None:
        self.closed = True


def _base_config(**overrides) -> LocalReadOnlyRunConfig:
    root = Path(tempfile.mkdtemp())
    workspace = root / "workspace"
    workspace.mkdir()
    executable = root / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    config = LocalReadOnlyRunConfig(
        case_root=root,
        workspace=workspace,
        database=root / "state" / "composition.sqlite3",
        code_home=root / "codex-home",
        codex_executable=executable,
        provider_identity={
            "provider": "fake-loopback",
            "model": "fake-model",
            "endpoint": "http://127.0.0.1:11434",
            "model_provider": "fake-loopback",
        },
    )
    for key, value in overrides.items():
        object.__setattr__(config, key, value)
    return config


class S1ArkReadonlyEgressTests(unittest.TestCase):
    def test_facade_wires_ark_profile_for_single_provider(self) -> None:
        # The default entry must wire the selected single Provider (ARK) profile
        # into the adapter: the remote egress endpoint is preserved on the
        # wired adapter. Per the #39 identity<->transport single-source binding,
        # model_provider is the profile's declared model_provider ("custom"), NOT
        # the profile NAME used as the identity provider field ("ark-test"). The
        # adapter must not silently conflate the two.
        config = _base_config(
            provider_identity={
                "provider": "ark-test",
                "model": "coding-model",
                "endpoint": "https://ark.example.com/api/coding/v3",
            },
            authorized_providers=frozenset({"ark-test"}),
            provider_profile=ARK_PROFILE,
        )
        with CompositionOwner(config.database) as owner:
            adapter = HostCapabilityFacade.acquire_provider(owner, config)

        self.assertEqual(adapter.provider_identity["provider"], "ark-test")
        self.assertEqual(
            adapter.provider_identity["endpoint"],
            "https://ark.example.com/api/coding/v3",
        )
        # #39 binding: adapter.model_provider is the profile's declared value,
        # not identity["provider"].
        self.assertEqual(adapter.model_provider, "custom")
        self.assertEqual(config.provider_profile.model_provider, "custom")

    def test_facade_derives_model_provider_from_identity(self) -> None:
        # Without an explicit profile, the loopback fixture's provider_identity is
        # the single source of model_provider (no silent ollama default injected,
        # and no conflation with provider_identity["provider"]).
        config = _base_config()
        with CompositionOwner(config.database) as owner:
            adapter = HostCapabilityFacade.acquire_provider(owner, config)
        self.assertEqual(adapter.model_provider, "fake-loopback")

    def test_run_entry_admits_authorized_remote_provider_end_to_end(self) -> None:
        # A single authorized remote Provider (ARK) must pass preflight through
        # the default entry and complete an owner-backed run.
        config = _base_config(
            provider_identity={
                "provider": "ark-test",
                "model": "coding-model",
                "endpoint": "https://ark.example.com/api/coding/v3",
            },
            authorized_providers=frozenset({"ark-test"}),
            provider_profile=ARK_PROFILE,
        )
        adapters = []

        def factory(owner, factory_config):
            adapter = RecordingAdapter(owner, factory_config)
            adapters.append(adapter)
            return adapter

        result = LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
            "run-ark-1",
            "inspect the local project and return fixture-ok",
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.preflight.allowed)
        self.assertEqual(len(adapters), 1)
        self.assertTrue(adapters[0].closed)
        # The adapter received the ARK profile, not the ollama default.
        self.assertEqual(adapters[0].config.provider_profile.model_provider, "custom")
        with CompositionOwner(config.database) as owner:
            run = owner.get_run("run-ark-1")
            self.assertEqual(run["status"], "completed")

    def test_cli_reads_prompt_from_stdin(self) -> None:
        # `--prompt -` must read the task prompt from stdin and still drive the
        # default entry. We stub the orchestrator so no real Codex process runs.
        root = Path(tempfile.mkdtemp())
        workspace = root / "workspace"
        workspace.mkdir()
        codex = root / "codex"
        codex.write_text("#!/bin/sh\n", encoding="utf-8")
        codex.chmod(0o755)

        captured: dict = {}

        class StubOrchestrator:
            def __init__(self, stub_config, adapter_factory=None):
                captured["config"] = stub_config

            def run(self, run_id, prompt, timeout=45.0):
                captured["prompt"] = prompt
                preflight = PreflightResult("pass", "local_read_only", "digest", {"ok": True}, ())
                return local_run.LocalReadOnlyRunResult("completed", run_id, preflight)

        arguments = [
            "run",
            "--case-root", str(root),
            "--workspace", str(workspace),
            "--codex", str(codex),
            "--prompt", "-",
        ]
        with mock.patch("zworkbench.cli.LocalReadOnlyRunOrchestrator", StubOrchestrator):
            output = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO("prompt-injected-from-stdin\n")):
                with redirect_stdout(output):
                    status = main(arguments)

        self.assertEqual(status, 0)
        self.assertEqual(captured["prompt"], "prompt-injected-from-stdin\n")
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "completed")


if __name__ == "__main__":
    unittest.main()
