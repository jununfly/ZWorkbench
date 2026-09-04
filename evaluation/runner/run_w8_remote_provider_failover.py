#!/usr/bin/env python3
"""Generate isolated dual-loopback Provider failover evidence.

This acceptance/evaluation runner exercises the fixture router against two
real HTTP servers bound to ephemeral ``127.0.0.1`` ports.  The primary can be
made to return a deterministic failure, while the secondary returns the fixed
semantic fixture.  CompositionOwner remains the only durable ledger: the
router's in-memory cooldown projection is discarded and rebuilt after an
owner reopen.

The generated package is ``pass-with-composition`` evidence.  It does not
claim real Ark failover, production Provider availability, or Provider-side
task/data/backup/retention/account exit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import threading
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_remote_provider_failover" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RUNNER_SCHEMA = "zworkbench-w8-remote-provider-failover-runner/v1"
FIXTURE_SCHEMA = "zworkbench-w8-remote-provider-failover-fixture/v1"
COOLDOWN_TICKS = 5
RAW_SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(rb"AKIA[0-9A-Z]{12,}"),
    re.compile(rb"fixture-secret"),
    re.compile(rb"Authorization:\s*Bearer\s+\S+", re.IGNORECASE),
)

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(FIXTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(FIXTURE_ROOT))

from router import (  # noqa: E402
    OwnerBackedProviderRouter,
    ProviderFailure,
    ProviderRoute,
)
from zworkbench import CompositionOwner  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def secret_scan(root: Path) -> Dict[str, Any]:
    """Scan generated evidence for raw credential-shaped bytes."""

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


class LoopbackProvider:
    """A case-local HTTP Provider with a non-persistent request summary."""

    def __init__(self, provider_id: str, model: str, mode: str):
        if mode not in {"normal", "rate_limit", "unavailable"}:
            raise ValueError(f"unknown loopback Provider mode: {mode}")
        self.provider_id = provider_id
        self.model = model
        self.mode = mode
        self.requests: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name=f"{provider_id}-loopback", daemon=True)

    def _handler(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _send(self, status: int, payload: Dict[str, Any]) -> None:
                data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send(200, {"ok": True, "provider": provider.provider_id})
                else:
                    self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:
                if self.path != "/v1/responses":
                    self._send(404, {"error": "not_found"})
                    return
                content_length = int(self.headers.get("content-length", "0"))
                self.rfile.read(content_length)
                if provider.mode == "rate_limit":
                    status = 429
                    payload = {"error": {"code": "RATE_LIMIT"}}
                elif provider.mode == "unavailable":
                    status = 503
                    payload = {"error": {"code": "UPSTREAM_UNAVAILABLE"}}
                else:
                    status = 200
                    payload = {
                        "status": "completed",
                        "model": provider.model,
                        "output_text": "fixture-ok",
                    }
                with provider._lock:
                    provider.requests.append(
                        {
                            "method": "POST",
                            "path": self.path,
                            "request_bytes": content_length,
                            "status": status,
                        }
                    )
                self._send(status, payload)

        return Handler

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1/responses"

    @property
    def route(self) -> ProviderRoute:
        return ProviderRoute(self.provider_id, self.model, self.endpoint)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def dispatch_http(calls: List[str], route: ProviderRoute) -> Dict[str, Any]:
    """Call one loopback Provider without retaining request/response bodies."""

    calls.append(route.provider_id)
    body = json.dumps(
        {"model": route.model, "input": [{"type": "text", "text": "fixture request"}]},
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        route.endpoint,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2.0) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        response_body = exc.read()
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        code = ((payload.get("error") or {}).get("code") if isinstance(payload, dict) else None)
        if exc.code == 429 and code == "RATE_LIMIT":
            raise ProviderFailure("RATE_LIMIT", http_status=429) from exc
        if exc.code == 503 and code == "UPSTREAM_UNAVAILABLE":
            raise ProviderFailure("UPSTREAM_UNAVAILABLE", http_status=503) from exc
        raise ProviderFailure(f"HTTP_{exc.code}", http_status=exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderFailure("LOOPBACK_TRANSPORT_ERROR") from exc
    if status != 200:
        raise ProviderFailure(f"HTTP_{status}", http_status=status)
    return {"status": payload.get("status"), "text": payload.get("output_text")}


def create_run(owner: CompositionOwner, run_id: str) -> None:
    owner.create_run(run_id, "provider.read-only", {"request": "fixture"})
    owner.start_run(run_id)


def result_by_kind(run: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    return [item for item in run["results"] if item["kind"] == kind]


def events_by_type(events: List[Dict[str, Any]], event_type: str) -> List[Dict[str, Any]]:
    return [event for event in events if event["type"] == event_type]


def run_fallback_case(output_dir: Path) -> Dict[str, Any]:
    case_root = output_dir / "cases" / "fallback"
    case_root.mkdir(parents=True, exist_ok=False)
    database = case_root / "state" / "composition.sqlite3"
    primary = LoopbackProvider("fake-a", "fixture-model-a", "rate_limit")
    secondary = LoopbackProvider("fake-b", "fixture-model-b", "normal")
    calls: List[str] = []
    execution_error: Optional[Dict[str, str]] = None
    result: Optional[Dict[str, Any]] = None
    primary.start()
    secondary.start()
    try:
        with CompositionOwner(database) as owner:
            create_run(owner, "failover-run")
            router = OwnerBackedProviderRouter(owner, (primary.route, secondary.route), COOLDOWN_TICKS)
            try:
                result = router.route("failover-run", "request-1", 0, lambda route: dispatch_http(calls, route))
            except Exception as exc:  # evidence should report an unexpected seam failure
                execution_error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        primary.stop()
        secondary.stop()

    with CompositionOwner(database) as reopened:
        run = reopened.get_run("failover-run")
        events = reopened.events("failover-run")
        state_digest = reopened.state_digest()

    attempts = events_by_type(events, "provider.attempt")
    cooldowns = events_by_type(events, "provider.cooldown.updated")
    decisions = events_by_type(events, "provider.failover.decision")
    decision = decisions[0]["payload"] if decisions else {}
    checks = {
        "router_completed": execution_error is None and result is not None and result.get("status") == "completed",
        "owner_completed": run["status"] == "completed",
        "primary_rate_limit_then_secondary": calls == ["fake-a", "fake-b"],
        "fallback_reason_recorded": decision.get("reason") == "RATE_LIMIT",
        "fallback_target_recorded": decision.get("from_provider") == "fake-a" and decision.get("to_provider") == "fake-b",
        "primary_cooldown_recorded": len(cooldowns) == 1
        and cooldowns[0]["payload"].get("cooldown_before") == 0
        and cooldowns[0]["payload"].get("cooldown_until") == COOLDOWN_TICKS,
        "provider_identity_complete": all(
            all(event["payload"].get(field) not in {None, "unknown", ""} for field in ("provider", "model", "endpoint", "transport"))
            for event in attempts
        ),
        "bounded_attempts": len(attempts) == 4 and calls.count("fake-a") == 1 and calls.count("fake-b") == 1,
        "effects_zero": len(run["effects"]) == 0,
        "loopback_only": all(route.endpoint.startswith("http://127.0.0.1:") for route in (primary.route, secondary.route)),
        "state_digest_present": bool(state_digest),
    }
    summary = {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": FIXTURE_SCHEMA,
        "evidence_level": "owner-backed + loopback-composed",
        "scenario": "fallback",
        "status": "pass" if all(checks.values()) else "fail",
        "run_id": "failover-run",
        "observed": {
            "execution_error": execution_error,
            "owner_status": run["status"],
            "selected_provider": result.get("provider") if result else None,
            "calls": calls,
            "attempt_count": len(attempts),
            "provider_requests": {
                primary.provider_id: list(primary.requests),
                secondary.provider_id: list(secondary.requests),
            },
            "state_digest": state_digest,
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "checks": checks,
        "non_claims": [
            "This does not prove real Ark or any other remote Provider failover.",
            "This does not prove default ZWorkbench Provider routing or production availability.",
            "Provider-side task, data, backup, retention and account exit remain delegated and unverified.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_all_cooled_reopen_case(output_dir: Path) -> Dict[str, Any]:
    case_root = output_dir / "cases" / "all-cooled-after-reopen"
    case_root.mkdir(parents=True, exist_ok=False)
    database = case_root / "state" / "composition.sqlite3"
    primary = LoopbackProvider("fake-a", "fixture-model-a", "unavailable")
    secondary = LoopbackProvider("fake-b", "fixture-model-b", "unavailable")
    seed_calls: List[str] = []
    reopened_calls: List[str] = []
    seed_result: Optional[Dict[str, Any]] = None
    reopen_result: Optional[Dict[str, Any]] = None
    reopen_error: Optional[Dict[str, str]] = None
    primary.start()
    secondary.start()
    try:
        with CompositionOwner(database) as owner:
            create_run(owner, "cooldown-seed")
            router = OwnerBackedProviderRouter(owner, (primary.route, secondary.route), COOLDOWN_TICKS)
            seed_result = router.route(
                "cooldown-seed",
                "seed-request",
                0,
                lambda route: dispatch_http(seed_calls, route),
            )
    finally:
        primary.stop()
        secondary.stop()

    with CompositionOwner(database) as reopened:
        create_run(reopened, "reopened-run")
        rebuilt_router = OwnerBackedProviderRouter(reopened, (primary.route, secondary.route), COOLDOWN_TICKS)

        def must_not_dispatch(route: ProviderRoute) -> Dict[str, Any]:
            reopened_calls.append(route.provider_id)
            raise RuntimeError("all-cooled route dispatched to a Provider")

        try:
            reopen_result = rebuilt_router.route("reopened-run", "reopen-request", 0, must_not_dispatch)
        except Exception as exc:
            reopen_error = {"type": type(exc).__name__, "message": str(exc)}
        seed_run = reopened.get_run("cooldown-seed")
        run = reopened.get_run("reopened-run")
        events = reopened.events("reopened-run")
        state_digest = reopened.state_digest()

    decisions = events_by_type(events, "provider.failover.decision")
    decision = decisions[0]["payload"] if decisions else {}
    attempts = events_by_type(events, "provider.attempt")
    checks = {
        "seed_cooled_both_routes": seed_result is not None
        and seed_result.get("status") == "safe_stopped"
        and seed_calls == ["fake-a", "fake-b"],
        "owner_reopen_rebuilt_cooldown": decision.get("cooldown_snapshot") == {"fake-a": COOLDOWN_TICKS, "fake-b": COOLDOWN_TICKS},
        "all_cooled_safe_stop": reopen_error is None
        and reopen_result is not None
        and reopen_result.get("status") == "safe_stopped"
        and run["status"] == "safe_stopped",
        "no_new_provider_selection": reopened_calls == [] and len(attempts) == 0,
        "all_cooled_reason_and_no_target": decision.get("reason") == "all_routes_cooling_down"
        and decision.get("degradation") == "safe_stop"
        and decision.get("to_provider") is None,
        "effects_zero": len(seed_run["effects"]) == 0 and len(run["effects"]) == 0,
        "state_digest_present": bool(state_digest),
        "loopback_only": all(route.endpoint.startswith("http://127.0.0.1:") for route in (primary.route, secondary.route)),
    }
    summary = {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": FIXTURE_SCHEMA,
        "evidence_level": "owner-backed + loopback-composed",
        "scenario": "all-cooled-after-reopen",
        "status": "pass" if all(checks.values()) else "fail",
        "run_id": "reopened-run",
        "observed": {
            "reopen_error": reopen_error,
            "seed_calls": seed_calls,
            "reopened_calls": reopened_calls,
            "seed_provider_request_counts": {
                primary.provider_id: len(primary.requests),
                secondary.provider_id: len(secondary.requests),
            },
            "owner_status": run["status"],
            "state_digest": state_digest,
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "checks": checks,
        "non_claims": [
            "This does not prove real Ark or any other remote Provider failover.",
            "This does not prove Provider-side task, data, backup, retention or account exit.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_suite(output_dir: Path) -> Dict[str, Any]:
    """Generate both failover cases under a fresh evidence directory."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("failover evidence output directory must be new or empty")
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"fixture manifest is missing: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("fixture manifest schema mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = now()
    cases = [run_fallback_case(output_dir), run_all_cooled_reopen_case(output_dir)]
    scan = secret_scan(output_dir)
    checks = {
        "cases_passed": all(case["status"] == "pass" for case in cases),
        "raw_credential_matches_zero": scan["matches"] == 0,
        "loopback_only": all(case["checks"].get("loopback_only") is True for case in cases),
        "effects_zero": all(case["checks"].get("effects_zero") is True for case in cases),
    }
    summary = {
        "schema": RUNNER_SCHEMA,
        "fixture_schema": FIXTURE_SCHEMA,
        "classification": "acceptance/evaluation",
        "evidence_level": "owner-backed + loopback-composed",
        "started_at": started_at,
        "finished_at": now(),
        "output_dir": str(output_dir),
        "status": "pass-with-composition" if all(checks.values()) else "unknown/stop",
        "checks": checks,
        "observed": {
            "case_count": len(cases),
            "passed_case_count": sum(case["status"] == "pass" for case in cases),
            "secret_scan": scan,
            "external_network_requests": 0,
            "real_credentials": 0,
            "external_effects": 0,
        },
        "cases": cases,
        "formal_1_9_7_2_status": "HOLD: real remote Provider failover and Provider-side exit evidence are not claimed",
        "non_claims": [
            "Loopback-composed evidence is not real Ark or production Provider compatibility evidence.",
            "No remote task, data, backup, retention or account exit operation was performed.",
            "This runner does not alter the default ZWorkbench Provider route or scheduler.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new or empty evidence directory")
    args = parser.parse_args()
    try:
        summary = run_suite(args.output.expanduser().resolve())
    except Exception as exc:
        print(json.dumps({"schema": RUNNER_SCHEMA, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass-with-composition" else 1


if __name__ == "__main__":
    raise SystemExit(main())
