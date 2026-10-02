"""Single source of truth for ZWorkbench provider vocabulary and transport classes.

ADR 0009 L44 requires a single vocabulary mapping table on the owner side
(SSOT) plus a consistency test. This module *is* that table. It centralizes
three vocabularies that were previously scattered as inline string literals
across ``local_run.py`` / ``cli.py`` / ``codex_adapter.py``:

* ``KNOWN_TRANSPORTS`` -- the transport classes ZWorkbench admits. v1 admits
  only ``loopback-only``; ``network-egress`` exists for explicit
  profile-authorized remote providers.
* ``PROVIDER_VOCABULARY`` -- canonical provider name -> model_provider ->
  transport class. ``fake-loopback`` and ``ollama`` are the v1 loopback
  defaults; ``ark`` / ``custom`` are remote providers reachable only through
  an explicit authorized profile.
* ``KNOWN_DENY_CODES`` -- every ``PreflightViolation.code`` the admission
  layer may emit. The consistency test enforces that the running code never
  emits an unregistered code.

``classify_provider_transport`` is the single function that derives a
transport class from a provider identity, replacing scattered ``setdefault``
backfills (ADR 0009 C5). It is fail-closed: an unknown name, or a remote
provider that is not explicitly authorized, collapses to ``loopback-only``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

# Transport classes -------------------------------------------------------

TRANSPORT_LOOPBACK_ONLY = "loopback-only"
TRANSPORT_NETWORK_EGRESS = "network-egress"
KNOWN_TRANSPORTS: FrozenSet[str] = frozenset(
    {TRANSPORT_LOOPBACK_ONLY, TRANSPORT_NETWORK_EGRESS}
)


@dataclass(frozen=True)
class ProviderVocabEntry:
    """One canonical provider vocabulary row."""

    provider: str
    model_provider: str
    transport: str
    note: str = ""


# Provider vocabulary (SSOT) ---------------------------------------------
#
# ``fake-loopback`` and ``ollama`` are the v1 loopback defaults. ``ark`` and
# ``custom`` are profile-authorized remote providers (network-egress); they
# are only admissible when an explicit provider profile names them.

PROVIDER_VOCABULARY: dict[str, ProviderVocabEntry] = {
    "fake-loopback": ProviderVocabEntry(
        provider="fake-loopback",
        model_provider="ollama",
        transport=TRANSPORT_LOOPBACK_ONLY,
        note="built-in loopback fixture used by tests and dry runs",
    ),
    "ollama": ProviderVocabEntry(
        provider="ollama",
        model_provider="ollama",
        transport=TRANSPORT_LOOPBACK_ONLY,
        note="default adapter model_provider for the local ollama server",
    ),
    "ark": ProviderVocabEntry(
        provider="ark",
        model_provider="custom",
        transport=TRANSPORT_NETWORK_EGRESS,
        note="remote provider; only admissible via an explicit authorized profile",
    ),
    "custom": ProviderVocabEntry(
        provider="custom",
        model_provider="custom",
        transport=TRANSPORT_NETWORK_EGRESS,
        note="generic remote provider reachable only via profile",
    ),
}


# Deny-code vocabulary (SSOT) --------------------------------------------
#
# Every ``PreflightViolation.code`` raised by ``local_run.preflight`` or the
# CLI admission path must be a member of this set. The consistency test
# enforces that the running code never emits an unregistered code.

KNOWN_DENY_CODES: FrozenSet[str] = frozenset(
    {
        # local_run.preflight
        "case_root_missing_or_not_directory",
        "mode_not_local_read_only",
        "sandbox_not_read_only",
        "approval_policy_not_disabled",
        "workspace_missing_or_not_directory",
        "workspace_outside_case_root",
        "state_outside_case_root",
        "code_home_outside_case_root",
        "event_log_outside_case_root",
        "codex_executable_missing",
        "codex_executable_not_executable",
        "provider_identity_missing_or_invalid",
        "provider_not_loopback",
        "provider_identity_not_json_serializable",
        "required_features_not_disabled",
        "provider_credentials_present",
        "provider_endpoint_invalid",
        "provider_endpoint_scheme_not_supported",
        "provider_endpoint_embeds_credentials",
        # cli admission path
        "cli_path_outside_case_root",
        "cli_path_conflict",
        "timeout_not_positive",
        "prompt_contains_credential_pattern",
    }
)


def classify_provider_transport(provider_name: object, *, authorized: bool) -> str:
    """Resolve the transport class for a provider name, fail-closed.

    An unknown provider name (or one that requires network egress but is not
    explicitly authorized) collapses to ``loopback-only``. This is the single
    place that decides transport from identity; callers must not re-derive the
    string inline (ADR 0009 C5).
    """

    if not isinstance(provider_name, str) or not provider_name:
        return TRANSPORT_LOOPBACK_ONLY
    entry = PROVIDER_VOCABULARY.get(provider_name)
    if entry is None:
        return TRANSPORT_LOOPBACK_ONLY
    if entry.transport == TRANSPORT_NETWORK_EGRESS and not authorized:
        return TRANSPORT_LOOPBACK_ONLY
    return entry.transport


def is_known_provider(provider_name: str) -> bool:
    """True when ``provider_name`` is a registered vocabulary entry."""

    return provider_name in PROVIDER_VOCABULARY
