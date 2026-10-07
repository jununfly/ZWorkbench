from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from evaluation.runner import run_w8_remote_provider_failover as runner
from evaluation.fixtures.w8_remote_provider_failover.v1.router import (
    OwnerBackedProviderRouter,
    ProviderFailure,
    ProviderRoute,
)
from scripts import run_real_ark_failover as real_ark_runner
from zworkbench import CompositionOwner


class RemoteProviderFailoverFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.database = self.root / "state" / "composition.sqlite3"
        self.routes = (
            ProviderRoute("primary", "fixture-model-primary", "http://127.0.0.1:41001/v1/responses"),
            ProviderRoute("secondary", "fixture-model-secondary", "http://127.0.0.1:41002/v1/responses"),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _start_run(self, owner: CompositionOwner, run_id: str) -> None:
        owner.create_run(run_id, "provider.read-only", {"request": "fixture"})
        owner.start_run(run_id)

    def test_rate_limit_falls_back_once_and_records_durable_reason_ledger(self) -> None:
        calls: list[str] = []
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "failover-run")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def dispatch(route: ProviderRoute):
                calls.append(route.provider_id)
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            result = router.route("failover-run", "request-1", 0, dispatch)
            run = owner.get_run("failover-run")
            events = owner.events("failover-run")

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["provider"], "secondary")
            self.assertEqual(calls, ["primary", "secondary"])
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["effects"], [])

            attempts = [event for event in events if event["type"] == "provider.attempt"]
            self.assertEqual([event["payload"]["status"] for event in attempts], ["started", "failed", "started", "succeeded"])
            cooldown = [event for event in events if event["type"] == "provider.cooldown.updated"]
            self.assertEqual(len(cooldown), 1)
            self.assertEqual(cooldown[0]["payload"]["provider_id"], "primary")
            self.assertEqual(cooldown[0]["payload"]["cooldown_before"], 0)
            self.assertEqual(cooldown[0]["payload"]["cooldown_until"], 5)

            decisions = [event for event in events if event["type"] == "provider.failover.decision"]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["payload"]["reason"], "RATE_LIMIT")
            self.assertEqual(decisions[0]["payload"]["from_provider"], "primary")
            self.assertEqual(decisions[0]["payload"]["to_provider"], "secondary")
            self.assertEqual(decisions[0]["payload"]["degradation"], "fallback")
            self.assertEqual(decisions[0]["payload"]["http_status"], 429)

            ledger_results = [item for item in run["results"] if item["kind"] == "provider.failover"]
            self.assertEqual(len(ledger_results), 1)
            self.assertEqual(ledger_results[0]["value"]["reason"], "RATE_LIMIT")
            self.assertEqual(ledger_results[0]["value"]["to_provider"], "secondary")

            owner_json = json.dumps(owner.snapshot(), ensure_ascii=False, sort_keys=True)
            self.assertNotIn("api_key", owner_json)
            self.assertNotIn("authorization", owner_json)
            self.assertNotIn("fixture-secret", owner_json)

    def test_reopen_rebuilds_all_route_cooldown_and_safe_stops_without_dispatch(self) -> None:
        seeded_calls: list[str] = []
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "cooldown-seed")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def fail_dispatch(route: ProviderRoute):
                seeded_calls.append(route.provider_id)
                raise ProviderFailure("UPSTREAM_UNAVAILABLE", http_status=503)

            result = router.route("cooldown-seed", "seed-request", 0, fail_dispatch)
            self.assertEqual(result["status"], "safe_stopped")
            self.assertEqual(seeded_calls, ["primary", "secondary"])
            self.assertEqual(owner.get_run("cooldown-seed")["status"], "safe_stopped")

        reopened_calls: list[str] = []
        with CompositionOwner(self.database) as reopened:
            self._start_run(reopened, "reopened-run")
            rebuilt_router = OwnerBackedProviderRouter(reopened, self.routes, cooldown_ticks=5)

            def must_not_dispatch(route: ProviderRoute):
                reopened_calls.append(route.provider_id)
                raise AssertionError("all-cooled route must not call a Provider")

            result = rebuilt_router.route("reopened-run", "reopen-request", 0, must_not_dispatch)
            run = reopened.get_run("reopened-run")
            events = reopened.events("reopened-run")

            self.assertEqual(result["status"], "safe_stopped")
            self.assertEqual(reopened_calls, [])
            self.assertEqual(run["status"], "safe_stopped")
            self.assertEqual(run["effects"], [])
            self.assertEqual([event["type"] for event in events].count("provider.attempt"), 0)
            decision = next(event for event in events if event["type"] == "provider.failover.decision")
            self.assertEqual(decision["payload"]["reason"], "all_routes_cooling_down")
            self.assertEqual(decision["payload"]["degradation"], "safe_stop")
            self.assertIsNone(decision["payload"]["to_provider"])
            self.assertEqual(decision["payload"]["cooldown_snapshot"], {"primary": 5, "secondary": 5})

            owner_json = json.dumps(reopened.snapshot(), ensure_ascii=False, sort_keys=True)
            self.assertNotIn("api_key", owner_json)
            self.assertNotIn("authorization", owner_json)
            self.assertNotIn("fixture-secret", owner_json)

    def test_runner_produces_pass_with_composition_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = runner.run_suite(Path(temporary) / "evidence")

        self.assertEqual(summary["status"], "pass-with-composition")
        self.assertEqual(summary["observed"]["secret_scan"]["matches"], 0)
        self.assertEqual(summary["observed"]["external_network_requests"], 0)
        self.assertEqual(summary["observed"]["external_effects"], 0)
        self.assertEqual(summary["observed"]["passed_case_count"], 2)

    def test_real_ark_runner_is_explicit_about_route_identity_and_redaction(self) -> None:
        with self.assertRaises(ValueError):
            real_ark_runner.validate_configuration(
                region="cn-beijing",
                project_fingerprint="0" * 64,
                primary_model="ark-code-latest",
                fallback_model="ark-code-latest",
                budget_requests=2,
                max_duration_seconds=30,
            )

        configuration = real_ark_runner.validate_configuration(
            region="cn-beijing",
            project_fingerprint="0" * 64,
            primary_model="__zworkbench_invalid_model__",
            fallback_model="ark-code-latest",
            budget_requests=2,
            max_duration_seconds=30,
        )
        self.assertTrue(all(configuration[gate] is True for gate in real_ark_runner.REQUIRED_GATES))

        redacted = real_ark_runner.redact_probe_result(
            {
                "outcome": "http_success",
                "http_status": 200,
                "credential": {"api_key": "fixture-secret-must-not-be-copied"},
                "response": {
                    "json": True,
                    "body_bytes": 42,
                    "body_sha256": "body-digest",
                    "fixture_token_present": True,
                    "semantic_fixture_exact": True,
                    "response_model": "ark-code-latest",
                    "raw_body": "fixture-secret-must-not-be-copied",
                },
            }
        )
        redacted_json = json.dumps(redacted, ensure_ascii=False)
        self.assertNotIn("fixture-secret", redacted_json)
        self.assertNotIn("api_key", redacted_json)
        self.assertEqual(redacted["response"]["semantic_fixture_exact"], True)

    def test_fallback_is_recorded_in_owner_backed_fallback_ledger(self) -> None:
        # Node 1-1-1: the router's fallback decision must now land in the
        # dedicated owner-backed provider_fallback_ledger, not only fixture events.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "fallback-ledger-run")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def dispatch(route: ProviderRoute):
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            router.route("fallback-ledger-run", "request-1", 0, dispatch)
            ledger = owner.provider_fallback_ledger_for_run("fallback-ledger-run")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["from_provider"], "primary")
            self.assertEqual(ledger[0]["to_provider"], "secondary")
            self.assertEqual(ledger[0]["reason"], "RATE_LIMIT")
            self.assertEqual(ledger[0]["degradation_mode"], "fallback")
            self.assertEqual(ledger[0]["attempt"], 1)
            self.assertEqual(ledger[0]["http_status"], 429)

    def test_owner_fallback_ledger_rejects_missing_reason(self) -> None:
        # Regression for node 1-1-1: reason-required fail-closed at the owner.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "missing-reason-run")
            with self.assertRaises(ValueError):
                owner.record_provider_fallback(
                    "missing-reason-run",
                    from_provider="primary",
                    to_provider="secondary",
                    reason="",
                    degradation_mode="fallback",
                    attempt=1,
                )

    def test_attempts_recorded_in_owner_backed_attempt_ledger(self) -> None:
        # Node 1-1-2: every dispatched attempt must land in the dedicated
        # owner-backed provider_attempt_ledger (not only fixture events), so a
        # downstream Provider-level retry budget can count attempts per run.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "attempt-ledger-run")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def dispatch(route: ProviderRoute):
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            router.route("attempt-ledger-run", "request-1", 0, dispatch)
            ledger = owner.provider_attempt_ledger_for_run("attempt-ledger-run")
            self.assertEqual(len(ledger), 2)
            self.assertEqual([e["attempt_number"] for e in ledger], [1, 2])
            self.assertEqual([e["provider_id"] for e in ledger], ["primary", "secondary"])
            self.assertEqual([e["status"] for e in ledger], ["failed", "succeeded"])
            self.assertEqual(ledger[0]["failure_code"], "RATE_LIMIT")
            self.assertIsNone(ledger[1]["failure_code"])

            per_provider = {}
            for entry in ledger:
                per_provider[entry["provider_id"]] = per_provider.get(entry["provider_id"], 0) + 1
            self.assertEqual(per_provider, {"primary": 1, "secondary": 1})

    def test_attempt_ledger_survives_reopen(self) -> None:
        # Node 1-1-2 regression: attempt accounting is durable and survives a
        # DB reopen, proving it is owner-backed rather than transient fixture state.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "attempt-reopen-run")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def dispatch(route: ProviderRoute):
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            router.route("attempt-reopen-run", "request-1", 0, dispatch)
            digest_before = owner.state_digest()

        with CompositionOwner(self.database) as reopened:
            ledger = reopened.provider_attempt_ledger_for_run("attempt-reopen-run")
            self.assertEqual(len(ledger), 2)
            self.assertEqual([e["status"] for e in ledger], ["failed", "succeeded"])
            self.assertEqual(reopened.state_digest(), digest_before)

    def test_retry_budget_captured_for_undeclared_provider(self) -> None:
        # Node 1-1-3 regression: the router records every cross-Provider retry in
        # the owner-backed retry-budget ledger (attempt/failure_class/target/reason).
        # With no declared ceiling the bound is 'undeclared' and the path is not
        # blocked, proving the budget layer is auditing rather than silent.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "budget-undeclared-run")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            def dispatch(route: ProviderRoute):
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            router.route("budget-undeclared-run", "request-1", 0, dispatch)
            ledger = owner.provider_retry_budget_ledger_for_run("budget-undeclared-run")
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["provider_id"], "primary")
            self.assertEqual(ledger[0]["attempt_number"], 1)
            self.assertEqual(ledger[0]["failure_class"], "RATE_LIMIT")
            self.assertEqual(ledger[0]["target"], "secondary")
            self.assertEqual(ledger[0]["reason"], "RATE_LIMIT")
            self.assertEqual(ledger[0]["bound"], "undeclared")

    def test_declared_budget_exhaustion_safe_stops(self) -> None:
        # Node 1-1-3 regression: a declared ceiling is enforced fail-closed. A
        # zero-retry budget means the Provider cannot be retried; the router must
        # safe-stop instead of dispatching the fallback Provider.
        with CompositionOwner(self.database) as owner:
            self._start_run(owner, "budget-exhausted-run")
            owner.declare_provider_retry_budget("primary", max_retries=0, declared_by="owner")
            router = OwnerBackedProviderRouter(owner, self.routes, cooldown_ticks=5)

            dispatched: list[str] = []

            def dispatch(route: ProviderRoute):
                dispatched.append(route.provider_id)
                if route.provider_id == "primary":
                    raise ProviderFailure("RATE_LIMIT", http_status=429)
                return {"text": "fixture-ok", "provider": route.provider_id}

            result = router.route("budget-exhausted-run", "request-1", 0, dispatch)
            self.assertEqual(result["status"], "safe_stopped")
            self.assertEqual(dispatched, ["primary"])
            self.assertEqual(owner.get_run("budget-exhausted-run")["status"], "safe_stopped")

            ledger = owner.provider_retry_budget_ledger_for_run("budget-exhausted-run")
            self.assertEqual(len(ledger), 0)


if __name__ == "__main__":
    unittest.main()
