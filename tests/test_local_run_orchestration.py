from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from zworkbench import (
    CodexExecution,
    CompositionOwner,
    LocalReadOnlyRunConfig,
    LocalReadOnlyRunOrchestrator,
    ProviderProfile,
)
from zworkbench.composition import EVIDENCE_SOURCE_OUTER_COMPOSED


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
        self.owner.record_result(run_id, "adapter.fake", {"thread_id": "thread-1"}, "thread-1", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
        self.owner.record_result(run_id, "adapter.fake", {"turn_id": "turn-1"}, "turn-1", evidence_source=EVIDENCE_SOURCE_OUTER_COMPOSED)
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


class NonClosingAdapter:
    """Like RecordingAdapter but deliberately omits the terminal ``complete_run``.

    Exercises the 1-4-3 local_run finally anchor: when an adapter returns a
    successful execution without closing the run, local_run must close it.
    """

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
        self.owner.record_replay_metadata(
            run_id,
            f"{run_id}:recorded-view",
            "recorded_view",
            "event-digest",
            "environment-digest",
            provider_identity,
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

    def test_adapter_failure_closes_run_as_failed_via_finally_anchor(self) -> None:
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
                # 1-4-3 统一 run 闭合锚点: adapter 异常未闭合时，local_run
                # finally 兜底 fail_run，run 不再悬在 running。
                self.assertEqual(owner.get_run("run-failed")["status"], "failed")

    def test_default_path_records_unknown_delegated_exit_ledger_on_success(self) -> None:
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

            LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                "run-1",
                "inspect the local project and return fixture-ok",
            )

            with CompositionOwner(config.database) as owner:
                ledger = owner.provider_exit_ledger_for_run("run-1")
                self.assertEqual(len(ledger), 1)
                entry = ledger[0]
                self.assertEqual(entry["provider"], "fake-loopback")
                self.assertEqual(entry["endpoint"], "http://127.0.0.1:11434")
                self.assertEqual(entry["provider_remote_zero_residue"], "unknown/delegated")
                self.assertEqual(entry["exit_status"], "unknown/safe-stop")
                self.assertEqual(entry["exit_mode"], "inventory-only")

    def test_default_path_records_unknown_delegated_exit_ledger_on_failure(self) -> None:
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

            self.assertTrue(adapters[0].closed)
            with CompositionOwner(config.database) as owner:
                ledger = owner.provider_exit_ledger_for_run("run-failed")
                self.assertEqual(len(ledger), 1)
                self.assertEqual(ledger[0]["provider_remote_zero_residue"], "unknown/delegated")


    def test_run_closes_run_in_finally_when_adapter_leaves_it_running(self) -> None:
        # 1-4-3: a successful adapter that does NOT close the run must be closed
        # by the local_run finally anchor (defense-in-depth), not left running.
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
                adapter = NonClosingAdapter(owner, factory_config)
                adapters.append(adapter)
                return adapter

            result = LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                "run-nonclosing",
                "adapter returns without complete_run",
            )

            self.assertEqual(result.status, "completed")
            self.assertTrue(adapters[0].closed)
            with CompositionOwner(config.database) as owner:
                self.assertEqual(owner.get_run("run-nonclosing")["status"], "completed")

    def test_run_idempotent_closure_when_adapter_already_completed(self) -> None:
        # 1-4-3: when the adapter already closed the run, the finally anchor must
        # skip (idempotent) instead of raising InvalidTransition on re-close.
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
                "run-idempotent",
                "adapter already completed the run",
            )

            self.assertEqual(result.status, "completed")
            self.assertTrue(adapters[0].closed)
            with CompositionOwner(config.database) as owner:
                self.assertEqual(owner.get_run("run-idempotent")["status"], "completed")


class ProviderAccessGateTests(unittest.TestCase):
    """Node 1-1-4: the controlled gate between baseline and a real Provider.

    The loopback / fake baseline must never silently reach a real Provider: a
    real profile without the gate is denied at preflight, and every admitted run
    records its classification (real vs baseline) to the owner for audit.
    """

    def _fixture(self, root: Path) -> Path:
        workspace = root / "workspace"
        workspace.mkdir()
        executable = root / "codex"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def test_real_profile_without_gate_is_denied_before_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._fixture(root)
            profile = ProviderProfile(
                name="custom",
                model_provider="custom",
                model="ark-code-latest",
                base_url="https://ark.example.com/v1",
            )
            config = LocalReadOnlyRunConfig(
                case_root=root,
                workspace=root / "workspace",
                database=root / "state" / "composition.sqlite3",
                code_home=root / "codex-home",
                codex_executable=executable,
                provider_identity={
                    "provider": "fake-loopback",
                    "model": "fake-model",
                    "endpoint": "http://127.0.0.1:11434",
                },
                provider_profile=profile,
                provider_config_path=root / "provider-config.toml",
                real_provider_gate=False,  # gate explicitly off
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
            self.assertIn(
                "real_provider_gate_disabled",
                {violation.code for violation in result.preflight.violations},
            )
            self.assertEqual(factory_calls, [])
            self.assertFalse(config.database.exists())

    def test_baseline_run_records_baseline_gate_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._fixture(root)
            config = LocalReadOnlyRunConfig(
                case_root=root,
                workspace=root / "workspace",
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

            LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                "run-baseline",
                "inspect the local project and return fixture-ok",
            )
            self.assertEqual(len(adapters), 1)
            with CompositionOwner(config.database) as owner:
                ledger = owner.provider_access_gate_ledger_for_run("run-baseline")
                self.assertEqual(len(ledger), 1)
                self.assertEqual(ledger[0]["classification"], "baseline")
                self.assertFalse(ledger[0]["gate_enabled"])

    def test_real_profile_with_gate_records_real_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = self._fixture(root)
            profile = ProviderProfile(
                name="custom",
                model_provider="custom",
                model="ark-code-latest",
                base_url="https://ark.example.com/v1",
            )
            config = LocalReadOnlyRunConfig(
                case_root=root,
                workspace=root / "workspace",
                database=root / "state" / "composition.sqlite3",
                code_home=root / "codex-home",
                codex_executable=executable,
                provider_identity={
                    "provider": "fake-loopback",
                    "model": "fake-model",
                    "endpoint": "http://127.0.0.1:11434",
                },
                provider_profile=profile,
                provider_config_path=root / "provider-config.toml",
                real_provider_gate=True,
            )
            adapters = []

            def factory(owner, factory_config):
                adapter = RecordingAdapter(owner, factory_config)
                adapters.append(adapter)
                return adapter

            result = LocalReadOnlyRunOrchestrator(config, adapter_factory=factory).run(
                "run-real",
                "inspect the local project and return fixture-ok",
            )
            self.assertEqual(result.status, "completed")
            self.assertEqual(len(adapters), 1)
            with CompositionOwner(config.database) as owner:
                ledger = owner.provider_access_gate_ledger_for_run("run-real")
                self.assertEqual(len(ledger), 1)
                self.assertEqual(ledger[0]["classification"], "real")
                self.assertTrue(ledger[0]["gate_enabled"])
                self.assertEqual(ledger[0]["profile_name"], "custom")


if __name__ == "__main__":
    unittest.main()
