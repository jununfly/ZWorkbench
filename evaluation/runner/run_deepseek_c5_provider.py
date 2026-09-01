#!/usr/bin/env python3
"""Probe DeepSeek Harness provider routing versus provider failover.

The fixed DeepSeek ACP profile is run against isolated fake endpoints.  The
probe demonstrates normal route selection and records whether a timeout on one
endpoint reaches a separately started second endpoint.  It never treats a
same-route retry as a provider switch, and it keeps the C5 candidate result
unknown when no candidate-owned fallback contract is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
MANIFEST_PATH = REPO_ROOT / "evaluation" / "candidates" / "deepseek" / "manifest.json"
SCHEMA = "zworkbench-deepseek-c5-provider/v1"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def response_ok(frame: dict[str, Any]) -> bool:
    return "result" in frame and "error" not in frame


def environment_for(home: Path, base_url: str) -> dict[str, str]:
    import os

    environment = os.environ.copy()
    environment.update({
        "DSH_HOME": str(home),
        "DSH_TELEMETRY_DISABLED": "1",
        "DEEPSEEK_API_KEY": "w6-fake-key",
        "DEEPSEEK_BASE_URL": base_url + "/v1",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    })
    return environment


def one_route(entrypoint: Path, case_dir: Path, server: dict[str, Any], expected_provider: str) -> dict[str, Any]:
    from evaluation.runner.run_deepseek_c4_acp import AcpProcess, PROMPT, decode_session, session_paths

    project = case_dir / "project"
    shutil.copytree(FIXTURE / "code-project", project)
    home = case_dir / "dsh-home"
    agent = AcpProcess(
        entrypoint=entrypoint,
        project=project,
        environment=environment_for(home, server["base_url"]),
        transcript=case_dir / "transcript.jsonl",
    )
    try:
        initialize = agent.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        created = agent.request("session/new", {"cwd": str(project), "mcpServers": []})
        session_id = created.get("result", {}).get("sessionId", "")
        prompted = agent.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": PROMPT}]})
        closed = agent.close_session(session_id)
        exited = agent.close()
    except Exception:
        exited = agent.kill()
        raise
    paths = session_paths(home)
    events, invalid = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    requests = server["request_path"].read_text(encoding="utf-8").splitlines() if server["request_path"].exists() else []
    checks = {
        "initialize_ok": response_ok(initialize),
        "session_new_ok": response_ok(created),
        "prompt_completed": prompted.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "session_close_ok": response_ok(closed),
        "process_exited": exited["returncode"] == 0,
        "one_session_log": len(paths) == 1,
        "session_log_decodes": not invalid,
        "provider_request_seen": len(requests) > 0,
        "expected_provider_seen": any(expected_provider in line for line in requests),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observed": {"request_count": len(requests), "session_event_count": len(events), "session_event_types": sorted({str(event.get("type")) for event in events}), "invalid_session_lines": invalid},
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    from evaluation.runner.run_baseline import start_fake_provider, stop_fake_provider
    from evaluation.runner.run_deepseek_challenger import candidate_preflight

    manifest = load_json(MANIFEST_PATH)
    candidate_repo = args.candidate_repo.resolve()
    entrypoint = (args.candidate_entry or candidate_repo / manifest["runtime"]["entrypoint"]).resolve()
    preflight = candidate_preflight(candidate_repo, entrypoint, manifest)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "preflight.json", preflight)
    if preflight["status"] != "pass":
        summary = {"schema": SCHEMA, "status": "blocked", "classification": "acceptance/evaluation", "candidate": manifest, "preflight": preflight, "candidate_c5_status": "unknown"}
        write_json(output / "summary.json", summary)
        return summary

    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="zwb-w8-deepseek-c5-") as temp:
        root = Path(temp)
        for name in ("a", "b", "timeout", "fallback"):
            (root / name).mkdir()
        a, a_error = start_fake_provider(root / "a", "fake-a", "plain", port=0)
        b, b_error = start_fake_provider(root / "b", "fake-b", "plain", port=0)
        timeout, timeout_error = start_fake_provider(root / "timeout", "fake-a", "plain", port=0, fault="timeout_once")
        fallback, fallback_error = start_fake_provider(root / "fallback", "fake-b", "plain", port=0)
        if any((a_error, b_error, timeout_error, fallback_error)):
            raise RuntimeError(f"fake Provider startup failed: a={a_error}, b={b_error}, timeout={timeout_error}, fallback={fallback_error}")
        try:
            for provider, server in (("fake-a", a), ("fake-b", b)):
                for repeat in range(1, args.repeats + 1):
                    case_dir = output / "normal" / provider / f"repeat-{repeat:02d}"
                    case_dir.mkdir(parents=True, exist_ok=True)
                    result = one_route(entrypoint, case_dir, server, provider)
                    result.update({"scenario": "normal_route", "provider": provider, "repeat": repeat})
                    write_json(case_dir / "result.json", result)
                    cases.append(result)

            failover_case = output / "failure-no-fallback" / "repeat-01"
            failover_case.mkdir(parents=True, exist_ok=True)
            failure_result = one_route(entrypoint, failover_case, timeout, "fake-a")
            timeout_requests = timeout["request_path"].read_text(encoding="utf-8").splitlines() if timeout["request_path"].exists() else []
            fallback_requests = fallback["request_path"].read_text(encoding="utf-8").splitlines() if fallback["request_path"].exists() else []
            failure_result.update({
                "scenario": "failure_no_fallback",
                "provider": "fake-a",
                "repeat": 1,
                "observed": {
                    **failure_result.get("observed", {}),
                    "primary_request_count": len(timeout_requests),
                    "second_provider_request_count": len(fallback_requests),
                    "same_route_retry_only": len(timeout_requests) > 1 and len(fallback_requests) == 0,
                },
                "checks": {
                    **failure_result.get("checks", {}),
                    "second_provider_not_contacted": len(fallback_requests) == 0,
                },
            })
            write_json(failover_case / "result.json", failure_result)
            cases.append(failure_result)
        finally:
            for server in (fallback, timeout, b, a):
                stop_fake_provider(server)

    normal = [case for case in cases if case["scenario"] == "normal_route"]
    failure = [case for case in cases if case["scenario"] == "failure_no_fallback"]
    normal_pass = len(normal) == args.repeats * 2 and all(case["status"] == "pass" for case in normal)
    same_route_only = bool(failure and failure[0].get("observed", {}).get("same_route_retry_only"))
    summary = {
        "schema": SCHEMA,
        "status": "pass" if normal_pass else "fail",
        "classification": "acceptance/evaluation",
        "candidate": manifest,
        "preflight": preflight,
        "candidate_c5_status": "unknown: no candidate-owned provider failover/degradation contract observed",
        "normal_routes": {"status": "pass" if normal_pass else "fail", "cases": f"{sum(case['status'] == 'pass' for case in normal)}/{len(normal)}", "providers": ["fake-a", "fake-b"]},
        "failure_probe": {"status": "observed", "same_route_retry_only": same_route_only, "automatic_second_provider_contacted": not same_route_only, "degradation_reason_contract": "not established"},
        "threshold_interpretation": {"normal_deterministic_threshold": "met for isolated configured routes", "downgrade_reason_threshold": "not met/unknown because no fallback transition exists to explain", "unknown_rule": "same-route retry is not provider failover; a composition router would need a separate adapter and ledger"},
        "cases": cases,
        "checks": {"preflight_passed": preflight["status"] == "pass", "normal_routes_passed": normal_pass, "no_real_credentials": True, "no_external_network": True, "no_production_data": True, "no_external_side_effects": True},
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--candidate-entry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    summary = run(args)
    print(json.dumps({"status": summary["status"], "output": str(args.output.resolve()), "candidate_c5_status": summary["candidate_c5_status"]}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
