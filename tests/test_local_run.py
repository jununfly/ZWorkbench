from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from zworkbench import LocalReadOnlyRunConfig, preflight


class LocalReadOnlyRunPreflightTests(unittest.TestCase):
    def test_valid_case_local_configuration_passes_with_json_safe_result(self) -> None:
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
                event_log=root / "events" / "codex.jsonl",
                provider_identity={
                    "provider": "fake-loopback",
                    "model": "fake-model",
                    "endpoint": "http://127.0.0.1:11434",
                    "transport": "loopback-only",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "pass")
            self.assertTrue(result.allowed)
            payload = result.to_dict()
            self.assertEqual(payload["mode"], "local_read_only")
            self.assertEqual(payload["checks"]["provider_loopback"], True)
            self.assertEqual(payload["violations"], [])
            self.assertNotIn("api_key", json.dumps(payload, sort_keys=True))
            self.assertFalse((root / "state").exists())
            self.assertFalse((root / "codex-home").exists())
            self.assertFalse((root / "events").exists())

    def test_non_json_provider_identity_is_denied_without_leaking_value(self) -> None:
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
                    "opaque": object(),
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertFalse(result.allowed)
            self.assertIn(
                "provider_identity_not_json_serializable",
                {violation.code for violation in result.violations},
            )
            payload = json.dumps(result.to_dict(), sort_keys=True)
            self.assertNotIn("object at", payload)

    def test_loopback_endpoint_with_unsupported_scheme_is_denied(self) -> None:
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
                    "endpoint": "ftp://localhost:11434",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertIn(
                "provider_endpoint_scheme_not_supported",
                {violation.code for violation in result.violations},
            )

    def test_secret_and_external_state_paths_are_denied_without_secret_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as external:
            root = Path(temporary)
            outside = Path(external)
            workspace = root / "workspace"
            workspace.mkdir()
            executable = root / "codex"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            secret = "personal-provider-secret-value"
            config = LocalReadOnlyRunConfig(
                case_root=root,
                workspace=workspace,
                database=outside / "composition.sqlite3",
                code_home=outside / "codex-home",
                codex_executable=executable,
                event_log=outside / "events.jsonl",
                provider_identity={
                    "provider": "ark",
                    "model": "coding-model",
                    "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
                    "api_key": secret,
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            codes = {violation.code for violation in result.violations}
            self.assertTrue(
                {
                    "state_outside_case_root",
                    "code_home_outside_case_root",
                    "event_log_outside_case_root",
                    "provider_not_loopback",
                    "provider_credentials_present",
                }.issubset(codes)
            )
            self.assertNotIn(secret, json.dumps(result.to_dict(), sort_keys=True))

    def test_credential_reference_is_allowed_but_credential_value_is_not(self) -> None:
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
                    "endpoint": "http://localhost:11434",
                    "api_key_ref": "credential-store://personal-ark",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "pass")
            self.assertTrue(result.checks["no_credentials_in_config"])

    def test_malformed_endpoint_is_denied_as_a_structured_result(self) -> None:
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
                    "endpoint": "http://[::1",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertIn(
                "provider_endpoint_invalid",
                {violation.code for violation in result.violations},
            )


    def test_provider_remote_endpoint_without_authorization_is_denied(self) -> None:
        # Isolated negative-path assertion for the `provider_not_loopback` branch
        # (ADR 0009 L44: every deny branch needs its own negative assertion).
        # All other inputs are valid; only the remote, unauthorized endpoint fires.
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
                    "provider": "ark",
                    "model": "coding-model",
                    "endpoint": "https://ark.example.com/api/coding/v3",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertEqual(
                {violation.code for violation in result.violations},
                {"provider_not_loopback"},
            )

    def test_provider_credential_value_in_config_is_denied(self) -> None:
        # Isolated negative-path assertion for the `provider_credentials_present`
        # branch. A credential *value* must be denied even when the endpoint is a
        # safe loopback (so no other branch should co-fire).
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
                    "api_key": "sk-secret-value-must-not-be-recorded",
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertEqual(
                {violation.code for violation in result.violations},
                {"provider_credentials_present"},
            )
            self.assertNotIn(
                "sk-secret-value-must-not-be-recorded",
                json.dumps(result.to_dict(), sort_keys=True),
            )

    def test_provider_identity_missing_required_field_is_denied(self) -> None:
        # Negative-path assertion for the `provider_identity_missing_or_invalid`
        # branch. A missing required field must fail closed. (Note: the loopback
        # check is coupled to identity validity, so `provider_not_loopback` may
        # co-fire; the assertion only requires this branch to be present.)
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
                    "provider": "ark",
                    "endpoint": "http://127.0.0.1:11434",
                    # `model` intentionally absent
                },
            )

            result = preflight(config)

            self.assertEqual(result.status, "deny")
            self.assertIn(
                "provider_identity_missing_or_invalid",
                {violation.code for violation in result.violations},
            )


if __name__ == "__main__":
    unittest.main()
