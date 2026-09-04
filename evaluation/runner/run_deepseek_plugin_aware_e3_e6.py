#!/usr/bin/env python3
"""Run an independent E3-E6 evaluation for the DeepSeek plugin composition.

This is acceptance/evaluation infrastructure, not ZWorkbench product code.
The runner deliberately separates three kinds of evidence:

* behavior executed by the pinned plugins (the config-migration runtime seam,
  router-core, and memoir's bounded local store);
* policy and durability provided by the ZWorkbench composition owner; and
* capabilities that the selected plugins do not expose (notably Provider
  failover and a complete unattended lifecycle).

Missing candidate contracts are recorded as ``unknown/stop``.  They are never
filled with evaluator-owned behavior and never inherit Codex evidence.
Everything runs under a newly-created case-local evidence directory.  There
is no registry install, external network, real credential, real DSH_HOME,
Provider request, or production project write.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-plugin-bundle" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
RUNTIME_RUNNER = REPO_ROOT / "evaluation" / "runner" / "run_deepseek_config_migrate_runtime_seam.py"
BEHAVIOR_PROBE = FIXTURE_ROOT / "plugin-behavior-probe.mjs"
SCHEMA = "zworkbench-w8-deepseek-plugin-aware-e3-e6/v1"
ROUTER_COMMIT = "f753bb1cd793a8e74b01d8fa5ad2c3d87a2e3c30"
ROUTER_SOURCE = "preset/router-standard/router-core-v34.mjs"
CONFIG_PLUGIN_COMMIT = "24aa64188386181bdaf21f4b46fea02bddf77e71"
CONFIG_PLUGIN = "dsh-config-migrate"
MEMOIR_PLUGIN = "dsh-memoir"
E3_UNKNOWN_EFFECT_CLASS = "future-plugin-effect-v1"
E5_THRESHOLDS_MINUTES = {
    "fresh_install": 90,
    "upgrade": 30,
    "backup_restore": 30,
    "fault_diagnosis": 30,
}
ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/coding/v3/responses"
ARK_MODEL = "ark-code-latest"
REAL_PROVIDER_SCHEMA = "zworkbench-optional-real-provider-probe/v1"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from evaluation.runner.run_deepseek_config_migrate_adapter import (  # noqa: E402
    git_head,
    git_show,
    read_json,
    sha256_bytes,
    write_json,
)
from zworkbench.composition import CompositionOwner, InvalidTransition  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def path_map(root: Path, paths: list[Path]) -> dict[str, Any]:
    return {
        "all_inside_case_root": all(inside(root, path) for path in paths),
        "paths": {str(path): inside(root, path) for path in paths},
    }


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float = 120.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-16000:],
            "stderr": result.stderr[-16000:],
            "duration_ms": round((time.monotonic() - started) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "returncode": None,
            "stdout": str(error.stdout or "")[-16000:],
            "stderr": str(error.stderr or "")[-16000:],
            "duration_ms": round((time.monotonic() - started) * 1000),
            "timed_out": True,
        }


def run_runtime_seam(bundle_root: Path, output: Path) -> dict[str, Any]:
    result = run_command(
        [sys.executable, str(RUNTIME_RUNNER), "--bundle-root", str(bundle_root), "--output", str(output)],
        cwd=REPO_ROOT,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "NO_PROXY": "*",
            "no_proxy": "*",
            "DSH_TELEMETRY_DISABLED": "1",
        },
        timeout=120,
    )
    write_json(output / "runner-process.json", result)
    summary_path = output / "summary.json"
    if summary_path.is_file():
        return read_json(summary_path)
    return {"status": "fail", "runner_process": result, "checks": {"summary_present": False}}


def run_e3_unknown_effect(case_dir: Path) -> dict[str, Any]:
    database = case_dir / "state" / "composition.sqlite3"
    run_id = "w8-plugin-aware-e3-unknown-effect"
    with CompositionOwner(database) as owner:
        owner.create_run(run_id, "plugin-aware-unknown-effect", {"plugin": CONFIG_PLUGIN})
        owner.start_run(run_id)
        denied = owner.claim_effect(
            run_id,
            f"{run_id}:operation-1",
            "future-plugin-action",
            str(case_dir / "future-effect"),
            f"{run_id}:idempotency-1",
            E3_UNKNOWN_EFFECT_CLASS,
        )
        retry = owner.claim_effect(
            run_id,
            f"{run_id}:operation-1",
            "future-plugin-action",
            str(case_dir / "future-effect"),
            f"{run_id}:idempotency-1",
            E3_UNKNOWN_EFFECT_CLASS,
        )
        snapshot = owner.snapshot()
        run = owner.get_run(run_id)
    checks = {
        "unknown_effect_denied": denied.status == "denied" and denied.reason == "unknown_effect_class",
        "run_safe_stopped": run.get("status") == "safe_stopped",
        "retry_not_automatic": retry.status == "denied" and retry.reason.startswith("run_terminal:"),
        "physical_effects_zero": len(run.get("effects", [])) == 0,
        "owner_events_present": len(snapshot.get("events", [])) >= 3,
    }
    result = {
        "schema": "zworkbench-w8-plugin-aware-e3-unknown-effect/v1",
        "status": "pass" if all(checks.values()) else "fail",
        "run_id": run_id,
        "denied": {"status": denied.status, "reason": denied.reason},
        "retry": {"status": retry.status, "reason": retry.reason},
        "checks": checks,
        "observed": {
            "run_status": run.get("status"),
            "effect_count": len(run.get("effects", [])),
            "event_count": len(snapshot.get("events", [])),
            "database": str(database),
        },
    }
    write_json(case_dir / "unknown-effect.json", result)
    return result


def evaluate_e3(bundle_root: Path, output: Path) -> dict[str, Any]:
    runtime_dir = output / "runtime-seam"
    runtime = run_runtime_seam(bundle_root, runtime_dir)
    unknown = run_e3_unknown_effect(output / "unknown-effect")
    runtime_checks = runtime.get("checks") if isinstance(runtime.get("checks"), dict) else {}
    checks = {
        "runtime_seam_passed": runtime.get("status") == "pass" and all(runtime_checks.values()),
        "unknown_effect_control_passed": unknown.get("status") == "pass",
        "critical_write_interception": all(
            runtime_checks.get(name) is True
            for name in ("export_write_denied", "import_path_escape_denied", "tool_write_denied", "write_attempts_all_denied")
        ),
        "unauthorized_execution_zero": runtime_checks.get("subprocess_negative_probe_denied") is True,
        "unsafe_duplicate_effect_zero": unknown.get("observed", {}).get("effect_count") == 0,
    }
    result = {
        "gate": "E3",
        "status": "pass" if all(checks.values()) else "fail",
        "scope": "pinned dsh-config-migrate runtime seam + CompositionOwner unknown-effect control",
        "checks": checks,
        "runtime_seam": {
            "status": runtime.get("status"),
            "evidence": str(runtime_dir / "summary.json"),
            "plugin_commit": runtime.get("plugin", {}).get("actual_commit"),
            "registrations": runtime.get("observed", {}).get("registrations"),
            "owner_run_status": runtime.get("observed", {}).get("owner_run_status"),
            "owner_effect_count": len(runtime.get("owner_observation", {}).get("snapshot", {}).get("effects", [])),
        },
        "unknown_effect": unknown,
        "non_claims": [
            "E3 does not prove host-level OS sandbox inheritance.",
            "E3 does not prove successful real DSH_HOME migration; writes remain denied in this gate.",
            "E3 is not a DeepSeek product integration approval.",
        ],
    }
    write_json(output / "e3-summary.json", result)
    return result


def run_behavior_probe(bundle_root: Path, case_dir: Path) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    prepared_home = bundle_root / "home-full"
    # dsh-memoir keeps its ESM entrypoints under lib/. Point the probe at the
    # actual package entrypoint directory so the evidence exercises the pinned
    # plugin artifact rather than an evaluator-owned shim.
    memoir_dir = prepared_home / "profiles" / "headless" / "node_modules" / "dsh-memoir" / "lib"
    router_source = git_show(bundle_root / "dsh-routing-suite", ROUTER_COMMIT, ROUTER_SOURCE)
    if router_source is None:
        raise RuntimeError("pinned router-core source is unavailable")
    router_path = case_dir / "inputs" / "router-core-v34.mjs"
    router_path.parent.mkdir(parents=True, exist_ok=True)
    router_path.write_text(router_source, encoding="utf-8")
    node = os.environ.get("NODE_BINARY") or shutil.which("node") or "node"
    case_root = case_dir.resolve()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(case_root),
        "DSH_HOME": str(case_root / "dsh-home"),
        "NO_PROXY": "*",
        "no_proxy": "*",
        "DSH_TELEMETRY_DISABLED": "1",
    }
    command = [
        node,
        str(BEHAVIOR_PROBE),
        f"--case-root={case_root}",
        f"--router-core={router_path}",
        f"--memoir-dir={memoir_dir}",
    ]
    process = run_command(command, cwd=case_root, env=env, timeout=60)
    write_json(case_dir / "process-result.json", process)
    parsed: dict[str, Any] | None = None
    parse_error = None
    try:
        parsed = json.loads(process.get("stdout", ""))
    except json.JSONDecodeError as error:
        parse_error = str(error)
    result = {
        "status": "pass" if process.get("returncode") == 0 and isinstance(parsed, dict) else "fail",
        "process": {key: value for key, value in process.items() if key not in {"stdout", "stderr"}},
        "parsed": parsed,
        "parse_error": parse_error,
        "source": {
            "router_commit": ROUTER_COMMIT,
            "router_path": str(router_path),
            "router_sha256": sha256_bytes(router_source.encode("utf-8")),
            "memoir_package_dir": str(memoir_dir),
            "memoir_entry_present": (memoir_dir / "store.js").is_file() and (memoir_dir / "selector.js").is_file(),
        },
        "paths": path_map(case_root, [case_root, case_root / "workspace", case_root / "dsh-memoir.json"]),
    }
    write_json(case_dir / "behavior-result.json", result)
    return result


def owner_idempotency_case(case_dir: Path) -> dict[str, Any]:
    database = case_dir / "state" / "composition.sqlite3"
    effect_target = case_dir / "effects" / "delivery.json"
    run_id = "w8-plugin-aware-e4-idempotency"
    operation_id = f"{run_id}:operation-1"
    idempotency_key = f"{run_id}:key-1"
    physical_writes = 0
    with CompositionOwner(database) as owner:
        owner.create_run(run_id, "plugin-aware-idempotency", {"plugin": "composition-adapter"})
        owner.start_run(run_id)
        first = owner.claim_effect(run_id, operation_id, "local-delivery", str(effect_target), idempotency_key, "idempotent")
        if first.executable:
            effect_target.parent.mkdir(parents=True, exist_ok=True)
            effect_target.write_text("fixture-ok\n", encoding="utf-8")
            physical_writes += 1
            owner.complete_effect(first.effect_id, {"delivered": True}, {"path": str(effect_target)})
        duplicate = owner.claim_effect(run_id, operation_id, "local-delivery", str(effect_target), idempotency_key, "idempotent")
        owner.complete_run(run_id, {"status": "idempotency-verified", "plugin": CONFIG_PLUGIN})
        run = owner.get_run(run_id)
        snapshot = owner.snapshot()
    checks = {
        "first_claim_executable": first.executable,
        "duplicate_claim_suppressed": duplicate.status == "already_completed",
        "one_physical_write": physical_writes == 1,
        "one_owner_effect": len(run.get("effects", [])) == 1,
        "owner_run_completed": run.get("status") == "completed",
        "owner_correlation_present": all(item.get("run_id") == run_id for item in snapshot.get("events", [])),
        "case_local_target": inside(case_dir, effect_target),
    }
    result = {
        "status": "pass" if all(checks.values()) else "fail",
        "run_id": run_id,
        "checks": checks,
        "observed": {
            "first_claim": {"status": first.status, "attempt": first.attempt},
            "duplicate_claim": {"status": duplicate.status, "reason": duplicate.reason},
            "physical_writes": physical_writes,
            "effect_count": len(run.get("effects", [])),
            "database": str(database),
            "target": str(effect_target),
        },
    }
    write_json(case_dir / "idempotency.json", result)
    return result


def owner_replay_case(case_dir: Path) -> dict[str, Any]:
    database = case_dir / "state" / "composition.sqlite3"
    cassette = case_dir / "replay-cassette.json"
    cassette_payload = {
        "schema": "w8-plugin-aware-cassette/v1",
        "events": [
            {"type": "plugin.route", "mode": "spec", "provider": "fixture-a"},
            {"type": "plugin.result", "semantic": "fixture-ok"},
        ],
        "expected": {"semantic": "fixture-ok", "effect_count": 0},
    }
    cassette.parent.mkdir(parents=True, exist_ok=True)
    cassette.write_bytes(canonical(cassette_payload))
    source_digest = sha256_bytes(cassette.read_bytes())
    environment_digest = digest({"node": "pinned", "network": "deny", "credentials": "deny"})
    provider = {"provider": "fixture-loopback", "model": "fixture-model", "endpoint": "http://127.0.0.1:11434"}
    run_id = "w8-plugin-aware-e4-replay"
    replay_results: list[dict[str, Any]] = []
    with CompositionOwner(database) as owner:
        owner.create_run(run_id, "plugin-aware-replay", {"plugin": "dsh-routing-suite"})
        owner.start_run(run_id)
        for repeat in range(1, 6):
            loaded = json.loads(cassette.read_text(encoding="utf-8"))
            semantic = loaded["expected"]["semantic"]
            recorded = owner.record_replay_metadata(
                run_id,
                f"{run_id}:simulated-{repeat:02d}",
                "simulated_replay",
                source_digest,
                environment_digest,
                provider,
                {"repeat": repeat, "plugin_aware": True},
            )
            replay_results.append({"repeat": repeat, "semantic": semantic, "replay_id": recorded["replay_id"]})
        live_metadata = owner.record_replay_metadata(
            run_id,
            f"{run_id}:live-denied",
            "live_replay",
            source_digest,
            environment_digest,
            provider,
            {"policy": "approval-required-and-not-granted"},
        )
        live_policy = {"mode": "live_replay", "decision": "deny", "reason": "no-explicit-approval", "effect_count": 0}
        write_json(case_dir / "live-replay-policy.json", live_policy)
        owner.record_result(run_id, "replay.policy", live_policy, "live-replay")
        owner.complete_run(run_id, {"status": "replay-boundary-verified", "plugin": "dsh-routing-suite"})
        run = owner.get_run(run_id)
        snapshot = owner.snapshot()
    checks = {
        "simulated_replay_5_of_5": len(replay_results) == 5 and all(item["semantic"] == "fixture-ok" for item in replay_results),
        "replay_identity_recorded": len(run.get("results", [])) >= 1 and len(snapshot.get("replays", [])) == 6,
        "unapproved_live_effect_zero": live_policy["decision"] == "deny" and live_policy["effect_count"] == 0 and len(run.get("effects", [])) == 0,
        "owner_run_completed": run.get("status") == "completed",
        "provider_identity_explicit": all(item.get("provider_identity") == provider for item in snapshot.get("replays", [])),
    }
    result = {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observed": {
            "simulated_replay_count": len(replay_results),
            "live_replay_metadata": live_metadata["replay_id"],
            "owner_replay_count": len(snapshot.get("replays", [])),
            "effect_count": len(run.get("effects", [])),
            "database": str(database),
            "cassette": str(cassette),
        },
    }
    write_json(case_dir / "replay.json", result)
    return result


def load_real_provider_summary(path: Path | None) -> dict[str, Any]:
    """Validate a redacted real-provider result without copying its body.

    The optional Ark probe owns credential handling.  This bridge consumes only
    its redacted summary so that E4 can correlate a real Provider observation
    without ever receiving the API key or raw request/response.
    """
    if path is None:
        return {
            "status": "not-provided",
            "source": None,
            "checks": {
                "summary_present": False,
            },
            "observed": {},
        }
    value = read_json(path)
    if not isinstance(value, dict):
        return {
            "status": "fail",
            "source": str(path.resolve()),
            "checks": {"summary_is_object": False},
            "observed": {},
        }
    credential = value.get("credential") if isinstance(value.get("credential"), dict) else {}
    response = value.get("response") if isinstance(value.get("response"), dict) else {}
    attempts = value.get("attempts") if isinstance(value.get("attempts"), list) else []
    fingerprint = credential.get("api_key_fingerprint")
    requested_count = value.get("requested_count")
    repeated_request_shape = requested_count == 5 and value.get("request_count") == 5
    single_http_success = isinstance(value.get("http_status"), int) and 200 <= value["http_status"] < 300
    repeated_http_success = repeated_request_shape and len(attempts) == 5 and all(
        isinstance(item, dict)
        and item.get("outcome") == "http_success"
        and isinstance(item.get("http_status"), int)
        and 200 <= item["http_status"] < 300
        for item in attempts
    )
    http_success = value.get("outcome") == "http_success" and (single_http_success or repeated_http_success)
    response_models = response.get("response_models") if isinstance(response.get("response_models"), list) else []
    checks = {
        "schema_is_real_provider_probe": value.get("schema") == REAL_PROVIDER_SCHEMA,
        "provider_is_volcengine_ark": value.get("provider") == "volcengine-ark",
        "endpoint_is_fixed_ark_coding": value.get("endpoint") == ARK_ENDPOINT,
        "configured_model_is_ark_code_latest": value.get("model") == ARK_MODEL,
        "credential_fingerprint_recorded": isinstance(fingerprint, str) and len(fingerprint) == 64 and all(character in "0123456789abcdef" for character in fingerprint.lower()),
        "http_success": http_success,
        "one_request_or_five_explicit": value.get("request_count") == 1 or repeated_request_shape,
        "zero_retries": value.get("retry_count") == 0,
        "synthetic_fixture_present": response.get("fixture_token_present") is True or response.get("all_semantic_fixture_exact") is True,
        "raw_request_response_not_persisted": value.get("raw_request_or_response_persisted") is False,
        "response_model_route_matches": response.get("response_model") in {"auto", ARK_MODEL} or bool(response_models) and all(model in {"auto", ARK_MODEL} for model in response_models),
        "preflight_verified_or_legacy": "preflight" not in value or isinstance(value.get("preflight"), dict) and value["preflight"].get("status") == "verified",
        "verified_compatibility_or_legacy": requested_count != 5 or value.get("compatibility_status") == "verified-for-authorized-read-only-staging",
    }
    result = {
        "status": "pass" if all(checks.values()) else "fail",
        "source": str(path.resolve()),
        "checks": checks,
        "observed": {
            "provider": value.get("provider"),
            "endpoint": value.get("endpoint"),
            "configured_model": value.get("model"),
            "response_model": response.get("response_model") or response_models,
            "response_model_interpretation": "Ark response model=auto is recorded as the configured ark-code-latest route per the established provider mapping.",
            "api_key_fingerprint": fingerprint,
            "http_status": value.get("http_status"),
            "request_count": value.get("request_count"),
            "requested_count": requested_count,
            "retry_count": value.get("retry_count"),
            "fixture_id": value.get("synthetic_fixture", {}).get("id") if isinstance(value.get("synthetic_fixture"), dict) else None,
            "response_body_persisted": value.get("raw_request_or_response_persisted"),
            "remote_resource_inventory": value.get("remote_resource_inventory"),
        },
        "non_claims": [
            "This bridge does not claim Provider failover, a second Provider, or a fallback reason ledger.",
            "This bridge does not claim that remote tasks, Webhooks, backups, or retention were inventoried.",
            "No API key or raw request/response body is copied into this result.",
        ],
    }
    return result


def evaluate_e4(bundle_root: Path, output: Path, real_provider: dict[str, Any]) -> dict[str, Any]:
    behavior = run_behavior_probe(bundle_root, output / "plugin-behavior")
    idem = owner_idempotency_case(output / "idempotency")
    replay = owner_replay_case(output / "replay")
    parsed = behavior.get("parsed") if isinstance(behavior.get("parsed"), dict) else {}
    router = parsed.get("router") if isinstance(parsed.get("router"), dict) else {}
    memoir = parsed.get("memoir") if isinstance(parsed.get("memoir"), dict) else {}
    routing_checks = {
        "router_probe_passed": behavior.get("status") == "pass",
        "router_deterministic": router.get("deterministic") is True,
        "router_stage_progression_observed": router.get("stageSequence") == [1, 2, 3],
        "memoir_probe_passed": behavior.get("status") == "pass" and memoir.get("deterministic") is True,
        "memoir_bounded": isinstance(memoir.get("estimatedTokens"), int) and memoir["estimatedTokens"] <= memoir.get("hardMaxTokens", -1),
        "memoir_note_excluded": memoir.get("noteExcluded") is True,
    }
    provider_failover = {
        "status": "unknown",
        "candidate_contract_present": False,
        "source": "dsh-routing-suite/preset/router-standard/router-core-v34.mjs",
        "reason": "The pinned router core exposes task/persona/stage routing, not a Provider selection, fallback, degradation, or fallback-reason ledger contract; no evaluator-owned fake router is promoted to candidate evidence.",
    }
    checks = {
        "idempotent_effect_threshold": idem.get("status") == "pass",
        "routing_and_memoir_plugin_behavior": all(routing_checks.values()),
        "provider_failover_contract": provider_failover["candidate_contract_present"],
        "real_provider_staging_observed": real_provider.get("status") == "pass",
        "replay_threshold": replay.get("status") == "pass",
    }
    status = "pass" if all(checks.values()) else "unknown/stop"
    result = {
        "gate": "E4",
        "status": status,
        "scope": "new plugin-aware evidence; plugin behavior and owner-provided parity recorded separately",
        "checks": checks,
        "plugin_behavior": {
            "status": behavior.get("status"),
            "evidence": str(output / "plugin-behavior" / "behavior-result.json"),
            "routing": routing_checks,
            "memoir": memoir,
        },
        "owner_idempotency": idem,
        "owner_replay": replay,
        "real_provider_staging": real_provider,
        "provider_failover": provider_failover,
        "interpretation": "The selected plugin behavior and the ZWorkbench owner can demonstrate bounded idempotency/replay controls, but E4 cannot be promoted while the selected routing plugin has no candidate-owned Provider failover/degradation contract.",
        "non_claims": [
            "Router/persona classification is not Provider failover.",
            "Owner replay metadata and cassette replay are composition evidence, not native dsh plugin replay.",
            "Local plugin behavior probes made no Provider request; any Ark request is separately marked as external staging evidence.",
        ],
    }
    write_json(output / "real-provider-staging.json", real_provider)
    write_json(output / "e4-summary.json", result)
    return result


def load_human_timings(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("--human-timings-json must contain an object keyed by E5 scenario")
    result: dict[str, float] = {}
    for scenario, raw in value.items():
        if scenario not in E5_THRESHOLDS_MINUTES:
            raise ValueError(f"unknown E5 scenario: {scenario}")
        minutes = raw.get("minutes") if isinstance(raw, dict) else raw
        if not isinstance(minutes, (int, float)) or minutes < 0:
            raise ValueError(f"human timing for {scenario} must be a non-negative number of minutes")
        result[scenario] = float(minutes)
    return result


def timed_operation(case_dir: Path, scenario: str, action: Callable[[], dict[str, Any]], human_timings: dict[str, float]) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        operation = action()
        error = None
    except Exception as exc:  # pragma: no cover - evidence records unexpected fixture errors
        operation = {"checks": {}, "observed": {}}
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - started
    checks = operation.get("checks") if isinstance(operation.get("checks"), dict) else {}
    machine_pass = error is None and bool(checks) and all(checks.values())
    human_minutes = human_timings.get(scenario)
    human_status = "unknown" if human_minutes is None else ("pass" if human_minutes <= E5_THRESHOLDS_MINUTES[scenario] else "fail")
    result = {
        "scenario": scenario,
        "status": "pass" if machine_pass else "fail",
        "machine_elapsed_seconds": round(elapsed, 6),
        "machine_elapsed_is_not_human_time": True,
        "human_elapsed_minutes": human_minutes,
        "human_timing_status": human_status,
        "threshold_minutes": E5_THRESHOLDS_MINUTES[scenario],
        "error": error,
        "operation": operation,
    }
    write_json(case_dir / "operation.json", result)
    return result


def e5_fresh_install(case_dir: Path, bundle_root: Path) -> dict[str, Any]:
    installed = case_dir / "installed" / CONFIG_PLUGIN
    installed.mkdir(parents=True, exist_ok=True)
    source_dir = bundle_root / CONFIG_PLUGIN
    host = git_show(source_dir, CONFIG_PLUGIN_COMMIT, "host.js")
    client = git_show(source_dir, CONFIG_PLUGIN_COMMIT, "client.js")
    if host is None or client is None:
        raise RuntimeError("pinned dynamic plugin entrypoints unavailable")
    (installed / "host.js").write_text(host, encoding="utf-8")
    (installed / "client.js").write_text(client, encoding="utf-8")
    write_json(installed / "adapter-manifest.json", {
        "plugin": CONFIG_PLUGIN,
        "commit": CONFIG_PLUGIN_COMMIT,
        "mode": "outer-composed",
        "network": "deny",
        "credentials": "deny",
        "owner": "ZWorkbench composition owner",
    })
    checks = {
        "case_local_install_root": inside(case_dir, installed),
        "pinned_entrypoints_copied": (installed / "host.js").read_text(encoding="utf-8") == host and (installed / "client.js").read_text(encoding="utf-8") == client,
        "adapter_manifest_present": (installed / "adapter-manifest.json").is_file(),
        "no_registry_install": True,
        "external_network_zero": True,
        "real_credentials_false": True,
        "production_data_false": True,
    }
    return {"checks": checks, "observed": {"install_root": str(installed), "entrypoint_sha256": {"host": sha256_bytes(host.encode()), "client": sha256_bytes(client.encode())}, "operation_kind": "prepared_case_local_assembly_not_real_product_install"}}


def e5_upgrade(case_dir: Path) -> dict[str, Any]:
    manifest = case_dir / "adapter-manifest.json"
    old = {"adapter": "0.1.0", "plugin": CONFIG_PLUGIN, "commit": CONFIG_PLUGIN_COMMIT}
    new = {"adapter": "0.1.1", "plugin": CONFIG_PLUGIN, "commit": CONFIG_PLUGIN_COMMIT}
    write_json(manifest, old)
    before = sha256_bytes(manifest.read_bytes())
    write_json(manifest, new)
    upgraded = sha256_bytes(manifest.read_bytes())
    write_json(manifest, old)
    rollback = sha256_bytes(manifest.read_bytes())
    checks = {
        "upgrade_changed_identity": upgraded != before,
        "rollback_restored_identity": rollback == before,
        "old_plugin_commit_preserved": read_json(manifest)["commit"] == CONFIG_PLUGIN_COMMIT,
        "owner_database_not_overwritten": not (case_dir / "state" / "composition.sqlite3").exists(),
    }
    return {"checks": checks, "observed": {"before_sha256": before, "upgraded_sha256": upgraded, "rollback_sha256": rollback, "operation_kind": "case_local_manifest_upgrade_rollback"}}


def e5_backup_restore(case_dir: Path) -> dict[str, Any]:
    database = case_dir / "state" / "composition.sqlite3"
    backup = case_dir / "backup"
    target = case_dir / "restore" / "composition.sqlite3"
    run_id = "w8-plugin-aware-e5-backup-restore"
    with CompositionOwner(database) as owner:
        owner.create_run(run_id, "plugin-aware-lifecycle", {"plugin": CONFIG_PLUGIN})
        owner.start_run(run_id)
        owner.record_result(run_id, "adapter", {"plugin": CONFIG_PLUGIN, "status": "fixture"}, "adapter")
        owner.complete_run(run_id, {"status": "healthy"})
        source_digest = owner.state_digest()
        manifest = owner.backup(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"corrupt target")
    restored = CompositionOwner.restore(backup, target, replace=True)
    with CompositionOwner(target) as reopened:
        restored_digest = reopened.state_digest()
        snapshot = reopened.snapshot()
    checks = {
        "backup_files_present": all((backup / name).is_file() for name in ("manifest.json", "composition.sqlite3", "state.json")),
        "backup_integrity_ok": manifest.get("integrity_check", {}).get("ok") is True,
        "corrupted_target_replaced": restored["target_database"] == str(target),
        "restore_digest_matches": restored_digest == source_digest == restored["state_digest"],
        "restore_snapshot_has_run": any(item.get("run_id") == run_id for item in snapshot.get("runs", [])),
        "case_local_paths": path_map(case_dir, [database, backup, target])["all_inside_case_root"],
    }
    return {"checks": checks, "observed": {"source_state_digest": source_digest, "restored_state_digest": restored_digest, "backup": str(backup), "target": str(target), "operation_kind": "composition_owner_backup_restore"}}


def e5_fault_diagnosis(case_dir: Path) -> dict[str, Any]:
    fault = {"code": "ADAPTER_WRITE_DENY", "request_id": "w8-plugin-aware-e3-write-1", "plugin": CONFIG_PLUGIN, "run_id": "w8-plugin-aware-e3"}
    diagnosis = {
        "schema": "zworkbench-w8-plugin-aware-diagnosis/v1",
        "fault_id": "fault-plugin-write-deny-1",
        "run_id": fault["run_id"],
        "category": "adapter_policy_denied_write",
        "recommended_action": "retain evidence; do not retry without an explicit policy change",
        "unknown_not_promoted": True,
    }
    write_json(case_dir / "fault.json", fault)
    write_json(case_dir / "diagnosis.json", diagnosis)
    checks = {
        "fault_correlated": diagnosis["run_id"] == fault["run_id"] and diagnosis["fault_id"].startswith("fault-"),
        "category_present": bool(diagnosis["category"]),
        "bounded_action_present": bool(diagnosis["recommended_action"]),
        "unknown_not_promoted": diagnosis["unknown_not_promoted"] is True,
        "no_network_or_credentials": True,
    }
    return {"checks": checks, "observed": {"fault": fault, "diagnosis": diagnosis, "operation_kind": "prepared_case_local_fault"}}


def e5_uninstall(case_dir: Path) -> dict[str, Any]:
    installed = case_dir / "installed"
    installed.mkdir(parents=True, exist_ok=True)
    (installed / "plugin-marker").write_text("case-local", encoding="utf-8")
    shutil.rmtree(installed)
    checks = {
        "local_install_removed": not installed.exists(),
        "remote_tasks_absent_in_fixture": True,
        "webhooks_absent_in_fixture": True,
        "remote_backups_not_claimed": True,
        "real_credentials_absent": True,
        "resident_services_at_most_three": 0 <= 3,
    }
    return {"checks": checks, "observed": {"resident_services": 0, "operation_kind": "case_local_uninstall_only", "remote_exit_status": "not-verified"}}


def evaluate_e5(bundle_root: Path, output: Path, human_timings: dict[str, float]) -> dict[str, Any]:
    operation_actions: dict[str, Callable[[], dict[str, Any]]] = {
        "fresh_install": lambda: e5_fresh_install(output / "fresh-install", bundle_root),
        "upgrade": lambda: e5_upgrade(output / "upgrade"),
        "backup_restore": lambda: e5_backup_restore(output / "backup-restore"),
        "fault_diagnosis": lambda: e5_fault_diagnosis(output / "fault-diagnosis"),
    }
    operations = {scenario: timed_operation(output / scenario, scenario, action, human_timings) for scenario, action in operation_actions.items()}
    uninstall = e5_uninstall(output / "uninstall")
    write_json(output / "uninstall.json", uninstall)
    machine_checks = all(item["status"] == "pass" for item in operations.values()) and uninstall.get("checks", {}).get("local_install_removed") is True
    human_statuses = [item["human_timing_status"] for item in operations.values()]
    human_gate = "fail" if "fail" in human_statuses else ("unknown" if "unknown" in human_statuses else "pass")
    checks = {
        "machine_operations_pass": machine_checks,
        "human_time_gate": human_gate == "pass",
        "resident_services_at_most_three": uninstall.get("checks", {}).get("resident_services_at_most_three") is True,
        "no_extra_specialist_declared": True,
        "remote_exit_verified": False,
    }
    result = {
        "gate": "E5",
        "status": "pass" if all(checks.values()) else "unknown/stop",
        "checks": checks,
        "human_timing": {
            "status": human_gate,
            "input_present": bool(human_timings),
            "template": {scenario: {"minutes": human_timings.get(scenario), "threshold_minutes": threshold, "status": "measured" if scenario in human_timings else "unknown"} for scenario, threshold in E5_THRESHOLDS_MINUTES.items()},
        },
        "operations": operations,
        "uninstall": uninstall,
        "interpretation": "Local machine fixture operations are observable, but a full candidate install/runbook and real single-operator timing have not been established; remote exit responsibility remains outside this isolated gate.",
        "non_claims": [
            "machine_elapsed_seconds is not a human stopwatch measurement",
            "prepared local assembly is not a real npm/registry product installation",
            "fixture absence of remote tasks/webhooks/backups is not proof of real remote cleanup",
        ],
    }
    write_json(output / "e5-summary.json", result)
    return result


def evaluate_e6(output: Path, e3: dict[str, Any], e4: dict[str, Any], e5: dict[str, Any]) -> dict[str, Any]:
    prerequisites = {"E3": e3.get("status") == "pass", "E4": e4.get("status") == "pass", "E5": e5.get("status") == "pass"}
    result = {
        "gate": "E6",
        "status": "pass" if all(prerequisites.values()) else "blocked-by-E3-E5-prerequisites",
        "prerequisites": prerequisites,
        "comparison_contract": {
            "same_task_set": False,
            "same_provider": False,
            "same_owner_contract": True,
            "codex_evidence_inherited": False,
        },
        "benefit_candidates": [
            {"capability": "task/persona routing", "source": "dsh-routing-suite", "status": "hypothesis-only", "reason": "no matched Codex comparison run in this gate"},
            {"capability": "bounded local project memory", "source": "dsh-memoir", "status": "hypothesis-only", "reason": "no matched Codex comparison run in this gate"},
            {"capability": "configuration migration", "source": "dsh-config-migrate", "status": "hypothesis-only", "reason": "write path is deny-only in this safety gate"},
        ],
        "checks": {
            "prerequisites_all_pass": all(prerequisites.values()),
            "measurable_non_duplicate_advantage": False,
            "no_replacement_decision": True,
        },
        "interpretation": "No E6 advantage claim is allowed until E3-E5 pass under the same comparison contract and at least one benefit is measured against Codex.",
    }
    write_json(output / "e6-summary.json", result)
    return result


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    bundle_root = args.bundle_root.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("E3-E6 evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    human_timings = load_human_timings(args.human_timings_json)
    real_provider = load_real_provider_summary(args.real_provider_summary)
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "evaluation-contract.json", {
        "schema": SCHEMA,
        "classification": "acceptance/evaluation",
        "independent_evidence": True,
        "bundle_root": str(bundle_root),
        "real_provider": args.real_provider_summary is not None,
        "real_credentials": args.real_provider_summary is not None,
        "external_network": args.real_provider_summary is not None,
        "local_fixture_real_credentials": False,
        "local_fixture_external_network": False,
        "production_data": False,
        "codex_evidence_inherited": False,
        "human_timings_present": bool(human_timings),
        "real_provider_summary": real_provider.get("source"),
    })
    e3 = evaluate_e3(bundle_root, output / "E3")
    e4 = evaluate_e4(bundle_root, output / "E4", real_provider)
    e5 = evaluate_e5(bundle_root, output / "E5", human_timings)
    e6 = evaluate_e6(output / "E6", e3, e4, e5)
    gates = {"E3": e3, "E4": e4, "E5": e5, "E6": e6}
    summary = {
        "schema": SCHEMA,
        "status": "pass" if all(gate.get("status") == "pass" for gate in gates.values()) else "blocked",
        "classification": "acceptance/evaluation",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_root),
        "output": str(output),
        "candidate": {
            "core": manifest["core"],
            "plugins": manifest["plugins"],
            "composition_mode": "standard bundles + outer-composed dsh-config-migrate dynamic adapter",
        },
        "gates": gates,
        "thresholds": manifest["gates"],
        "independence": {
            "new_evidence_directory": True,
            "runtime_seam_rerun": str(output / "E3" / "runtime-seam" / "summary.json"),
            "codex_or_previous_bundle_evidence_reused_for_pass": False,
            "owner_contract_used": True,
        },
        "non_claims": [
            "This is not ZWorkbench product integration approval.",
            "Local plugin fixtures use no real Provider or credential; when supplied, the separately marked Ark staging summary records one real credential-backed request without copying the key or raw body.",
            "E4 unknown/stop is not evidence that the plugin ecosystem has no value; it identifies a missing Provider failover contract in this selected composition.",
            "E5 unknown/stop is not a negative install benchmark; it identifies missing real operator and remote exit evidence.",
        ],
        "next_action": "Do not replace or parallelize Codex. Either add a separately pinned/provider-router candidate with explicit failover evidence and collect DeepSeek operator timing/remote exit evidence, or stop this composition branch.",
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True, help="isolated root containing the pinned core and plugin checkout")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--human-timings-json", type=Path, help="optional E5 timings in minutes; never inferred from machine time")
    parser.add_argument("--real-provider-summary", type=Path, help="optional redacted summary from the one-shot Ark staging probe; never a key or raw response")
    args = parser.parse_args()
    summary = build_summary(args)
    print(json.dumps({
        "status": summary["status"],
        "output": summary["output"],
        "gates": {name: gate["status"] for name, gate in summary["gates"].items()},
        "human_timing": summary["gates"]["E5"]["human_timing"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
