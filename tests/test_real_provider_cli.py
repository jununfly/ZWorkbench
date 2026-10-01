"""Regression tests for roadmap node 1-3: open a real Provider on the product CLI.

Covers the three fail-closed / authorization branches plus the config reader:

* ollama stays the default fallback (loopback, ``model_provider="ollama"``);
* a configured remote/custom provider is authorized via an explicit allowlist;
* an unknown / unconfigured provider is denied (fail-closed);
* the Codex-style config.toml provider reader returns the right profiles and
  never captures credential *values*.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from zworkbench import (
    CompositionOwner,
    LocalReadOnlyRunConfig,
    ProviderProfile,
    preflight,
)
from zworkbench.cli import main
from zworkbench.codex_adapter import DEFAULT_CONFIG_OVERRIDES
from zworkbench.local_run import (
    _default_adapter_factory,
    load_provider_profiles,
)


FAKE_CODEX = """
import json
import sys

THREAD_ID = "cli-fixture-thread"
TURN_ID = "cli-fixture-turn"


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    request_id = message["id"]
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "thread/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    elif method == "turn/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        send({"jsonrpc": "2.0", "method": "item/agentMessage/delta", "params": {"turnId": TURN_ID, "delta": "fixture-ok"}})
        send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
    elif method == "thread/read":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown method"}})
"""


class _ConfigFixture:
    def make_case(self, root: Path) -> LocalReadOnlyRunConfig:
        workspace = root / "workspace"
        workspace.mkdir()
        executable = root / "codex"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        return LocalReadOnlyRunConfig(
            case_root=root,
            workspace=workspace,
            database=root / "state" / "composition.sqlite3",
            code_home=root / "codex-home",
            codex_executable=executable,
            event_log=root / "events" / "codex.jsonl",
            provider_identity={
                "provider": "fake-loopback",
                "model": "fake-model",
                "endpoint": "http://127.0.0.1:11434",
            },
        )

    def write_config(self, root: Path, body: str) -> Path:
        path = root / "codex-config.toml"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path


class ProviderConfigReaderTests(unittest.TestCase):
    def test_load_provider_profiles_reads_both_table_styles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            body = """
            model = "ark-code-latest"

            [model_providers.custom]
            name = "ark_codingplan"
            base_url = "https://ark.cn-beijing.volces.com/api/coding/v3"
            wire_api = "responses"
            requires_openai_auth = false
            experimental_bearer_token = "ark-SECRET-MUST-NOT-LEAK"

            [provider.ark]
            base_url = "https://ark.example.com/v1"
            wire_api = "responses"
            requires_openai_auth = true
            env = "ARK_API_KEY"
            """
            path = _ConfigFixture().write_config(root, body)
            profiles = load_provider_profiles(path)

            self.assertEqual(set(profiles), {"custom", "ark"})

            custom = profiles["custom"]
            self.assertEqual(custom.model_provider, "custom")
            self.assertEqual(custom.model, "ark-code-latest")
            self.assertEqual(custom.base_url, "https://ark.cn-beijing.volces.com/api/coding/v3")
            self.assertEqual(custom.wire_api, "responses")
            self.assertFalse(custom.requires_openai_auth)
            # The bearer token value must not be captured at all.
            self.assertIsNone(custom.env_ref)

            ark = profiles["ark"]
            self.assertEqual(ark.model_provider, "ark")
            self.assertEqual(ark.model, "ark-code-latest")
            self.assertEqual(ark.base_url, "https://ark.example.com/v1")
            self.assertTrue(ark.requires_openai_auth)
            self.assertEqual(ark.env_ref, "ARK_API_KEY")

            # No credential value is ever returned by the reader.
            self.assertNotIn("ark-SECRET-MUST-NOT-LEAK", repr(profiles))

    def test_load_provider_profiles_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "does-not-exist.toml"
            with self.assertRaises(FileNotFoundError):
                load_provider_profiles(missing)


class OllamaDefaultFallbackTests(unittest.TestCase):
    def test_ollama_default_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = _ConfigFixture().make_case(Path(temporary))
            result = preflight(config)
            self.assertEqual(result.status, "pass")
            self.assertTrue(result.allowed)
            self.assertTrue(result.checks["provider_loopback"])

    def test_factory_uses_ollama_default_when_no_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = _ConfigFixture().make_case(Path(temporary))
            db = config.database
            with CompositionOwner(db) as owner:
                adapter = _default_adapter_factory(owner, config)
                try:
                    self.assertEqual(adapter.model_provider, "ollama")
                    self.assertEqual(adapter.model, "fake-model")
                    self.assertEqual(adapter.config_overrides, DEFAULT_CONFIG_OVERRIDES)
                    self.assertEqual(adapter.extra_environment, {})
                finally:
                    adapter.close()


class AuthorizedRemoteProviderTests(unittest.TestCase):
    def test_authorized_remote_provider_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _ConfigFixture().make_case(root)
            config = LocalReadOnlyRunConfig(
                case_root=config.case_root,
                workspace=config.workspace,
                database=config.database,
                code_home=config.code_home,
                codex_executable=config.codex_executable,
                event_log=config.event_log,
                provider_identity={
                    "provider": "ark",
                    "model": "ark-code-latest",
                    "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
                },
                authorized_providers=frozenset({"ark", "custom"}),
            )
            result = preflight(config)
            self.assertEqual(result.status, "pass")
            self.assertTrue(result.allowed)
            self.assertTrue(result.checks["provider_loopback"])

    def test_factory_uses_real_model_provider_when_profile_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _ConfigFixture().make_case(root)
            profile = ProviderProfile(
                name="custom",
                model_provider="custom",
                model="ark-code-latest",
                base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
            )
            config = LocalReadOnlyRunConfig(
                case_root=config.case_root,
                workspace=config.workspace,
                database=config.database,
                code_home=config.code_home,
                codex_executable=config.codex_executable,
                event_log=config.event_log,
                provider_identity={
                    "provider": "custom",
                    "model": "ark-code-latest",
                    "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
                },
                authorized_providers=frozenset({"custom"}),
                provider_profile=profile,
            )
            with CompositionOwner(config.database) as owner:
                adapter = _default_adapter_factory(owner, config)
                try:
                    self.assertEqual(adapter.model_provider, "custom")
                    self.assertEqual(adapter.model, "ark-code-latest")
                    self.assertEqual(adapter.config_overrides, ())
                    self.assertEqual(adapter.extra_environment, {})
                finally:
                    adapter.close()

    def test_factory_injects_credential_from_local_env_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _ConfigFixture().make_case(root)
            profile = ProviderProfile(
                name="ark",
                model_provider="ark",
                model="ark-code-latest",
                base_url="https://ark.example.com/v1",
                env_ref="ARK_API_KEY",
            )
            config = LocalReadOnlyRunConfig(
                case_root=config.case_root,
                workspace=config.workspace,
                database=config.database,
                code_home=config.code_home,
                codex_executable=config.codex_executable,
                event_log=config.event_log,
                provider_identity={
                    "provider": "ark",
                    "model": "ark-code-latest",
                    "endpoint": "https://ark.example.com/v1",
                },
                authorized_providers=frozenset({"ark"}),
                provider_profile=profile,
            )
            with CompositionOwner(config.database) as owner:
                with patch.dict(os.environ, {"ARK_API_KEY": "local-secret-value"}):
                    with _default_adapter_factory(owner, config) as adapter:
                        self.assertEqual(adapter.extra_environment, {"ARK_API_KEY": "local-secret-value"})
                with patch.dict(os.environ, {}, clear=True):
                    with _default_adapter_factory(owner, config) as adapter:
                        self.assertEqual(adapter.extra_environment, {})


class UnknownProviderFailClosedTests(unittest.TestCase):
    def test_unknown_remote_provider_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _ConfigFixture().make_case(root)
            config = LocalReadOnlyRunConfig(
                case_root=config.case_root,
                workspace=config.workspace,
                database=config.database,
                code_home=config.code_home,
                codex_executable=config.codex_executable,
                event_log=config.event_log,
                provider_identity={
                    "provider": "rogue",
                    "model": "rogue-model",
                    "endpoint": "https://rogue.example.invalid/v1",
                },
                authorized_providers=frozenset({"ark"}),
            )
            result = preflight(config)
            self.assertEqual(result.status, "deny")
            self.assertFalse(result.allowed)
            self.assertIn(
                "provider_not_loopback",
                {violation.code for violation in result.violations},
            )

    def test_remote_endpoint_without_profile_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _ConfigFixture().make_case(root)
            config = LocalReadOnlyRunConfig(
                case_root=config.case_root,
                workspace=config.workspace,
                database=config.database,
                code_home=config.code_home,
                codex_executable=config.codex_executable,
                event_log=config.event_log,
                provider_identity={
                    "provider": "ark",
                    "model": "ark-code-latest",
                    "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
                },
                authorized_providers=frozenset(),
            )
            result = preflight(config)
            self.assertEqual(result.status, "deny")
            self.assertIn(
                "provider_not_loopback",
                {violation.code for violation in result.violations},
            )


class CliRealProviderTests(unittest.TestCase):
    def _fake_codex(self, root: Path) -> Path:
        executable = root / "fake-codex"
        executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(FAKE_CODEX)), encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def test_cli_runs_with_authorized_provider_profile(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)
            config_path = _ConfigFixture().write_config(
                root,
                """
                model = "ark-code-latest"
                [provider.ark]
                base_url = "https://ark.example.com/v1"
                wire_api = "responses"
                """,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(
                    [
                        "run",
                        "--case-root",
                        str(root),
                        "--workspace",
                        str(workspace),
                        "--prompt",
                        "inspect the fixture and return fixture-ok",
                        "--codex",
                        str(codex),
                        "--run-id",
                        "cli-ark-1",
                        "--provider-profile",
                        "ark",
                        "--provider-config",
                        str(config_path),
                    ]
                )
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["execution"]["text"], "fixture-ok")
            self.assertTrue(payload["owner"]["database_present"])
            self.assertTrue(payload["owner"]["recorded_view_present"])

    def test_cli_unknown_provider_profile_is_denied(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)
            config_path = _ConfigFixture().write_config(
                root,
                """
                model = "ark-code-latest"
                [provider.ark]
                base_url = "https://ark.example.com/v1"
                """,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(
                    [
                        "run",
                        "--case-root",
                        str(root),
                        "--workspace",
                        str(workspace),
                        "--prompt",
                        "must not execute",
                        "--codex",
                        str(codex),
                        "--provider-profile",
                        "not-present",
                        "--provider-config",
                        str(config_path),
                    ]
                )
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertFalse((root / "state" / "composition.sqlite3").exists())

    def test_cli_missing_provider_config_is_denied(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            codex = self._fake_codex(root)
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(
                    [
                        "run",
                        "--case-root",
                        str(root),
                        "--workspace",
                        str(workspace),
                        "--prompt",
                        "must not execute",
                        "--codex",
                        str(codex),
                        "--provider-profile",
                        "ark",
                        "--provider-config",
                        str(root / "missing.toml"),
                    ]
                )
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(payload["status"], "denied")
            self.assertFalse((root / "state" / "composition.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
