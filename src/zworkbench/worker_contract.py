"""Versioned, fail-closed wire contract for the DSH-to-Codex Worker seam.

This module describes messages; it does not start a process, call a Provider,
invoke a tool, or write CompositionOwner state.  The latter responsibilities
belong to the bridge and the owner respectively.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


WORKER_CONTRACT_SCHEMA = "zworkbench.worker.v1"
UNKNOWN = "unknown"

KNOWN_MESSAGE_TYPES = frozenset(
    {
        "handshake.request",
        "handshake.response",
        "capability.request",
        "capability.response",
        "event",
        "result",
        "cancel",
        "error",
    }
)
REPLAY_MODES = frozenset({"normal", "recorded_view", "simulated_replay", "live_replay"})


class WorkerContractError(ValueError):
    """Base class for malformed or unsafe Worker contract data."""

    def __init__(self, message: str, *, code: str, safe_stop: bool = False):
        super().__init__(message)
        self.code = code
        self.safe_stop = safe_stop


class SafeStopRequired(WorkerContractError):
    """The bridge must stop instead of interpreting this message."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message, code=code, safe_stop=True)


class CompletionBlocked(WorkerContractError):
    """A Worker result cannot be treated as a complete owner-backed run."""

    def __init__(self, message: str, *, missing: Iterable[str] = ()):
        super().__init__(message, code="completion_blocked", safe_stop=False)
        self.missing = tuple(missing)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerContractError(
            f"{field_name} must be a non-empty string",
            code="invalid_text",
        )
    return value


def _json_value(value: Any, field_name: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise WorkerContractError(
            f"{field_name} must be JSON serializable",
            code="non_json_value",
        ) from exc
    return value


def _mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkerContractError(f"{field_name} must be an object", code="invalid_object")
    return {str(key): item for key, item in value.items()}


def _reject_secrets(value: Mapping[str, Any], field_name: str) -> None:
    sensitive_names = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "key",
    }
    safe_identity_suffixes = ("_ref", "_reference", "_fingerprint", "_digest", "_id")

    def is_raw_credential_name(name: str) -> bool:
        if name.endswith(safe_identity_suffixes):
            return False
        parts = set(name.split("_"))
        return name in sensitive_names or bool(parts & sensitive_names)

    def visit(current: Any, path: str) -> None:
        if isinstance(current, Mapping):
            for key, item in current.items():
                normalized = str(key).lower().replace("-", "_")
                if is_raw_credential_name(normalized):
                    raise WorkerContractError(
                        f"{field_name} cannot contain raw credential field {path}.{key}",
                        code="credential_value_forbidden",
                    )
                visit(item, f"{path}.{key}")
        elif isinstance(current, (list, tuple)):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")

    visit(value, field_name)


@dataclass(frozen=True)
class IdentityChain:
    """Correlation chain shared by parent Run, DSH, Worker and Codex."""

    parent_run_id: str = UNKNOWN
    child_run_id: str = UNKNOWN
    attempt_id: str = UNKNOWN
    dsh_session_id: str = UNKNOWN
    dsh_turn_id: str = UNKNOWN
    worker_run_id: str = UNKNOWN
    codex_thread_id: str = UNKNOWN
    codex_turn_id: str = UNKNOWN
    event_id: str = UNKNOWN
    artifact_id: str = UNKNOWN

    FIELD_NAMES = (
        "parent_run_id",
        "child_run_id",
        "attempt_id",
        "dsh_session_id",
        "dsh_turn_id",
        "worker_run_id",
        "codex_thread_id",
        "codex_turn_id",
        "event_id",
        "artifact_id",
    )

    def __post_init__(self) -> None:
        for field_name in self.FIELD_NAMES:
            _text(getattr(self, field_name), f"identity.{field_name}")

    def to_dict(self) -> Dict[str, str]:
        return {field_name: getattr(self, field_name) for field_name in self.FIELD_NAMES}

    @classmethod
    def from_dict(cls, value: Any) -> "IdentityChain":
        data = _mapping(value, "identity")
        unknown = set(data) - set(cls.FIELD_NAMES)
        if unknown:
            raise WorkerContractError(
                f"identity contains unknown fields: {sorted(unknown)}",
                code="unknown_identity_field",
            )
        missing = set(cls.FIELD_NAMES) - set(data)
        if missing:
            raise WorkerContractError(
                f"identity must explicitly record unknown fields: {sorted(missing)}",
                code="identity_shape_incomplete",
            )
        return cls(**{field_name: data[field_name] for field_name in cls.FIELD_NAMES})

    def missing_fields(self) -> Tuple[str, ...]:
        return tuple(
            field_name
            for field_name in self.FIELD_NAMES
            if getattr(self, field_name) == UNKNOWN
        )

    def is_complete(self) -> bool:
        return not self.missing_fields()


@dataclass(frozen=True)
class ProviderIdentity:
    """Non-secret identity of the selected Provider route."""

    provider: str
    model: str
    endpoint: str
    transport: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("provider", "model", "endpoint", "transport"):
            _text(getattr(self, field_name), f"provider_identity.{field_name}")
        metadata = _mapping(self.metadata, "provider_identity.metadata")
        _reject_secrets(metadata, "provider_identity.metadata")
        _json_value(metadata, "provider_identity.metadata")
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "transport": self.transport,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderIdentity":
        data = _mapping(value, "provider_identity")
        required = ("provider", "model", "endpoint", "transport")
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise WorkerContractError(
                f"provider identity is missing fields: {missing}",
                code="provider_identity_incomplete",
            )
        unknown = set(data) - set(required) - {"metadata"}
        if unknown:
            raise WorkerContractError(
                f"provider identity contains unknown fields: {sorted(unknown)}",
                code="unknown_provider_identity_field",
            )
        return cls(
            provider=data["provider"],
            model=data["model"],
            endpoint=data["endpoint"],
            transport=data["transport"],
            metadata=data.get("metadata", {}),
        )

    def is_complete(self) -> bool:
        return all(
            value != UNKNOWN
            for value in (self.provider, self.model, self.endpoint, self.transport)
        )


@dataclass(frozen=True)
class ComponentIdentity:
    """Pinned source/version/digest identity for a Worker component."""

    name: str
    version: str
    digest: str
    source: str

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "digest", "source"):
            _text(getattr(self, field_name), f"component.{field_name}")

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "digest": self.digest,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Any, field_name: str = "component") -> "ComponentIdentity":
        data = _mapping(value, field_name)
        required = ("name", "version", "digest", "source")
        missing = [key for key in required if key not in data]
        unknown = set(data) - set(required)
        if missing or unknown:
            raise WorkerContractError(
                f"{field_name} shape invalid; missing={missing}, unknown={sorted(unknown)}",
                code="component_identity_shape_invalid",
            )
        return cls(**{key: data[key] for key in required})

    def missing_fields(self) -> Tuple[str, ...]:
        return tuple(
            field_name
            for field_name in ("name", "version", "digest", "source")
            if getattr(self, field_name) == UNKNOWN
        )

    def is_complete(self) -> bool:
        return not self.missing_fields()


@dataclass(frozen=True)
class CapabilityRequest:
    """A request routed through the Host Capability Facade."""

    request_id: str
    capability: str
    operation: str
    resource: str
    effect_class: str
    declared_permissions: Tuple[str, ...]
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "capability",
            "operation",
            "resource",
            "effect_class",
        ):
            _text(getattr(self, field_name), f"capability_request.{field_name}")
        permissions = tuple(_text(item, "capability_request.declared_permissions[]") for item in self.declared_permissions)
        if len(set(permissions)) != len(permissions):
            raise WorkerContractError(
                "declared permissions must not repeat",
                code="duplicate_permission",
            )
        arguments = _mapping(self.arguments, "capability_request.arguments")
        _json_value(arguments, "capability_request.arguments")
        _reject_secrets(arguments, "capability_request.arguments")
        object.__setattr__(self, "declared_permissions", permissions)
        object.__setattr__(self, "arguments", arguments)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "capability": self.capability,
            "operation": self.operation,
            "resource": self.resource,
            "effect_class": self.effect_class,
            "declared_permissions": list(self.declared_permissions),
            "arguments": dict(self.arguments),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CapabilityRequest":
        data = _mapping(value, "capability_request")
        required = (
            "request_id",
            "capability",
            "operation",
            "resource",
            "effect_class",
            "declared_permissions",
            "arguments",
        )
        missing = [key for key in required if key not in data]
        unknown = set(data) - set(required)
        if missing or unknown:
            raise WorkerContractError(
                f"capability request shape invalid; missing={missing}, unknown={sorted(unknown)}",
                code="capability_request_shape_invalid",
            )
        if not isinstance(data["declared_permissions"], list):
            raise WorkerContractError(
                "declared_permissions must be an array",
                code="invalid_permissions",
            )
        return cls(
            request_id=data["request_id"],
            capability=data["capability"],
            operation=data["operation"],
            resource=data["resource"],
            effect_class=data["effect_class"],
            declared_permissions=tuple(data["declared_permissions"]),
            arguments=data["arguments"],
        )


WIRE_FIELDS = frozenset(
    {
        "schema",
        "message_type",
        "identity",
        "provider_identity",
        "replay_mode",
        "policy_digest",
        "environment_digest",
        "workspace_digest",
        "worker_artifact_identity",
        "worker_schema_identity",
        "capability_request",
        "payload",
    }
)


@dataclass(frozen=True)
class WorkerEnvelope:
    """One strict JSON message crossing the external Worker boundary."""

    message_type: str
    identity: IdentityChain
    provider_identity: ProviderIdentity
    replay_mode: str
    policy_digest: str
    environment_digest: str
    workspace_digest: str
    worker_artifact_identity: ComponentIdentity
    worker_schema_identity: ComponentIdentity
    capability_request: Optional[CapabilityRequest] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema: str = WORKER_CONTRACT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != WORKER_CONTRACT_SCHEMA:
            raise SafeStopRequired(
                f"unsupported Worker contract schema: {self.schema!r}",
                code="unsupported_schema",
            )
        if self.message_type not in KNOWN_MESSAGE_TYPES:
            raise SafeStopRequired(
                f"unknown Worker wire message: {self.message_type!r}",
                code="unknown_wire_message",
            )
        if self.replay_mode not in REPLAY_MODES:
            raise WorkerContractError(
                f"unknown replay mode: {self.replay_mode!r}",
                code="unknown_replay_mode",
            )
        for field_name in ("policy_digest", "environment_digest", "workspace_digest"):
            _text(getattr(self, field_name), field_name)
        if not isinstance(self.identity, IdentityChain):
            raise WorkerContractError("identity must be IdentityChain", code="invalid_identity")
        if not isinstance(self.provider_identity, ProviderIdentity):
            raise WorkerContractError(
                "provider_identity must be ProviderIdentity",
                code="invalid_provider_identity",
            )
        if not isinstance(self.worker_artifact_identity, ComponentIdentity):
            raise WorkerContractError(
                "worker_artifact_identity must be ComponentIdentity",
                code="invalid_worker_artifact_identity",
            )
        if not isinstance(self.worker_schema_identity, ComponentIdentity):
            raise WorkerContractError(
                "worker_schema_identity must be ComponentIdentity",
                code="invalid_worker_schema_identity",
            )
        payload = _mapping(self.payload, "payload")
        _json_value(payload, "payload")
        _reject_secrets(payload, "payload")
        if self.message_type == "capability.request" and self.capability_request is None:
            raise WorkerContractError(
                "capability.request requires capability_request",
                code="capability_request_required",
            )
        if self.message_type != "capability.request" and self.capability_request is not None:
            raise WorkerContractError(
                "capability_request is only valid for capability.request",
                code="capability_request_unexpected",
            )
        object.__setattr__(self, "payload", payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "message_type": self.message_type,
            "identity": self.identity.to_dict(),
            "provider_identity": self.provider_identity.to_dict(),
            "replay_mode": self.replay_mode,
            "policy_digest": self.policy_digest,
            "environment_digest": self.environment_digest,
            "workspace_digest": self.workspace_digest,
            "worker_artifact_identity": self.worker_artifact_identity.to_dict(),
            "worker_schema_identity": self.worker_schema_identity.to_dict(),
            "capability_request": (
                self.capability_request.to_dict() if self.capability_request is not None else None
            ),
            "payload": dict(self.payload),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Any) -> "WorkerEnvelope":
        data = _mapping(value, "Worker envelope")
        unknown = set(data) - set(WIRE_FIELDS)
        missing = set(WIRE_FIELDS) - set(data)
        if unknown:
            raise SafeStopRequired(
                f"Worker envelope contains unknown wire fields: {sorted(unknown)}",
                code="unknown_wire_field",
            )
        if missing:
            raise WorkerContractError(
                f"Worker envelope is missing fields: {sorted(missing)}",
                code="envelope_shape_incomplete",
            )
        capability_value = data["capability_request"]
        return cls(
            schema=data["schema"],
            message_type=data["message_type"],
            identity=IdentityChain.from_dict(data["identity"]),
            provider_identity=ProviderIdentity.from_dict(data["provider_identity"]),
            replay_mode=data["replay_mode"],
            policy_digest=data["policy_digest"],
            environment_digest=data["environment_digest"],
            workspace_digest=data["workspace_digest"],
            worker_artifact_identity=ComponentIdentity.from_dict(
                data["worker_artifact_identity"], "worker_artifact_identity"
            ),
            worker_schema_identity=ComponentIdentity.from_dict(
                data["worker_schema_identity"], "worker_schema_identity"
            ),
            capability_request=(
                None
                if capability_value is None
                else CapabilityRequest.from_dict(capability_value)
            ),
            payload=data["payload"],
        )

    @classmethod
    def from_json(cls, value: str) -> "WorkerEnvelope":
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise WorkerContractError("Worker envelope is not valid JSON", code="invalid_json") from exc
        return cls.from_dict(decoded)

    def missing_completion_fields(self) -> Tuple[str, ...]:
        missing = list(self.identity.missing_fields())
        for prefix, component in (
            ("worker_artifact_identity", self.worker_artifact_identity),
            ("worker_schema_identity", self.worker_schema_identity),
        ):
            missing.extend(f"{prefix}.{field_name}" for field_name in component.missing_fields())
        if not self.provider_identity.is_complete():
            missing.extend(
                f"provider_identity.{field_name}"
                for field_name in ("provider", "model", "endpoint", "transport")
                if getattr(self.provider_identity, field_name) == UNKNOWN
            )
        for field_name, value in (
            ("policy_digest", self.policy_digest),
            ("environment_digest", self.environment_digest),
            ("workspace_digest", self.workspace_digest),
        ):
            if value == UNKNOWN:
                missing.append(field_name)
        return tuple(missing)

    def validate_worker_completion(self) -> None:
        """Validate a Worker result without completing the parent Run."""

        if self.message_type != "result":
            raise CompletionBlocked(
                "only a result message can complete a Worker contract",
                missing=("message_type=result",),
            )
        if self.payload.get("status") != "completed":
            raise CompletionBlocked(
                "Worker result is not explicitly completed",
                missing=("payload.status=completed",),
            )
        missing = self.missing_completion_fields()
        if missing:
            raise CompletionBlocked(
                "Worker completion has incomplete identity or provenance",
                missing=missing,
            )


DEFAULT_CAPABILITY_EFFECTS = {
    "workspace.read": ("none", frozenset({"workspace.read"})),
    "workspace.list": ("none", frozenset({"workspace.read"})),
    "test.run": ("local_process", frozenset({"process.local_read"})),
    "artifact.emit": ("owner_record", frozenset({"owner.artifact_write"})),
    "provider.infer": ("provider_request", frozenset({"provider.infer"})),
}
KNOWN_EFFECT_CLASSES = frozenset(
    {
        "none",
        "local_process",
        "owner_record",
        "provider_request",
        "isolated_workspace_write",
        "external_write",
    }
)


@dataclass(frozen=True)
class CapabilityDecision:
    request_id: str
    decision: str
    reason: str
    safe_stop: bool = False


class CapabilityFacade:
    """Authorize known requests; never execute them or grant unknown ones."""

    def __init__(
        self,
        capability_effects: Optional[Mapping[str, Tuple[str, Iterable[str]]]] = None,
    ) -> None:
        source = capability_effects or DEFAULT_CAPABILITY_EFFECTS
        self._capability_effects = {
            capability: (effect, frozenset(permissions))
            for capability, (effect, permissions) in source.items()
        }

    def authorize(self, envelope: WorkerEnvelope) -> CapabilityDecision:
        if envelope.message_type != "capability.request" or envelope.capability_request is None:
            raise WorkerContractError(
                "CapabilityFacade requires capability.request",
                code="capability_message_required",
            )
        request = envelope.capability_request
        if envelope.replay_mode != "normal":
            raise SafeStopRequired(
                "replay mode cannot start a Worker, Provider or tool capability",
                code="replay_execution_forbidden",
            )
        if not envelope.identity.is_complete():
            raise SafeStopRequired(
                "capability request identity is incomplete",
                code="capability_identity_incomplete",
            )
        if request.capability not in self._capability_effects:
            raise SafeStopRequired(
                f"unknown capability: {request.capability!r}",
                code="unknown_capability",
            )
        if request.effect_class not in KNOWN_EFFECT_CLASSES:
            raise SafeStopRequired(
                f"unknown effect class: {request.effect_class!r}",
                code="unknown_effect",
            )
        expected_effect, expected_permissions = self._capability_effects[request.capability]
        if request.effect_class != expected_effect:
            raise SafeStopRequired(
                f"capability {request.capability!r} declared effect {request.effect_class!r}; "
                f"expected {expected_effect!r}",
                code="effect_mismatch",
            )
        if frozenset(request.declared_permissions) != expected_permissions:
            raise SafeStopRequired(
                f"capability {request.capability!r} declared permissions do not match policy",
                code="permission_mismatch",
            )
        return CapabilityDecision(
            request_id=request.request_id,
            decision="allow",
            reason="allowlisted capability and declared permission",
        )


__all__ = [
    "KNOWN_EFFECT_CLASSES",
    "KNOWN_MESSAGE_TYPES",
    "REPLAY_MODES",
    "WORKER_CONTRACT_SCHEMA",
    "UNKNOWN",
    "CapabilityDecision",
    "CapabilityFacade",
    "CapabilityRequest",
    "ComponentIdentity",
    "CompletionBlocked",
    "IdentityChain",
    "ProviderIdentity",
    "SafeStopRequired",
    "WorkerContractError",
    "WorkerEnvelope",
]
