"""Host Capability Facade — the only runtime seam for Provider access.

Product code (the Control Plane / ``LocalReadOnlyRunOrchestrator``) must obtain
a Provider adapter through this seam and never import or construct
``CodexAppServerAdapter`` directly.  This enforces the R3 architecture negative
constraint ("Provider 接入必须经 Host Capability Facade，产品代码不得直连";
``docs/prds/r3-real-usability-roadmap.md`` 架构约束第 1 条) and keeps a single,
durable-owner-independent boundary that the future multi-Provider (H6-full) and
DSH runtime paths must route through.

This facade is deliberately narrow and distinct from
``worker_contract.CapabilityFacade``:

* ``worker_contract.CapabilityFacade`` is a *policy gate* for the DSH→Worker wire
  seam: it authorizes known capability requests and never executes them.
* ``HostCapabilityFacade`` is a *runtime acquisition seam* for the Control Plane
  → Provider boundary: it produces the concrete adapter and nothing else.

Tests and fixtures may still construct ``CodexAppServerAdapter`` directly; the
constraint only forbids **product orchestration code** from doing so.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Mapping

from .codex_adapter import CodexAppServerAdapter
from .composition import CompositionOwner


if TYPE_CHECKING:  # pragma: no cover - import only for static type checking
    from .local_run import LocalReadOnlyRunConfig


FACADE_SCHEMA = "zworkbench.host-capability-facade/v1"


class HostCapabilityFacade:
    """Produce the configured Provider adapter behind one controlled seam.

    The facade is a static factory: it holds no session state and never writes
    CompositionOwner or runs an effect itself.  It centralizes the single place
    that knows how to turn a run config into a concrete Provider adapter, so the
    Control Plane cannot bypass it by importing the adapter class.
    """

    SCHEMA = FACADE_SCHEMA

    @staticmethod
    def acquire_provider(
        owner: CompositionOwner,
        config: "LocalReadOnlyRunConfig",
    ) -> CodexAppServerAdapter:
        """Build the Codex adapter for one admitted, case-local run.

        When an explicit real Provider profile is selected, the adapter is wired
        to that provider: the profile's ``model_provider`` (e.g. ``custom``), an
        empty ``config_overrides`` so Codex honours its own
        ``[model_providers.<name>]`` table, and an optional credential read from
        a local env var named by ``env_ref``.  Otherwise the historical ollama
        default is used for backward compatibility (loopback,
        ``model_provider="ollama"``).
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
        extra_environment: Mapping[str, str] = {}
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


__all__ = ["FACADE_SCHEMA", "HostCapabilityFacade"]
