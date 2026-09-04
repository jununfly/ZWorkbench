"""Deterministic owner-backed Provider failover fixture.

This fixture keeps route selection in memory but records every attempt,
cooldown update, fallback decision, degradation reason and safe-stop through
CompositionOwner.  It is intentionally not a production Provider router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping


SCHEMA = "zworkbench-w8-remote-provider-failover-fixture/v1"


class ProviderFailure(RuntimeError):
    """A deterministic Provider failure injected by the fixture."""

    def __init__(self, code: str, **details: Any):
        super().__init__(code)
        self.code = code
        self.details = dict(details)


@dataclass(frozen=True)
class ProviderRoute:
    provider_id: str
    model: str
    endpoint: str

    def identity(self) -> Dict[str, str]:
        return {
            "provider": self.provider_id,
            "model": self.model,
            "endpoint": self.endpoint,
            "transport": "loopback-only",
        }


class OwnerBackedProviderRouter:
    """Route bounded attempts while keeping the durable ledger in the owner."""

    def __init__(self, owner: Any, routes: Iterable[ProviderRoute], cooldown_ticks: int = 5):
        self.owner = owner
        self.routes = tuple(routes)
        if not self.routes:
            raise ValueError("at least one Provider route is required")
        if cooldown_ticks <= 0:
            raise ValueError("cooldown_ticks must be positive")
        self.cooldown_ticks = cooldown_ticks
        self._cooldown_until = self._load_cooldowns()

    def _load_cooldowns(self) -> Dict[str, int]:
        cooldowns: Dict[str, int] = {}
        for event in self.owner.events():
            if event.get("type") != "provider.cooldown.updated":
                continue
            payload = event.get("payload") or {}
            provider_id = payload.get("provider_id")
            cooldown_until = payload.get("cooldown_until")
            if isinstance(provider_id, str) and isinstance(cooldown_until, int):
                cooldowns[provider_id] = max(cooldowns.get(provider_id, 0), cooldown_until)
        return cooldowns

    def _record(self, run_id: str, event_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        self.owner.record_event(run_id, event_type, {"schema": SCHEMA, **dict(payload)}, event_id)

    def _available(self, logical_time: int, attempted: set[str] | None = None) -> list[ProviderRoute]:
        attempted = attempted or set()
        return [
            route
            for route in self.routes
            if route.provider_id not in attempted
            and self._cooldown_until.get(route.provider_id, 0) <= logical_time
        ]

    def route(
        self,
        run_id: str,
        request_id: str,
        logical_time: int,
        dispatch: Callable[[ProviderRoute], Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Execute one bounded route sequence and return an owner-visible result."""

        if not isinstance(logical_time, int) or logical_time < 0:
            raise ValueError("logical_time must be a non-negative integer")
        available = self._available(logical_time)
        if not available:
            decision = {
                "request_id": request_id,
                "failure_code": "all_routes_cooling_down",
                "from_provider": None,
                "to_provider": None,
                "reason": "all_routes_cooling_down",
                "degradation": "safe_stop",
                "selected_provider": None,
                "cooldown_snapshot": dict(self._cooldown_until),
            }
            self._record(run_id, f"{request_id}:decision:all-cooled", "provider.failover.decision", decision)
            self.owner.record_result(run_id, "provider.failover", decision, f"{request_id}:decision")
            self.owner.safe_stop_run(run_id, "provider_all_routes_cooled")
            return {"status": "safe_stopped", "attempts": [], "decision": decision}

        attempts: list[Dict[str, Any]] = []
        attempted: set[str] = set()
        for attempt_number, route in enumerate(available, start=1):
            attempted.add(route.provider_id)
            identity = route.identity()
            started = {
                "request_id": request_id,
                "attempt": attempt_number,
                **identity,
                "status": "started",
            }
            self._record(run_id, f"{request_id}:attempt:{attempt_number}:started", "provider.attempt", started)
            try:
                semantic = dict(dispatch(route))
            except ProviderFailure as failure:
                cooldown_before = self._cooldown_until.get(route.provider_id, 0)
                cooldown_after = max(cooldown_before, logical_time + self.cooldown_ticks)
                self._cooldown_until[route.provider_id] = cooldown_after
                failed = {
                    "request_id": request_id,
                    "attempt": attempt_number,
                    **identity,
                    "status": "failed",
                    "failure_code": failure.code,
                    **failure.details,
                }
                attempts.append(failed)
                self._record(run_id, f"{request_id}:attempt:{attempt_number}:failed", "provider.attempt", failed)
                self._record(
                    run_id,
                    f"{request_id}:cooldown:{route.provider_id}",
                    "provider.cooldown.updated",
                    {
                        "request_id": request_id,
                        "provider_id": route.provider_id,
                        "cooldown_before": cooldown_before,
                        "cooldown_until": cooldown_after,
                        "failure_code": failure.code,
                        **failure.details,
                    },
                )
                fallback = self._available(logical_time, attempted)
                decision = {
                    "request_id": request_id,
                    "attempt": attempt_number,
                    "failure_code": failure.code,
                    "from_provider": route.provider_id,
                    "to_provider": fallback[0].provider_id if fallback else None,
                    "reason": failure.code,
                    "degradation": "fallback" if fallback else "safe_stop",
                    "cooldown_before": cooldown_before,
                    "cooldown_after": cooldown_after,
                    **failure.details,
                }
                self._record(run_id, f"{request_id}:decision:{attempt_number}", "provider.failover.decision", decision)
                self.owner.record_result(run_id, "provider.failover", decision, f"{request_id}:decision:{attempt_number}")
                if not fallback:
                    self.owner.safe_stop_run(run_id, "provider_all_routes_cooled")
                    return {"status": "safe_stopped", "attempts": attempts, "decision": decision}
                continue

            succeeded = {
                "request_id": request_id,
                "attempt": attempt_number,
                **identity,
                "status": "succeeded",
            }
            attempts.append(succeeded)
            self._record(run_id, f"{request_id}:attempt:{attempt_number}:succeeded", "provider.attempt", succeeded)
            result = {
                "status": "completed",
                "provider": route.provider_id,
                "model": route.model,
                "endpoint": route.endpoint,
                "semantic": semantic,
                "attempts": attempts,
            }
            self.owner.record_result(run_id, "provider.route", result, f"{request_id}:route")
            self.owner.complete_run(run_id, result)
            return result

        raise AssertionError("bounded route sequence exhausted without a terminal result")
