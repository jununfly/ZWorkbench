"""Configuration and static preflight for the first local run slice.

This module deliberately stops at the execution seam.  It does not start a
process, create a directory, read credentials, or make a network request.
Callers receive one small, serializable result that can be persisted by a
later orchestration module without copying the policy checks around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore

from .codex_adapter import CodexAppServerAdapter, CodexExecution
from .composition import CompositionOwner


LOCAL_READ_ONLY_MODE = "local_read_only"
READ_ONLY_SANDBOX = "read-only"
NO_APPROVAL_POLICY = "never"
REQUIRED_DISABLED_FEATURES = frozenset({"plugins", "apps"})

#: Provider identity names permitted to use a non-loopback endpoint. Populated
#: from the user's Codex-style config.toml; empty by default so any remote
#: endpoint stays fail-closed until an explicit profile is selected.
DEFAULT_AUTHORIZED_PROVIDERS: frozenset = frozenset()

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|private[_-]?key|secret|token)$",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,})")


@dataclass(frozen=True)
class LocalReadOnlyRunConfig:
    """The complete input contract for one case-local read-only run."""

    case_root: Path
    workspace: Path
    database: Path
    code_home: Path
    codex_executable: Path
    provider_identity: Mapping[str, Any]
    event_log: Optional[Path] = None
    mode: str = LOCAL_READ_ONLY_MODE
    sandbox: str = READ_ONLY_SANDBOX
    approval_policy: str = NO_APPROVAL_POLICY
    disabled_features: Tuple[str, ...] = ("plugins", "apps")
    authorized_providers: frozenset = DEFAULT_AUTHORIZED_PROVIDERS
    provider_profile: Optional[ProviderProfile] = None

    def __post_init__(self) -> None:
        for field_name in (
            "case_root",
            "workspace",
            "database",
            "code_home",
            "codex_executable",
        ):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)).expanduser().resolve(strict=False))
        if self.event_log is None:
            event_log = self.case_root / "events" / "codex.jsonl"
        else:
            event_log = Path(self.event_log).expanduser().resolve(strict=False)
        object.__setattr__(self, "event_log", event_log)
        object.__setattr__(self, "provider_identity", dict(self.provider_identity or {}))
        object.__setattr__(self, "disabled_features", tuple(self.disabled_features))
        object.__setattr__(self, "authorized_providers", frozenset(self.authorized_providers or ()))
        object.__setattr__(self, "provider_profile", self.provider_profile)


@dataclass(frozen=True)
class PreflightViolation:
    """A stable, non-sensitive reason why a configuration cannot run."""

    code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class PreflightResult:
    """The static admission result for :class:`LocalReadOnlyRunConfig`."""

    status: str
    mode: str
    config_digest: str
    checks: Mapping[str, bool]
    violations: Tuple[PreflightViolation, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe representation without config or secret values."""

        return {
            "status": self.status,
            "mode": self.mode,
            "config_digest": self.config_digest,
            "allowed": self.allowed,
            "checks": dict(self.checks),
            "violations": [violation.to_dict() for violation in self.violations],
        }


@dataclass(frozen=True)
class LocalReadOnlyRunResult:
    """The caller-facing outcome of one owner-backed local run."""

    status: str
    run_id: str
    preflight: PreflightResult
    execution: Optional[CodexExecution] = None
    state_digest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        execution = None
        if self.execution is not None:
            execution = {
                "run_id": self.execution.run_id,
                "thread_id": self.execution.thread_id,
                "turn_id": self.execution.turn_id,
                "status": self.execution.status,
                "text": self.execution.text,
                "provider_identity": dict(self.execution.provider_identity),
                "event_digest": self.execution.event_digest,
                "environment_digest": self.execution.environment_digest,
                "raw_event_count": self.execution.raw_event_count,
            }
        return {
            "status": self.status,
            "run_id": self.run_id,
            "preflight": self.preflight.to_dict(),
            "execution": execution,
            "state_digest": self.state_digest,
        }


AdapterFactory = Callable[[CompositionOwner, LocalReadOnlyRunConfig], Any]


@dataclass(frozen=True)
class ProviderProfile:
    """An explicitly configured remote/custom Provider, read from a Codex-style config.toml.

    Only non-secret, auditable fields are captured. Credential values (bearer
    tokens, api keys) are never read into this profile: the Codex app-server reads
    its own local config at runtime, or a credential is injected through the hidden
    ``extra_environment`` seam named by ``env_ref`` (never recorded in owner state
    or the config digest).
    """

    name: str
    model_provider: str
    model: str
    base_url: str
    wire_api: str = ""
    requires_openai_auth: bool = False
    env_ref: Optional[str] = None


class LocalReadOnlyRunOrchestrator:
    """Run the first local slice through one owner and one Codex adapter."""

    def __init__(
        self,
        config: LocalReadOnlyRunConfig,
        *,
        adapter_factory: Optional[AdapterFactory] = None,
    ) -> None:
        self.config = config
        self.adapter_factory = adapter_factory or _default_adapter_factory

    def run(self, run_id: str, prompt: str, *, timeout: float = 45.0) -> LocalReadOnlyRunResult:
        """Preflight and execute one local read-only run.

        A denied preflight does not open the owner database or call the adapter
        factory.  Once admitted, the adapter remains responsible for the run
        lifecycle and the owner remains responsible for durable state.
        """

        _require_text(run_id, "run_id")
        _require_text(prompt, "prompt")
        admission = preflight(self.config)
        if not admission.allowed:
            return LocalReadOnlyRunResult("denied", run_id, admission)

        with CompositionOwner(self.config.database) as owner:
            adapter = self.adapter_factory(owner, self.config)
            try:
                execution = adapter.execute(
                    run_id,
                    prompt,
                    task_type="local_read_only",
                    input_value={"prompt": prompt},
                    metadata={
                        "run_mode": self.config.mode,
                        "preflight": admission.to_dict(),
                    },
                    timeout=timeout,
                )
                return LocalReadOnlyRunResult(
                    "completed",
                    run_id,
                    admission,
                    execution,
                    owner.state_digest(),
                )
            finally:
                adapter.close()


def _default_adapter_factory(owner: CompositionOwner, config: LocalReadOnlyRunConfig) -> CodexAppServerAdapter:
    """Build the Codex adapter after preflight has admitted the case.

    When an explicit real Provider profile is selected, the adapter is wired to
    that provider: the profile's ``model_provider`` (e.g. ``custom``), an empty
    ``config_overrides`` so Codex honours its own ``[model_providers.<name>]``
    table, and an optional credential read from a local env var named by
    ``env_ref``. Otherwise the historical ollama default is used for backward
    compatibility (loopback, ``model_provider="ollama"``).
    """

    if config.provider_profile is None:
        return CodexAppServerAdapter(
            owner,
            config.codex_executable,
            config.code_home,
            config.workspace,
            model=str(config.provider_identity["model"]),
            model_provider="ollama",
            provider_identity=config.provider_identity,
            sandbox=config.sandbox,
            approval_policy=config.approval_policy,
            disabled_features=config.disabled_features,
            event_log=config.event_log,
        )

    profile = config.provider_profile
    extra_environment: Dict[str, str] = {}
    if profile.env_ref:
        credential = os.environ.get(profile.env_ref)
        if credential:
            extra_environment[profile.env_ref] = credential
    return CodexAppServerAdapter(
        owner,
        config.codex_executable,
        config.code_home,
        config.workspace,
        model=profile.model or str(config.provider_identity.get("model", "")),
        model_provider=profile.model_provider,
        provider_identity=config.provider_identity,
        sandbox=config.sandbox,
        approval_policy=config.approval_policy,
        disabled_features=config.disabled_features,
        config_overrides=(),
        extra_environment=extra_environment,
        event_log=config.event_log,
    )


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} must be a non-empty string".format(name))
    return value


def preflight(config: LocalReadOnlyRunConfig) -> PreflightResult:
    """Statically admit or deny a local read-only configuration.

    The function is intentionally side-effect free.  It only inspects local
    paths and values supplied by the caller.  A failed or ambiguous check is a
    denial with a stable violation code; it is never silently downgraded to a
    warning.
    """

    checks: Dict[str, bool] = {}
    violations: list[PreflightViolation] = []

    def check(name: str, passed: bool, code: str, message: str) -> None:
        checks[name] = passed
        if not passed:
            violations.append(PreflightViolation(code, message))

    root = config.case_root
    root_is_directory = root.is_dir()
    check(
        "case_root_directory",
        root_is_directory,
        "case_root_missing_or_not_directory",
        "case_root must already exist as a directory",
    )

    check(
        "mode_local_read_only",
        config.mode == LOCAL_READ_ONLY_MODE,
        "mode_not_local_read_only",
        "mode must be local_read_only",
    )
    check(
        "read_only_sandbox",
        config.sandbox == READ_ONLY_SANDBOX,
        "sandbox_not_read_only",
        "sandbox must be read-only",
    )
    check(
        "approval_policy_never",
        config.approval_policy == NO_APPROVAL_POLICY,
        "approval_policy_not_disabled",
        "the first slice must not enable an unreviewed approval path",
    )

    workspace_is_directory = config.workspace.is_dir()
    check(
        "workspace_directory",
        workspace_is_directory,
        "workspace_missing_or_not_directory",
        "workspace must already exist as a directory",
    )
    check(
        "workspace_inside_case",
        _is_inside(root, config.workspace),
        "workspace_outside_case_root",
        "workspace must be inside case_root",
    )
    check(
        "state_inside_case",
        _is_inside(root, config.database),
        "state_outside_case_root",
        "database must be inside case_root",
    )
    check(
        "code_home_inside_case",
        _is_inside(root, config.code_home),
        "code_home_outside_case_root",
        "CODEX_HOME must be inside case_root",
    )
    check(
        "event_log_inside_case",
        _is_inside(root, config.event_log),
        "event_log_outside_case_root",
        "event log must be inside case_root",
    )

    check(
        "codex_executable_file",
        config.codex_executable.is_file(),
        "codex_executable_missing",
        "Codex executable must already exist as a file",
    )
    check(
        "codex_executable_executable",
        config.codex_executable.is_file() and os.access(config.codex_executable, os.X_OK),
        "codex_executable_not_executable",
        "Codex executable must be executable",
    )

    provider_valid, provider_violations = _validate_provider_identity(config.provider_identity)
    check(
        "provider_identity_explicit",
        provider_valid[0],
        "provider_identity_missing_or_invalid",
        "provider identity must include provider, model and endpoint strings",
    )
    provider_name = config.provider_identity.get("provider")
    authorized_provider = bool(provider_name) and provider_name in config.authorized_providers
    check(
        "provider_loopback",
        provider_valid[1] or authorized_provider,
        "provider_not_loopback",
        "Provider endpoint must resolve to localhost/loopback, or name an "
        "explicitly authorized remote provider from config",
    )
    violations.extend(provider_violations)
    provider_json_safe = _is_json_serializable(config.provider_identity)
    check(
        "provider_identity_json_serializable",
        provider_json_safe,
        "provider_identity_not_json_serializable",
        "provider identity must be JSON serializable",
    )

    check(
        "plugins_and_apps_disabled",
        REQUIRED_DISABLED_FEATURES.issubset(set(config.disabled_features)),
        "required_features_not_disabled",
        "plugins and apps must both be disabled in the first slice",
    )
    check(
        "no_credentials_in_config",
        not _contains_credentials(config.provider_identity),
        "provider_credentials_present",
        "credential values must be injected outside this config and never recorded",
    )

    digest = _config_digest(config)
    return PreflightResult(
        status="pass" if not violations else "deny",
        mode=config.mode,
        config_digest=digest,
        checks=checks,
        violations=tuple(violations),
    )


def _validate_provider_identity(identity: Mapping[str, Any]) -> Tuple[Tuple[bool, bool], list[PreflightViolation]]:
    violations: list[PreflightViolation] = []
    required = (identity.get("provider"), identity.get("model"), identity.get("endpoint"))
    explicit = all(isinstance(value, str) and bool(value.strip()) for value in required)
    if not explicit:
        return (False, False), violations

    endpoint = str(identity["endpoint"])
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        parsed.port  # Force malformed port values through the same safe path.
    except ValueError:
        violations.append(
            PreflightViolation(
                "provider_endpoint_invalid",
                "Provider endpoint is not a valid URL",
            )
        )
        return (True, False), violations
    if parsed.scheme.lower() not in {"http", "https"}:
        violations.append(
            PreflightViolation(
                "provider_endpoint_scheme_not_supported",
                "Provider endpoint must use http or https",
            )
        )
        return (True, False), violations
    if parsed.username or parsed.password:
        violations.append(
            PreflightViolation("provider_endpoint_embeds_credentials", "Provider endpoint must not contain credentials")
        )
        return (True, False), violations
    loopback = _is_loopback_host(host) if parsed.scheme and host else False
    return (True, loopback), violations


def _is_loopback_host(host: Optional[str]) -> bool:
    if not host:
        return False
    if host.lower() in {"localhost", "localhost."}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


def _contains_credentials(value: Any, key: str = "") -> bool:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            name = str(child_key)
            if _SENSITIVE_KEY.search(name) and not name.lower().endswith(("_ref", "-ref")):
                return True
            if _contains_credentials(child_value, name):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_credentials(item, key) for item in value)
    return isinstance(value, str) and bool(_SECRET_VALUE.search(value))


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def _redact(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key) and not key.lower().endswith(("_ref", "-ref")):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(child_key): _redact(child_value, str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, key) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return "<non-json:{0}>".format(type(value).__name__)


def _config_digest(config: LocalReadOnlyRunConfig) -> str:
    payload = {
        "case_root": str(config.case_root),
        "workspace": str(config.workspace),
        "database": str(config.database),
        "code_home": str(config.code_home),
        "codex_executable": str(config.codex_executable),
        "event_log": str(config.event_log),
        "provider_identity": _redact(config.provider_identity),
        "mode": config.mode,
        "sandbox": config.sandbox,
        "approval_policy": config.approval_policy,
        "disabled_features": list(config.disabled_features),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_provider_profiles(config_path: Path) -> Dict[str, ProviderProfile]:
    """Read authorized remote/custom providers from a Codex-style config.toml.

    Supports both the Codex-native ``[model_providers.<name>]`` tables and the
    project ``[provider.<name>]`` tables. Returns a mapping of provider identity
    name -> :class:`ProviderProfile`. Credential *values* are intentionally
    never returned: a Codex bearer token sitting in the user's config is the
    local credential path read by the app-server itself, and an ``env`` field is
    captured only as the env var *name* (``env_ref``) for hidden injection.
    """

    path = Path(config_path).expanduser().resolve(strict=True)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    top_level_model = data.get("model") if isinstance(data.get("model"), str) else ""
    profiles: Dict[str, ProviderProfile] = {}
    for table_key in ("model_providers", "provider"):
        section = data.get(table_key)
        if not isinstance(section, Mapping):
            continue
        for name, raw in section.items():
            if not isinstance(raw, Mapping):
                continue
            profiles[str(name)] = ProviderProfile(
                name=str(name),
                model_provider=str(name),
                model=str(raw.get("model") or top_level_model or ""),
                base_url=str(raw.get("base_url") or ""),
                wire_api=str(raw.get("wire_api") or ""),
                requires_openai_auth=bool(raw.get("requires_openai_auth", False)),
                env_ref=str(raw["env"]) if isinstance(raw.get("env"), str) else None,
            )
    return profiles
