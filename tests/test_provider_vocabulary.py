"""Consistency tests for the owner-side provider vocabulary SSOT (1-6-2).

ADR 0009 L44 requires a single vocabulary mapping table on the owner side
(SSOT) plus a consistency test. ``src/zworkbench/provider_vocabulary.py`` is
that table; this module enforces two-way consistency:

* every registered deny code is actually referenced by the admission layer
  (no phantom entries), and
* every deny code the running code emits at preflight time is registered
  (no unregistered code may slip through).

It also pins the fail-closed ``classify_provider_transport`` behaviour and the
CLI / adapter default resolutions, so the vocabulary cannot drift silently.
"""

from __future__ import annotations

import pathlib
import re
import tempfile
import unittest
from pathlib import Path

from zworkbench import LocalReadOnlyRunConfig, preflight
from zworkbench.local_run import ProviderProfile
from zworkbench.provider_vocabulary import (
    DEFAULT_MODEL_PROVIDER,
    KNOWN_DENY_CODES,
    PROVIDER_VOCABULARY,
    TRANSPORT_LOOPBACK_ONLY,
    TRANSPORT_NETWORK_EGRESS,
    classify_provider_transport,
    is_known_provider,
    resolve_model_provider,
)

_SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "zworkbench"
_SOURCE = (_SRC_DIR / "local_run.py").read_text(encoding="utf-8") + "\n" + (
    _SRC_DIR / "cli.py"
).read_text(encoding="utf-8")


def _quoted_in_source(code: str) -> bool:
    return re.search(r'["\']' + re.escape(code) + r'["\']', _SOURCE) is not None


class ProviderVocabularyTests(unittest.TestCase):
    # --- two-way deny-code consistency -----------------------------------

    def test_every_registered_deny_code_is_referenced_in_source(self) -> None:
        # No phantom entries: each SSOT code must be used by the admission
        # layer in local_run.py or cli.py.
        for code in KNOWN_DENY_CODES:
            self.assertTrue(
                _quoted_in_source(code),
                "SSOT deny code {0!r} is not referenced by local_run.py/cli.py".format(code),
            )

    def test_preflight_emits_only_registered_deny_codes(self) -> None:
        emitted: set[str] = set()
        for config in _sweep_configs():
            result = preflight(config)
            emitted.update(violation.code for violation in result.violations)

        # Every code the running code emits must be a registered SSOT entry.
        unregistered = emitted - KNOWN_DENY_CODES
        self.assertEqual(
            unregistered,
            set(),
            "preflight emitted deny codes not present in the SSOT vocabulary: {0}".format(
                sorted(unregistered)
            ),
        )

        # Sanity: the sweep actually exercises the key branches (otherwise the
        # test passes vacuously).
        for expected in (
            "provider_not_loopback",
            "provider_credentials_present",
            "provider_identity_missing_or_invalid",
            "state_outside_case_root",
            "codex_executable_missing",
            # The real-Provider branches must stay covered: without them this
            # guard passes vacuously and unregistered real-provider codes slip
            # through unnoticed (issue #40).
            "real_provider_config_missing",
            "real_provider_gate_disabled",
        ):
            self.assertIn(expected, emitted)

    # --- fail-closed transport classification -----------------------------

    def test_classify_provider_transport_is_fail_closed(self) -> None:
        # Loopback defaults always classify as loopback-only.
        self.assertEqual(
            classify_provider_transport("fake-loopback", authorized=False),
            TRANSPORT_LOOPBACK_ONLY,
        )
        self.assertEqual(
            classify_provider_transport("ollama", authorized=False),
            TRANSPORT_LOOPBACK_ONLY,
        )
        # A remote provider without explicit authorization collapses to
        # loopback-only (fail-closed), never to network-egress.
        self.assertEqual(
            classify_provider_transport("ark", authorized=False),
            TRANSPORT_LOOPBACK_ONLY,
        )
        # Only an explicitly authorized remote provider reaches network-egress.
        self.assertEqual(
            classify_provider_transport("ark", authorized=True),
            TRANSPORT_NETWORK_EGRESS,
        )
        self.assertEqual(
            classify_provider_transport("custom", authorized=True),
            TRANSPORT_NETWORK_EGRESS,
        )
        # Unknown / empty names are fail-closed too.
        self.assertEqual(
            classify_provider_transport("unknown-provider", authorized=False),
            TRANSPORT_LOOPBACK_ONLY,
        )
        self.assertEqual(
            classify_provider_transport(None, authorized=False),
            TRANSPORT_LOOPBACK_ONLY,
        )
        self.assertEqual(
            classify_provider_transport("", authorized=True),
            TRANSPORT_LOOPBACK_ONLY,
        )

    # --- CLI / adapter default resolution ---------------------------------

    def test_cli_and_adapter_defaults_resolve_to_loopback(self) -> None:
        fake_loopback = PROVIDER_VOCABULARY["fake-loopback"]
        self.assertEqual(fake_loopback.transport, TRANSPORT_LOOPBACK_ONLY)
        self.assertEqual(fake_loopback.model_provider, "ollama")

        ollama = PROVIDER_VOCABULARY["ollama"]
        self.assertEqual(ollama.transport, TRANSPORT_LOOPBACK_ONLY)
        self.assertEqual(ollama.model_provider, "ollama")

        self.assertTrue(is_known_provider("fake-loopback"))
        self.assertFalse(is_known_provider("nonexistent-provider"))

    def test_loopback_only_constant_is_canonical(self) -> None:
        # The SSOT defines the canonical transport string consumed by the
        # adapter / worker bridge after the 1-6-2 wiring.
        self.assertEqual(TRANSPORT_LOOPBACK_ONLY, "loopback-only")

    # --- model_provider resolution (issue #40 A) -------------------------
    #
    # The vocabulary owns provider -> model_provider. Product code must never
    # inline "ollama": it must resolve through the SSOT so a declared remote
    # provider identity cannot silently run on the ollama backend.

    def test_resolve_model_provider_follows_vocabulary(self) -> None:
        self.assertEqual(resolve_model_provider("fake-loopback"), "ollama")
        self.assertEqual(resolve_model_provider("ollama"), "ollama")
        self.assertEqual(resolve_model_provider("ark"), "custom")
        self.assertEqual(resolve_model_provider("custom"), "custom")

    def test_resolve_model_provider_is_fail_closed(self) -> None:
        # Unknown / empty / non-string names fall back to the loopback default,
        # never to a remote backend.
        self.assertEqual(resolve_model_provider("unknown-provider"), DEFAULT_MODEL_PROVIDER)
        self.assertEqual(resolve_model_provider(""), DEFAULT_MODEL_PROVIDER)
        self.assertEqual(resolve_model_provider(None), DEFAULT_MODEL_PROVIDER)
        self.assertEqual(resolve_model_provider(42), DEFAULT_MODEL_PROVIDER)

    def test_default_model_provider_is_ollama(self) -> None:
        # Pins the historical v1 fallback: #40 must not change baseline behaviour.
        self.assertEqual(DEFAULT_MODEL_PROVIDER, "ollama")

    def test_vocabulary_model_provider_matches_resolver(self) -> None:
        # No drift between the table and the resolver.
        for name, entry in PROVIDER_VOCABULARY.items():
            self.assertEqual(resolve_model_provider(name), entry.model_provider)


def _make_config(
    *,
    provider_identity=None,
    database=None,
    codex_executable=None,
    provider_profile=None,
    provider_config_path=None,
    real_provider_gate=False,
) -> LocalReadOnlyRunConfig:
    root = Path(tempfile.mkdtemp())
    workspace = root / "workspace"
    workspace.mkdir()
    executable = root / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    return LocalReadOnlyRunConfig(
        case_root=root,
        workspace=workspace,
        database=database if database is not None else root / "state" / "composition.sqlite3",
        code_home=root / "codex-home",
        codex_executable=codex_executable if codex_executable is not None else executable,
        provider_identity=provider_identity
        if provider_identity is not None
        else {
            "provider": "fake-loopback",
            "model": "fake-model",
            "endpoint": "http://127.0.0.1:11434",
        },
        provider_profile=provider_profile,
        provider_config_path=provider_config_path,
        real_provider_gate=real_provider_gate,
    )


def _ark_profile() -> ProviderProfile:
    return ProviderProfile(
        name="ark",
        model_provider="custom",
        model="coding-model",
        base_url="https://ark.example.com/api/coding/v3",
        wire_api="responses",
    )


def _ark_identity() -> dict:
    return {
        "provider": "ark",
        "model": "coding-model",
        "endpoint": "https://ark.example.com/api/coding/v3",
        "model_provider": "custom",
    }


def _sweep_configs():
    """Yield configs that trigger distinct preflight deny branches."""
    yield _make_config()  # valid, emits no violations

    # provider_not_loopback
    yield _make_config(
        provider_identity={
            "provider": "ark",
            "model": "coding-model",
            "endpoint": "https://ark.example.com/api/coding/v3",
        },
    )

    # provider_credentials_present (credential value on a loopback endpoint)
    yield _make_config(
        provider_identity={
            "provider": "fake-loopback",
            "model": "fake-model",
            "endpoint": "http://127.0.0.1:11434",
            "api_key": "sk-secret-must-not-be-recorded",
        },
    )

    # provider_identity_missing_or_invalid (missing `model`)
    yield _make_config(
        provider_identity={
            "provider": "ark",
            "endpoint": "http://127.0.0.1:11434",
        },
    )

    # state_outside_case_root
    yield _make_config(database=Path(tempfile.mkdtemp()) / "composition.sqlite3")

    # codex_executable_missing
    missing = _make_config()
    yield _make_config(codex_executable=missing.case_root / "does-not-exist")

    # real_provider_config_missing: a profile was selected but no
    # --provider-config path backs it.
    yield _make_config(provider_identity=_ark_identity(), provider_profile=_ark_profile())

    # real_provider_gate_disabled: profile + config path present, but the
    # explicit real-Provider gate was never enabled.
    gate_root = Path(tempfile.mkdtemp())
    config_file = gate_root / "zw-providers.toml"
    config_file.write_text('[model_providers.ark]\nbase_url = "https://ark.example.com"\n', encoding="utf-8")
    yield _make_config(
        provider_identity=_ark_identity(),
        provider_profile=_ark_profile(),
        provider_config_path=config_file,
        real_provider_gate=False,
    )


if __name__ == "__main__":
    unittest.main()
