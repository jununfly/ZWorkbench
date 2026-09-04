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


if __name__ == "__main__":
    unittest.main()
