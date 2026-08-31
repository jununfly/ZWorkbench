from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from zworkbench import (
    CodexExecution,
    CompositionOwner,
    LocalReadOnlyRunConfig,
    LocalReadOnlyRunOrchestrator,
)


class RecordingAdapter:
    def __init__(self, owner: CompositionOwner, config: LocalReadOnlyRunConfig) -> None:
        self.owner = owner
        self.config = config
        self.closed = False
        self.calls = []

    def execute(self, run_id: str, prompt: str, **kwargs):
        self.calls.append((run_id, prompt, kwargs))
        metadata = kwargs["metadata"]
        provider_identity = dict(self.config.provider_identity)
        self.owner.create_run(run_id, kwargs["task_type"], {"prompt": prompt}, metadata)
        self.owner.start_run(run_id)
        self.owner.record_result(run_id, "adapter.fake", {"thread_id": "thread-1"}, "thread-1")
        self.owner.record_result(run_id, "adapter.fake", {"turn_id": "turn-1"}, "turn-1")
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


class RaisingAdapter:
    def __init__(self, owner: CompositionOwner, config: LocalReadOnlyRunConfig) -> None:
        self.owner = owner
        self.closed = False

    def execute(self, run_id: str, prompt: str, **kwargs):
        self.owner.create_run(run_id, kwargs["task_type"], {"prompt": prompt}, kwargs["metadata"])
        self.owner.start_run(run_id)
        raise RuntimeError("controlled adapter failure")

    def close(self) -> None:
        self.closed = True


class LocalReadOnlyRunOrchestrationTests(unittest.TestCase):
    def test_passed_preflight_runs_one_owner_backed_adapter_and_returns_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                },
            )
            adapters = []

            def factory(owner, factory_config):
                adapter = RecordingAdapter(owner, factory_config)
                adapters.append(adapter)
                return adapter

            result = LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                "run-1",
                "inspect the local project and return fixture-ok",
            )

            self.assertEqual(result.status, "completed")
            self.assertTrue(result.preflight.allowed)
            self.assertIsNotNone(result.execution)
            self.assertEqual(result.execution.text, "fixture-ok")
            self.assertIsNotNone(result.state_digest)
            self.assertEqual(len(adapters), 1)
            self.assertTrue(adapters[0].closed)
            self.assertEqual(adapters[0].calls[0][2]["metadata"]["preflight"]["status"], "pass")
            with CompositionOwner(config.database) as owner:
                run = owner.get_run("run-1")
                self.assertEqual(run["status"], "completed")
                self.assertEqual(run["metadata"]["preflight"]["config_digest"], result.preflight.config_digest)

    def test_denied_preflight_short_circuits_before_owner_or_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    "provider": "remote-provider",
                    "model": "remote-model",
                    "endpoint": "https://api.example.invalid/v1",
                },
            )
            factory_calls = []

            def forbidden_factory(owner, factory_config):
                factory_calls.append((owner, factory_config))
                raise AssertionError("adapter factory must not run after denied preflight")

            result = LocalReadOnlyRunOrchestrator(config, adapter_factory=forbidden_factory).run(
                "run-denied",
                "must not execute",
            )

            self.assertEqual(result.status, "denied")
            self.assertFalse(result.preflight.allowed)
            self.assertIsNone(result.execution)
            self.assertEqual(factory_calls, [])
            self.assertFalse(config.database.exists())

    def test_adapter_failure_closes_adapter_and_preserves_owner_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                },
            )
            adapters = []

            def factory(owner, factory_config):
                adapter = RaisingAdapter(owner, factory_config)
                adapters.append(adapter)
                return adapter

            with self.assertRaisesRegex(RuntimeError, "controlled adapter failure"):
                LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                    "run-failed",
                    "controlled failure",
                )

            self.assertEqual(len(adapters), 1)
            self.assertTrue(adapters[0].closed)
            with CompositionOwner(config.database) as owner:
                self.assertEqual(owner.get_run("run-failed")["status"], "running")


if __name__ == "__main__":
    unittest.main()
