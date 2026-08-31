"""Deterministic adapters for the W8 local read-only fixture contract.

These adapters deliberately do not start Codex, call a Provider, read a
credential, or execute a tool.  They exercise the product orchestration seam
against the real :class:`CompositionOwner` so the runner can distinguish a
completed run from an expected fail-closed boundary.
"""

from __future__ import annotations

from typing import Any, Mapping

from zworkbench import CodexExecution, CompositionOwner, LocalReadOnlyRunConfig


FIXTURE_ADAPTER_SCHEMA = "zworkbench-w8-local-read-only-fixture-adapter/v1"
FIXTURE_THREAD_ID = "fixture-thread-0001"
FIXTURE_TURN_ID = "fixture-turn-0001"
FIXTURE_EVENT_DIGEST = "fixture-event-digest-v1"
FIXTURE_ENVIRONMENT_DIGEST = "fixture-environment-digest-v1"
FIXTURE_TEXT = "fixture-ok"


class FixtureUnknownBoundary(RuntimeError):
    """An unsupported request was intentionally stopped at the adapter seam."""

    def __init__(self, request_kind: str) -> None:
        self.request_kind = request_kind
        super().__init__("unsupported fixture request: {0}".format(request_kind))


class _FixtureAdapter:
    """Shared lifecycle and close behavior for deterministic fixture adapters."""

    def __init__(self, owner: CompositionOwner, config: LocalReadOnlyRunConfig) -> None:
        self.owner = owner
        self.config = config
        self.closed = False
        self.execute_calls = 0

    def close(self) -> None:
        self.closed = True

    def _run_metadata(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(metadata)
        result.update(
            {
                "adapter_schema": FIXTURE_ADAPTER_SCHEMA,
                "fixture_version": "w8-local-read-only/v1",
            }
        )
        return result

    def _start_run(
        self,
        run_id: str,
        prompt: str,
        task_type: str,
        input_value: Any,
        metadata: Mapping[str, Any],
    ) -> None:
        self.owner.create_run(
            run_id,
            task_type,
            input_value if input_value is not None else {"prompt": prompt},
            self._run_metadata(metadata),
        )
        self.owner.start_run(run_id)


class FixtureSuccessAdapter(_FixtureAdapter):
    """Complete one deterministic owner-backed read-only run."""

    def execute(
        self,
        run_id: str,
        prompt: str,
        *,
        task_type: str = "local_read_only",
        input_value: Any = None,
        metadata: Mapping[str, Any] | None = None,
        timeout: float = 45.0,
    ) -> CodexExecution:
        del timeout
        self.execute_calls += 1
        self._start_run(run_id, prompt, task_type, input_value, metadata or {})
        provider_identity = dict(self.config.provider_identity)
        self.owner.record_result(
            run_id,
            "adapter.fixture.initialized",
            {"schema": FIXTURE_ADAPTER_SCHEMA, "network_requests": 0},
            "fixture-adapter",
        )
        self.owner.record_result(
            run_id,
            "adapter.fixture.thread",
            {"thread_id": FIXTURE_THREAD_ID},
            FIXTURE_THREAD_ID,
        )
        self.owner.record_result(
            run_id,
            "adapter.fixture.turn",
            {"thread_id": FIXTURE_THREAD_ID, "turn_id": FIXTURE_TURN_ID},
            FIXTURE_TURN_ID,
        )
        self.owner.record_replay_metadata(
            run_id,
            "{0}:recorded-view".format(run_id),
            "recorded_view",
            FIXTURE_EVENT_DIGEST,
            FIXTURE_ENVIRONMENT_DIGEST,
            provider_identity,
            {"adapter_schema": FIXTURE_ADAPTER_SCHEMA},
        )
        self.owner.complete_run(
            run_id,
            {
                "status": "completed",
                "text": FIXTURE_TEXT,
                "thread_id": FIXTURE_THREAD_ID,
                "turn_id": FIXTURE_TURN_ID,
                "provider_identity": provider_identity,
                "event_digest": FIXTURE_EVENT_DIGEST,
                "environment_digest": FIXTURE_ENVIRONMENT_DIGEST,
                "external_side_effects": 0,
            },
        )
        return CodexExecution(
            run_id,
            FIXTURE_THREAD_ID,
            FIXTURE_TURN_ID,
            "completed",
            FIXTURE_TEXT,
            provider_identity,
            FIXTURE_EVENT_DIGEST,
            FIXTURE_ENVIRONMENT_DIGEST,
            3,
        )


class FixtureUnknownBoundaryAdapter(_FixtureAdapter):
    """Stop a run when an unsupported request reaches the adapter seam."""

    def __init__(
        self,
        owner: CompositionOwner,
        config: LocalReadOnlyRunConfig,
        request_kind: str = "future/server-request.v1",
    ) -> None:
        super().__init__(owner, config)
        self.request_kind = request_kind

    def execute(
        self,
        run_id: str,
        prompt: str,
        *,
        task_type: str = "local_read_only",
        input_value: Any = None,
        metadata: Mapping[str, Any] | None = None,
        timeout: float = 45.0,
    ) -> None:
        del timeout
        self.execute_calls += 1
        run_metadata = dict(metadata or {})
        run_metadata["unknown_request"] = self.request_kind
        self._start_run(run_id, prompt, task_type, input_value, run_metadata)
        self.owner.record_result(
            run_id,
            "adapter.fixture.initialized",
            {
                "schema": FIXTURE_ADAPTER_SCHEMA,
                "unknown_request": self.request_kind,
                "network_requests": 0,
            },
            "fixture-adapter",
        )
        self.owner.safe_stop_run(
            run_id,
            "unsupported fixture request: {0}".format(self.request_kind),
        )
        raise FixtureUnknownBoundary(self.request_kind)
