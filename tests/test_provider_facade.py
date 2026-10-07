"""Tests for the Host Capability Facade Provider-access seam (roadmap 1-6-5).

These guard the R3 architecture negative constraint: product orchestration code
must reach the Provider through :class:`HostCapabilityFacade` and never import or
construct ``CodexAppServerAdapter`` directly.  The static source assertion is the
durable guard; the behavioral tests confirm the facade produces the right adapter
for both the default loopback path and an explicit real-Provider profile.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import zworkbench.local_run as local_run_module
from zworkbench import HostCapabilityFacade, ProviderAccessDenied
from zworkbench.codex_adapter import CodexAppServerAdapter, DEFAULT_CONFIG_OVERRIDES
from zworkbench.composition import CompositionOwner
from zworkbench.local_run import LocalReadOnlyRunConfig, ProviderProfile



def _fake_executable(root: Path) -> Path:
    executable = root / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _base_config(root: Path, *, provider_profile: ProviderProfile | None = None, provider_config_path: Path | None = None, host_enforcement: bool = False, real_provider_gate: bool = False) -> LocalReadOnlyRunConfig:
    workspace = root / "workspace"
    workspace.mkdir(exist_ok=True)
    return LocalReadOnlyRunConfig(
        case_root=root,
        workspace=workspace,
        database=root / "state" / "composition.sqlite3",
        code_home=root / "codex-home",
        codex_executable=_fake_executable(root),
        event_log=root / "events" / "codex.jsonl",
        provider_identity={
            "provider": "fake-loopback",
            "model": "fake-model",
            "endpoint": "http://127.0.0.1:11434",
            "transport": "loopback-only",
        },
        provider_profile=provider_profile,
        provider_config_path=provider_config_path,
        host_enforcement=host_enforcement,
        real_provider_gate=real_provider_gate,
    )


class HostCapabilityFacadeNegativeConstraintTests(unittest.TestCase):
    def test_local_run_must_not_directly_import_provider_adapter(self) -> None:
        """Product Control Plane code routes through the facade, not the class.

        This is the source-level guard for the R3 negative constraint
        ("产品代码不得直连").  If a future edit reintroduces
        ``from .codex_adapter import CodexAppServerAdapter`` (or any direct
        construction) into ``local_run.py``, this fails loudly instead of
        silently reverting the architecture.
        """

        source = Path(local_run_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn(
            "CodexAppServerAdapter",
            source,
            "local_run.py must not import or construct CodexAppServerAdapter directly; "
            "route Provider access through HostCapabilityFacade",
        )
        self.assertIn(
            "HostCapabilityFacade",
            source,
            "local_run.py must obtain the Provider adapter via HostCapabilityFacade",
        )

    def test_orchestrator_default_factory_is_the_facade(self) -> None:
        from zworkbench.local_run import LocalReadOnlyRunOrchestrator

        orchestrator = LocalReadOnlyRunOrchestrator(_base_config(Path(tempfile.mkdtemp())))
        self.assertIs(
            orchestrator.adapter_factory,
            HostCapabilityFacade.acquire_provider,
            "LocalReadOnlyRunOrchestrator must default to the facade, not a direct adapter factory",
        )


class HostCapabilityFacadeAcquisitionTests(unittest.TestCase):
    def test_acquire_provider_default_ollama_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config(root)
            owner = CompositionOwner(config.database)
            try:
                adapter = HostCapabilityFacade.acquire_provider(owner, config)
                self.assertIsInstance(adapter, CodexAppServerAdapter)
                # Default path keeps the ollama config overrides and no injected
                # credentials; provider/model are bound from provider_identity
                # (issue #39 single-source rule), not the facade args.
                self.assertEqual(adapter.config_overrides, DEFAULT_CONFIG_OVERRIDES)
                self.assertEqual(adapter.extra_environment, {})
            finally:
                owner.close()

    def test_acquire_provider_custom_profile_injects_env_credential(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.environ["ARK_API_KEY"] = "dummy-ark-credential-for-test-only"
            try:
                profile = ProviderProfile(
                    name="ark",
                    model_provider="custom",
                    model="ark-code-latest",
                    base_url="https://example.invalid/v1",
                    env_ref="ARK_API_KEY",
                )
                config = _base_config(root, provider_profile=profile, real_provider_gate=True)
                owner = CompositionOwner(config.database)
                try:
                    adapter = HostCapabilityFacade.acquire_provider(owner, config)
                    self.assertIsInstance(adapter, CodexAppServerAdapter)
                    # Explicit real-Provider profile clears the ollama overrides
                    # so Codex honours its own [model_providers.<name>] table, and
                    # injects the credential named by env_ref from the local env.
                    self.assertEqual(adapter.config_overrides, ())
                    self.assertEqual(
                        adapter.extra_environment.get("ARK_API_KEY"),
                        "dummy-ark-credential-for-test-only",
                        "custom profile must inject the credential named by env_ref from the local env",
                    )
                finally:
                    owner.close()
            finally:
                os.environ.pop("ARK_API_KEY", None)

    def test_acquire_provider_custom_profile_passes_provider_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "provider-config.toml"
            config_path.write_text('model = "ark-code-latest"\n', encoding="utf-8")
            profile = ProviderProfile(
                name="custom",
                model_provider="custom",
                model="ark-code-latest",
                base_url="https://ark.example.com/v1",
            )
            config = _base_config(root, provider_profile=profile, provider_config_path=config_path, real_provider_gate=True)
            owner = CompositionOwner(config.database)
            try:
                adapter = HostCapabilityFacade.acquire_provider(owner, config)
                self.assertIsInstance(adapter, CodexAppServerAdapter)
                # The explicit config path must reach the adapter so Codex can
                # discover [model_providers.<name>] (roadmap 1-9-1).
                self.assertEqual(adapter.provider_config_path, config.provider_config_path)
            finally:
                owner.close()

    def test_acquire_provider_passes_host_enforcement(self) -> None:
        # roadmap 1-9-2: the host-enforcement intent must reach the adapter so
        # ZWorkbench can become the single sandbox authority (ADR 0008).
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config(root, host_enforcement=True)
            owner = CompositionOwner(config.database)
            try:
                adapter = HostCapabilityFacade.acquire_provider(owner, config)
                self.assertIsInstance(adapter, CodexAppServerAdapter)
                self.assertTrue(adapter.host_enforcement)
            finally:
                owner.close()


class ProviderAccessGateTests(unittest.TestCase):
    """Node 1-1-4: the facade is the controlled gate between baseline and real.

    A real Provider profile must never be acquired without the explicit
    ``real_provider_gate``; the baseline (loopback / fake) path stays the default.
    """

    def _real_profile(self) -> ProviderProfile:
        return ProviderProfile(
            name="custom",
            model_provider="custom",
            model="ark-code-latest",
            base_url="https://ark.example.com/v1",
        )

    def test_real_profile_without_gate_is_denied_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config(root, provider_profile=self._real_profile())
            owner = CompositionOwner(config.database)
            try:
                with self.assertRaises(ProviderAccessDenied):
                    HostCapabilityFacade.acquire_provider(owner, config)
            finally:
                owner.close()

    def test_real_profile_with_gate_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config(root, provider_profile=self._real_profile(), real_provider_gate=True)
            owner = CompositionOwner(config.database)
            try:
                adapter = HostCapabilityFacade.acquire_provider(owner, config)
                self.assertIsInstance(adapter, CodexAppServerAdapter)
                self.assertEqual(adapter.model_provider, "custom")
            finally:
                owner.close()

    def test_baseline_default_needs_no_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _base_config(root)
            owner = CompositionOwner(config.database)
            try:
                adapter = HostCapabilityFacade.acquire_provider(owner, config)
                self.assertIsInstance(adapter, CodexAppServerAdapter)
                self.assertEqual(adapter.model_provider, "ollama")
            finally:
                owner.close()


if __name__ == "__main__":
    unittest.main()
