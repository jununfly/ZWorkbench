#!/usr/bin/env python3
"""Run a bounded, owner-backed real Ark route-fallback staging probe.

The primary route deliberately uses a non-existent model so Ark returns a
deterministic model rejection.  The fallback route uses the configured real
model at the same fixed Ark endpoint.  This proves real Ark transport plus
the local owner/router fallback seam without pretending that a deliberate
negative control is a production outage or a second independent Provider.

The API key is read from stdin, held only in process memory, and never written
to the owner, event ledger, evidence, argv, or output.  This script is an
acceptance/evaluation runner, not the default ZWorkbench Provider route.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Mapping, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_remote_provider_failover" / "v1"
ROUTER_PATH = FIXTURE_ROOT / "router.py"
PROBE_PATH = REPO_ROOT / "scripts" / "run_optional_provider_probe.py"
RUNNER_SCHEMA = "zworkbench-real-ark-failover-runner/v1"
FIXTURE_SCHEMA = "zworkbench-w8-remote-provider-failover-fixture/v1"
ENDPOINT = "https://ark.cn-beijing.volces.com/api/coding/v3/responses"
DEFAULT_REGION = "cn-beijing"
DEFAULT_MODEL = "ark-code-latest"
DEFAULT_PRIMARY_MODEL = "__zworkbench_invalid_model__"
COOLDOWN_TICKS = 5
MAX_REQUESTS = 2
REQUIRED_GATES = (
    "key_scope_confirmed",
    "data_retention_confirmed",
    "remote_inventory_confirmed",
    "exit_path_confirmed",
    "one_time_authorization_confirmed",
)
RAW_SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(rb"AKIA[0-9A-Z]{12,}"),
    re.compile(rb"Authorization:\s*Bearer\s+\S+", re.IGNORECASE),
)

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


router_module = _load_module(ROUTER_PATH, "w8_remote_provider_failover_router")
probe_module = _load_module(PROBE_PATH, "optional_real_provider_probe")
OwnerBackedProviderRouter = router_module.OwnerBackedProviderRouter
ProviderFailure = router_module.ProviderFailure
ProviderRoute = router_module.ProviderRoute
from zworkbench import CompositionOwner  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def secret_scan(root: Path) -> Dict[str, int]:
    file_count = 0
    matches = 0
    matching_files = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        file_count += 1
        data = path.read_bytes()
        found = sum(len(pattern.findall(data)) for pattern in RAW_SECRET_PATTERNS)
        matches += found
        matching_files += int(found > 0)
    return {"file_count": file_count, "matching_files": matching_files, "matches": matches}


def validate_configuration(
    *,
    region: str,
    project_fingerprint: str,
    primary_model: str,
    fallback_model: str,
    budget_requests: int,
    max_duration_seconds: int,
) -> Dict[str, Any]:
    """Fail closed before reading the credential or making a network call."""

    preflight = {
        "region": region,
        "project_fingerprint": project_fingerprint,
        "budget_requests": budget_requests,
        "max_duration_seconds": max_duration_seconds,
        **{gate: True for gate in REQUIRED_GATES},
    }
    probe_module.validate_endpoint(ENDPOINT)
    verified = probe_module.validate_preflight(preflight, repeats=MAX_REQUESTS)
    if budget_requests != MAX_REQUESTS:
        raise ValueError("budget_requests must be exactly 2 for this two-route probe")
    if not isinstance(primary_model, str) or not primary_model.strip():
        raise ValueError("primary_model must be non-empty")
    if not isinstance(fallback_model, str) or not fallback_model.strip():
        raise ValueError("fallback_model must be non-empty")
    if primary_model == fallback_model:
        raise ValueError("primary_model and fallback_model must be different routes")
    # ``run_optional_provider_probe.run`` validates the caller-facing shape,
    # whose gate names are top-level. Keep the normalized fields, but retain
    # the explicit gates instead of passing only the nested summary shape.
    return {**verified, **{gate: True for gate in REQUIRED_GATES}}


def redact_probe_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep only the probe's already-redacted transport/semantic fields."""

    response = result.get("response") if isinstance(result.get("response"), Mapping) else {}
    return {
        "outcome": result.get("outcome"),
        "http_status": result.get("http_status"),
        "response": {
            "json": response.get("json"),
            "body_bytes": response.get("body_bytes"),
            "body_sha256": response.get("body_sha256"),
            "fixture_token_present": response.get("fixture_token_present"),
            "semantic_fixture_exact": response.get("semantic_fixture_exact"),
            "response_model": response.get("response_model"),
            "error_code": response.get("error_code"),
            "error_type": response.get("error_type"),
        },
        "error_type": result.get("error_type"),
    }


def run_probe(
    output_dir: Path,
    *,
    region: str,
    project_fingerprint: str,
    primary_model: str,
    fallback_model: str,
    budget_requests: int,
    max_duration_seconds: int,
    key: bytes,
) -> Dict[str, Any]:
    preflight = validate_configuration(
        region=region,
        project_fingerprint=project_fingerprint,
        primary_model=primary_model,
        fallback_model=fallback_model,
        budget_requests=budget_requests,
        max_duration_seconds=max_duration_seconds,
    )
    if not key:
        raise ValueError("credential input is empty")
    key_fingerprint = probe_module.digest(key)
    if key_fingerprint == project_fingerprint:
        raise ValueError("project_fingerprint matches api_key_fingerprint")

    case_root = output_dir / "case"
    case_root.mkdir(parents=True, exist_ok=False)
    database = case_root / "state" / "composition.sqlite3"
    run_id = "real-ark-failover-1"
    routes = (
        ProviderRoute("ark-primary", primary_model, ENDPOINT),
        ProviderRoute("ark-fallback", fallback_model, ENDPOINT),
    )
    calls: List[str] = []
    provider_attempts: List[Dict[str, Any]] = []
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None
    started = time.monotonic()
    with CompositionOwner(database) as owner:
        owner.create_run(run_id, "provider.read-only", {"request": "staging-fixture-001"}, {
            "provider": "volcengine-ark",
            "region": region,
            "project_fingerprint": project_fingerprint,
            "route_mode": "real-ark-negative-control-fallback",
        })
        owner.start_run(run_id)
        router = OwnerBackedProviderRouter(owner, routes, cooldown_ticks=COOLDOWN_TICKS)

        def dispatch(route: ProviderRoute) -> Mapping[str, Any]:
            calls.append(route.provider_id)
            remaining = max_duration_seconds - int(time.monotonic() - started)
            if remaining < 1:
                raise ProviderFailure("TIME_BUDGET_EXHAUSTED")
            probe_result = probe_module.run(
                route.endpoint,
                route.model,
                key,
                preflight=preflight,
                timeout=min(30, remaining),
            )
            redacted = redact_probe_result(probe_result)
            provider_attempts.append({"provider": route.provider_id, "model": route.model, **redacted})
            exact = (probe_result.get("response") or {}).get("semantic_fixture_exact") is True
            if probe_result.get("outcome") != "http_success" or not exact:
                if route.provider_id == "ark-primary":
                    http_status = probe_result.get("http_status")
                    error_code = (probe_result.get("response") or {}).get("error_code")
                    if http_status not in {400, 404}:
                        raise ProviderFailure("PRIMARY_NEGATIVE_CONTROL_UNEXPECTED", http_status=http_status, error_code=error_code)
                    raise ProviderFailure("MODEL_REJECTED", http_status=http_status, error_code=error_code)
                raise ProviderFailure("ARK_FALLBACK_FAILED", http_status=probe_result.get("http_status"))
            return {"semantic_fixture_exact": True, "text": "staging-fixture-001"}

        try:
            result = router.route(run_id, "real-ark-request-1", 0, dispatch)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}

    with CompositionOwner(database) as reopened:
        run = reopened.get_run(run_id)
        events = reopened.events(run_id)
        state_digest = reopened.state_digest()

    attempts = [event for event in events if event["type"] == "provider.attempt"]
    decisions = [event for event in events if event["type"] == "provider.failover.decision"]
    cooldowns = [event for event in events if event["type"] == "provider.cooldown.updated"]
    decision = decisions[0]["payload"] if decisions else {}
    checks = {
        "real_ark_route_completed": error is None and result is not None and result.get("status") == "completed",
        "owner_completed": run["status"] == "completed",
        "primary_rejected_then_fallback": calls == ["ark-primary", "ark-fallback"],
        "fallback_reason_recorded": decision.get("reason") == "MODEL_REJECTED",
        "primary_negative_control_http_status": decision.get("http_status") in {400, 404},
        "fallback_target_recorded": decision.get("from_provider") == "ark-primary" and decision.get("to_provider") == "ark-fallback",
        "cooldown_recorded": len(cooldowns) == 1
        and cooldowns[0]["payload"].get("cooldown_until") == COOLDOWN_TICKS,
        "bounded_attempts": len(attempts) == 4 and len(provider_attempts) == 2,
        "provider_identity_complete": all(
            all(event["payload"].get(field) not in {None, "", "unknown"} for field in ("provider", "model", "endpoint", "transport"))
            for event in attempts
        ),
        "effects_zero": len(run["effects"]) == 0,
        "state_digest_present": bool(state_digest),
    }
    write_json(
        case_root / "route-manifest.json",
        {
            "schema": RUNNER_SCHEMA,
            "endpoint": ENDPOINT,
            "region": region,
            "project_fingerprint": project_fingerprint,
            "routes": [
                {"provider": route.provider_id, "model": route.model, "endpoint": route.endpoint}
                for route in routes
            ],
            "failure_injection": "primary invalid model; no retry",
        },
    )
    scan = secret_scan(output_dir)
    checks["raw_credential_matches_zero"] = scan["matches"] == 0
    summary = {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": FIXTURE_SCHEMA,
        "classification": "acceptance/evaluation",
        "evidence_level": "authorized-real-Ark + owner-backed-route-fallback",
        "started_at": now(),
        "finished_at": now(),
        "output_dir": str(output_dir),
        "run_id": run_id,
        "status": "pass" if all(checks.values()) else "unknown/stop",
        "compatibility_status": "verified-for-authorized-real-ark-negative-control-fallback" if all(checks.values()) else "unknown/stop",
        "provider": {
            "provider": "volcengine-ark",
            "endpoint": ENDPOINT,
            "region": region,
            "project_fingerprint": project_fingerprint,
            "api_key_fingerprint": key_fingerprint,
            "primary_model": primary_model,
            "fallback_model": fallback_model,
        },
        "observed": {
            "error": error,
            "owner_status": run["status"],
            "calls": calls,
            "provider_attempts": provider_attempts,
            "owner_event_count": len(events),
            "state_digest": state_digest,
            "secret_scan": scan,
            "external_effects": 0,
            "retry_count": 0,
        },
        "checks": checks,
        "non_claims": [
            "The primary failure is a deliberate invalid-model negative control, not a proof of a transient Ark outage or quota exhaustion.",
            "Both routes use the same Ark endpoint and credential scope; this does not prove an independent second Provider or production failover availability.",
            "This does not prove default ZWorkbench remote routing, real project writes, tasks, Webhooks, backups, or Provider-side exit.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--project-fingerprint", required=True)
    parser.add_argument("--primary-model", default=DEFAULT_PRIMARY_MODEL)
    parser.add_argument("--fallback-model", default=DEFAULT_MODEL)
    parser.add_argument("--budget-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--max-duration-seconds", type=int, default=30)
    for gate in REQUIRED_GATES:
        parser.add_argument(f"--{gate.replace('_', '-')}", action="store_true")
    args = parser.parse_args()
    try:
        if not all(getattr(args, gate) for gate in REQUIRED_GATES):
            raise ValueError("all real-provider preflight gates must be explicitly confirmed")
        output_dir = args.output.expanduser().resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError("real Ark failover evidence output must be new or empty")
        output_dir.mkdir(parents=True, exist_ok=True)
        key = sys.stdin.buffer.read().strip()
        summary = run_probe(
            output_dir,
            region=args.region,
            project_fingerprint=args.project_fingerprint,
            primary_model=args.primary_model,
            fallback_model=args.fallback_model,
            budget_requests=args.budget_requests,
            max_duration_seconds=args.max_duration_seconds,
            key=key,
        )
    except Exception as exc:
        print(json.dumps({"schema": RUNNER_SCHEMA, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
