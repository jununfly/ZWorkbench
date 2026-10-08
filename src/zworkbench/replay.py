"""Owner-backed evidence and replay boundaries.

The service in this module is deliberately not an execution engine.  It has
three explicit entry points:

* ``recorded_view`` reads facts already persisted by ``CompositionOwner``;
* ``simulated_replay`` reads a sealed local cassette and returns its recorded
  result;
* ``live_replay`` validates the same provenance and then denies execution.

None of the entry points starts a process, calls a Provider, invokes a tool,
or writes an external effect.  The owner remains the only durable source of
truth; the service only reads its state and returns an auditable result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .composition import CompositionOwner, CompositionError, SCHEMA
from .worker_contract import (
    ComponentIdentity,
    IdentityChain,
    ProviderIdentity,
    UNKNOWN,
    _is_missing,
)


REPLAY_SERVICE_SCHEMA = "zworkbench.evidence-replay/v1"
CASSETTE_SCHEMA = "zworkbench.replay-cassette/v1"
REPLAY_MODES = frozenset({"recorded_view", "simulated_replay", "live_replay"})
CASSETTE_FIELDS = frozenset(
    {
        "schema",
        "sealed",
        "cassette_id",
        "source_run_id",
        "source_event_digest",
        "environment_digest",
        "provider_identity",
        "interactions",
        "tool_results",
        "expected_semantic_result",
    }
)
MAX_CASSETTE_BYTES = 4 * 1024 * 1024


class ReplayError(CompositionError):
    """Base class for a replay boundary error."""


@dataclass(frozen=True)
class CassetteIdentity:
    """Pinned identity of a sealed replay cassette."""

    cassette_id: str
    digest: str

    def __post_init__(self) -> None:
        _require_text(self.cassette_id, "cassette_identity.cassette_id")
        _require_text(self.digest, "cassette_identity.digest")

    def to_dict(self) -> Dict[str, str]:
        return {"cassette_id": self.cassette_id, "digest": self.digest}

    def missing_fields(self, prefix: str = "cassette_identity") -> Tuple[str, ...]:
        missing = []
        if self.cassette_id == UNKNOWN:
            missing.append(f"{prefix}.cassette_id")
        if self.digest == UNKNOWN:
            missing.append(f"{prefix}.digest")
        return tuple(missing)


@dataclass(frozen=True)
class ReplayIdentity:
    """All provenance needed to interpret owner evidence or a replay.

    ``plugin_identities`` is an explicit tuple: an empty tuple means that the
    pinned Harness profile has no plugins, while ``unknown`` in any component
    means that the evidence cannot be promoted to a reproducible result.
    """

    harness_identity: ComponentIdentity
    plugin_identities: Tuple[ComponentIdentity, ...]
    worker_identity: ComponentIdentity
    provider_identity: ProviderIdentity
    identity_chain: IdentityChain
    tool_schema_digest: str
    policy_digest: str
    workspace_digest: str
    environment_digest: str
    owner_schema: str
    source_event_digest: str
    cassette_identity: Optional[CassetteIdentity] = None

    def __post_init__(self) -> None:
        if not isinstance(self.harness_identity, ComponentIdentity):
            raise TypeError("harness_identity must be ComponentIdentity")
        if not isinstance(self.worker_identity, ComponentIdentity):
            raise TypeError("worker_identity must be ComponentIdentity")
        if not isinstance(self.provider_identity, ProviderIdentity):
            raise TypeError("provider_identity must be ProviderIdentity")
        if not isinstance(self.identity_chain, IdentityChain):
            raise TypeError("identity_chain must be IdentityChain")
        plugins = tuple(self.plugin_identities)
        if any(not isinstance(item, ComponentIdentity) for item in plugins):
            raise TypeError("plugin_identities must contain ComponentIdentity values")
        object.__setattr__(self, "plugin_identities", plugins)
        for field_name in (
            "tool_schema_digest",
            "policy_digest",
            "workspace_digest",
            "environment_digest",
            "owner_schema",
            "source_event_digest",
        ):
            _require_text(getattr(self, field_name), f"replay_identity.{field_name}")
        if self.cassette_identity is not None and not isinstance(self.cassette_identity, CassetteIdentity):
            raise TypeError("cassette_identity must be CassetteIdentity or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "harness_identity": self.harness_identity.to_dict(),
            "plugin_identities": [item.to_dict() for item in self.plugin_identities],
            "worker_identity": self.worker_identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "identity_chain": self.identity_chain.to_dict(),
            "tool_schema_digest": self.tool_schema_digest,
            "policy_digest": self.policy_digest,
            "workspace_digest": self.workspace_digest,
            "environment_digest": self.environment_digest,
            "owner_schema": self.owner_schema,
            "source_event_digest": self.source_event_digest,
            "cassette_identity": self.cassette_identity.to_dict() if self.cassette_identity else None,
        }

    def missing_fields(self, mode: str) -> Tuple[str, ...]:
        """Return missing identity fields without guessing their values."""

        if mode not in REPLAY_MODES:
            raise ValueError(f"unsupported replay mode: {mode}")
        missing = []
        for prefix, component in (
            ("harness_identity", self.harness_identity),
            ("worker_identity", self.worker_identity),
        ):
            missing.extend(f"{prefix}.{field}" for field in component.missing_fields())
        for index, component in enumerate(self.plugin_identities):
            missing.extend(f"plugin_identities[{index}].{field}" for field in component.missing_fields())
        if not self.provider_identity.is_complete():
            for field_name in ("provider", "model", "endpoint", "transport"):
                if getattr(self.provider_identity, field_name) == UNKNOWN:
                    missing.append(f"provider_identity.{field_name}")
        for field_name in (
            "tool_schema_digest",
            "policy_digest",
            "workspace_digest",
            "environment_digest",
            "owner_schema",
            "source_event_digest",
        ):
            if _is_missing(getattr(self, field_name)):
                missing.append(field_name)
        for field_name in self.identity_chain.missing_fields():
            missing.append(f"identity_chain.{field_name}")
        if mode in {"simulated_replay", "live_replay"}:
            if self.cassette_identity is None:
                missing.append("cassette_identity")
            else:
                missing.extend(self.cassette_identity.missing_fields())
        elif self.cassette_identity is not None:
            missing.extend(self.cassette_identity.missing_fields())
        return tuple(missing)


class OwnerBackedReplayService:
    """Read-only replay facade backed by a ``CompositionOwner``."""

    def __init__(self, owner: CompositionOwner):
        self.owner = owner

    @staticmethod
    def event_digest(events: Sequence[Mapping[str, Any]]) -> str:
        """Return a deterministic digest for an owner event projection."""

        encoded = json.dumps(
            [dict(event) for event in events],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return _sha256(encoded)

    def owner_event_digest(self, run_id: str) -> str:
        """Digest the saved events for one run without executing anything."""

        return self.event_digest(self.owner.events(run_id))

    def recorded_view(
        self,
        run_id: str,
        identity: ReplayIdentity,
        replay_id: str,
    ) -> Dict[str, Any]:
        """Project owner facts; never re-execute the recorded run."""

        result = self._base_result("recorded_view", replay_id, identity)
        missing = identity.missing_fields("recorded_view")
        if missing:
            return self._unknown(result, "missing_replay_identity", missing)
        try:
            run = self.owner.get_run(run_id)
            events = self.owner.events(run_id)
        except CompositionError:
            return self._unknown(result, "owner_source_run_missing")
        if identity.owner_schema != SCHEMA:
            return self._unknown(result, "owner_schema_mismatch")
        actual_digest = self.event_digest(events)
        if actual_digest != identity.source_event_digest:
            return self._unknown(result, "source_event_digest_mismatch")
        semantic = next((item["value"] for item in run["results"] if item["kind"] == "semantic"), None)
        if semantic is None:
            return self._unknown(result, "semantic_result_missing")
        result.update(
            {
                "status": "viewed",
                "source_run_id": run_id,
                "run": run,
                "events": events,
                "event_count": len(events),
                "semantic_result": semantic,
                "view_only": True,
                "owner_state_digest": self.owner.state_digest(),
            }
        )
        return result

    def simulated_replay(
        self,
        cassette_path: Path | str,
        identity: ReplayIdentity,
        replay_id: str,
    ) -> Dict[str, Any]:
        """Return a sealed cassette's result without calling its dependencies."""

        result = self._base_result("simulated_replay", replay_id, identity)
        missing = identity.missing_fields("simulated_replay")
        if missing:
            return self._unknown(result, "missing_replay_identity", missing)
        cassette, error = self._load_and_validate_cassette(cassette_path, identity)
        if error:
            return self._unknown(result, error)
        source_error = self._validate_owner_source(cassette, identity)
        if source_error:
            return self._unknown(result, source_error)
        result.update(
            {
                "status": "simulated",
                "source_run_id": cassette["source_run_id"],
                "cassette_id": cassette["cassette_id"],
                "cassette_only": True,
                "interaction_count": len(cassette["interactions"]),
                "tool_result_count": len(cassette["tool_results"]),
                "semantic_result": cassette["expected_semantic_result"],
                "owner_state_digest": self.owner.state_digest(),
            }
        )
        return result

    def live_replay(
        self,
        cassette_path: Path | str,
        identity: ReplayIdentity,
        replay_id: str,
    ) -> Dict[str, Any]:
        """Validate the requested replay, then fail closed before execution."""

        result = self._base_result("live_replay", replay_id, identity)
        missing = identity.missing_fields("live_replay")
        if missing:
            return self._unknown(result, "missing_replay_identity", missing)
        cassette, error = self._load_and_validate_cassette(cassette_path, identity)
        if error:
            return self._unknown(result, error)
        source_error = self._validate_owner_source(cassette, identity)
        if source_error:
            return self._unknown(result, source_error)
        result.update(
            {
                "status": "denied",
                "safe_denial": True,
                "policy_decision": {
                    "replay_mode": "live_replay",
                    "approval_required": True,
                    "approval_granted": False,
                    "decision": "deny",
                    "reason": "live_replay_disabled_by_default",
                },
                "owner_state_digest": self.owner.state_digest(),
            }
        )
        result["zero_external_execution"] = assert_zero_external_execution(result)
        return result

    def _base_result(self, mode: str, replay_id: str, identity: ReplayIdentity) -> Dict[str, Any]:
        _require_text(replay_id, "replay_id")
        return {
            "schema": REPLAY_SERVICE_SCHEMA,
            "replay_id": replay_id,
            "replay_mode": mode,
            "provenance": identity.to_dict(),
            "owner_backed": True,
            "execution_performed": False,
            "provider_requests": 0,
            "tool_invocations": 0,
            "external_calls": 0,
            "side_effect_count": 0,
        }

    @staticmethod
    def _unknown(
        result: Dict[str, Any],
        reason: str,
        missing_identity: Sequence[str] = (),
    ) -> Dict[str, Any]:
        result.update(
            {
                "status": "unknown",
                "safe_stop": True,
                "reason": reason,
                "missing_identity": list(missing_identity),
            }
        )
        return result

    def _validate_owner_source(self, cassette: Mapping[str, Any], identity: ReplayIdentity) -> Optional[str]:
        try:
            self.owner.get_run(cassette["source_run_id"])
            events = self.owner.events(cassette["source_run_id"])
        except CompositionError:
            return "owner_source_run_missing"
        if self.event_digest(events) != identity.source_event_digest:
            return "source_event_digest_mismatch"
        return None

    def _load_and_validate_cassette(
        self,
        cassette_path: Path | str,
        identity: ReplayIdentity,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        path = Path(cassette_path).expanduser().resolve(strict=False)
        if not path.is_file():
            return None, "cassette_missing"
        try:
            if path.stat().st_size > MAX_CASSETTE_BYTES:
                return None, "cassette_too_large"
            raw = path.read_bytes()
            if _sha256(raw) != identity.cassette_identity.digest:  # type: ignore[union-attr]
                return None, "cassette_digest_mismatch"
            cassette = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, "cassette_invalid_json"
        if not isinstance(cassette, dict):
            return None, "cassette_not_object"
        if set(cassette) != set(CASSETTE_FIELDS):
            return None, "cassette_field_shape_invalid"
        if cassette["schema"] != CASSETTE_SCHEMA:
            return None, "cassette_schema_unknown"
        if cassette["sealed"] is not True:
            return None, "cassette_not_sealed"
        for field_name in ("cassette_id", "source_run_id", "source_event_digest", "environment_digest"):
            if not isinstance(cassette[field_name], str) or not cassette[field_name].strip():
                return None, f"cassette_{field_name}_invalid"
        if cassette["cassette_id"] != identity.cassette_identity.cassette_id:  # type: ignore[union-attr]
            return None, "cassette_id_mismatch"
        if cassette["source_event_digest"] != identity.source_event_digest:
            return None, "cassette_source_event_digest_mismatch"
        if cassette["environment_digest"] != identity.environment_digest:
            return None, "cassette_environment_digest_mismatch"
        if cassette["provider_identity"] != identity.provider_identity.to_dict():
            return None, "cassette_provider_identity_mismatch"
        if not isinstance(cassette["interactions"], list) or not isinstance(cassette["tool_results"], list):
            return None, "cassette_interactions_invalid"
        try:
            _reject_raw_credentials(cassette, "cassette")
            json.dumps(cassette["expected_semantic_result"], ensure_ascii=False)
        except (ValueError, TypeError):
            return None, "cassette_payload_invalid"
        return cassette, None


def _require_text(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _reject_raw_credentials(value: Any, field_name: str) -> None:
    sensitive_names = {"api_key", "apikey", "authorization", "cookie", "password", "secret", "token", "key"}
    safe_suffixes = ("_ref", "_reference", "_fingerprint", "_digest", "_id")

    def visit(current: Any, path: str) -> None:
        if isinstance(current, Mapping):
            for key, item in current.items():
                normalized = str(key).lower().replace("-", "_")
                parts = set(normalized.split("_"))
                if (normalized in sensitive_names or parts & sensitive_names) and not normalized.endswith(safe_suffixes):
                    raise ValueError(f"{field_name} contains raw credential field {path}.{key}")
                visit(item, f"{path}.{key}")
        elif isinstance(current, (list, tuple)):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")

    visit(value, field_name)


# External-execution counters that must stay at their zero value for every
# replay result. ``live_replay`` is fail-closed by design (it never starts a
# process, calls a Provider, or writes an effect); these are the signals that
# would betray accidental execution introduced by a future refactor.
ZERO_EXTERNAL_EXECUTION_EXPECTED: Dict[str, Any] = {
    "execution_performed": False,
    "provider_requests": 0,
    "tool_invocations": 0,
    "external_calls": 0,
    "side_effect_count": 0,
}


def assert_zero_external_execution(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Assertion-style, non-structural guard that accounts zero external execution.

    ``live_replay``'s "zero external execution" is currently *structural*: the
    method simply does not execute. That leaves no guard — a refactor that
    accidentally made it execute would pass silently. This function turns the
    invariant into an explicit, machine-readable assertion so a violation fails
    closed instead of slipping through.

    It is a logical assertion at the replay seam, not an OS-level sandbox; it
    complements (and does not replace) the host sandbox enforced at 1-8.

    Raises:
        ReplayError: if any external-execution counter indicates that execution
            took place. The message lists the tripped fields.

    Returns:
        A ``zero_external_execution`` accounting block (asserted flag, a snapshot
        of the five counters, and an empty ``violations`` list).
    """

    violations = [
        field
        for field, expected in ZERO_EXTERNAL_EXECUTION_EXPECTED.items()
        if result.get(field) != expected
    ]
    if violations:
        raise ReplayError(
            "live_replay zero-external-execution guard tripped: "
            + ", ".join(violations)
            + " indicate external execution occurred"
        )
    return {
        "asserted": True,
        "execution_performed": result.get("execution_performed", False),
        "provider_requests": result.get("provider_requests", 0),
        "tool_invocations": result.get("tool_invocations", 0),
        "external_calls": result.get("external_calls", 0),
        "side_effect_count": result.get("side_effect_count", 0),
        "violations": [],
    }


__all__ = [
    "CASSETTE_SCHEMA",
    "CassetteIdentity",
    "OwnerBackedReplayService",
    "REPLAY_MODES",
    "REPLAY_SERVICE_SCHEMA",
    "ReplayError",
    "ReplayIdentity",
    "ZERO_EXTERNAL_EXECUTION_EXPECTED",
    "assert_zero_external_execution",
]
