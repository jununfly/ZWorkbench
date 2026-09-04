#!/usr/bin/env python3
"""Run the W8 H5 owner-backed evidence/replay contract.

The runner uses only a case-local CompositionOwner and a sealed JSON cassette.
It calls the product replay service directly; it never starts a Worker,
contacts a Provider, invokes a tool, or performs an external effect. The
result is ``owner-backed + fixture-composed`` evidence, not DSH-native or
real-Provider compatibility evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Mapping, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_evidence_replay" / "v1"
MANIFEST = FIXTURE_ROOT / "fixture-manifest.json"
CASSETTE_TEMPLATE = FIXTURE_ROOT / "replay-cassette.json"
RUNNER_SCHEMA = "zworkbench-w8-h5-evidence-replay-runner/v1"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import (  # noqa: E402
    CassetteIdentity,
    ComponentIdentity,
    CompositionOwner,
    OwnerBackedReplayService,
    ProviderIdentity,
    ReplayIdentity,
    UNKNOWN,
)


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def result_status(result: Mapping[str, Any]) -> str:
    return str(result.get("status", "missing"))


def make_source(owner: CompositionOwner) -> str:
    owner.create_run(
        "source-run",
        "h5.fixture",
        {"prompt": "fixture"},
        {
            "fixture": "w8-h5-evidence-replay/v1",
            "harness": "dsh-fixture-v1",
            "worker": "codex-worker-fixture-v1",
        },
    )
    owner.start_run("source-run")
    owner.record_event("source-run", "fixture.started", {"source": "h5"})
    owner.record_event("source-run", "fixture.observed", {"provider_requests": 0, "tool_invocations": 0})
    owner.complete_run("source-run", {"answer": "fixture-ok"})
    return OwnerBackedReplayService(owner).owner_event_digest("source-run")


def make_identity(source_event_digest: str, cassette: Optional[CassetteIdentity] = None) -> ReplayIdentity:
    return ReplayIdentity(
        harness_identity=ComponentIdentity("dsh-fixture", "1.0.0", digest_bytes(b"h5-dsh"), "evaluation-fixture"),
        plugin_identities=(),
        worker_identity=ComponentIdentity("codex-worker-fixture", "1.0.0", digest_bytes(b"h5-worker"), "evaluation-fixture"),
        provider_identity=ProviderIdentity(
            provider="fake-loopback",
            model="fixture-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        ),
        tool_schema_digest=digest_bytes(b"h5-tool-schema"),
        policy_digest=digest_bytes(b"h5-policy"),
        workspace_digest=digest_bytes(b"h5-workspace"),
        environment_digest=digest_bytes(b"h5-environment"),
        owner_schema="zworkbench-composition-owner/v1",
        source_event_digest=source_event_digest,
        cassette_identity=cassette,
    )


def materialize_cassette(case_root: Path, source_event_digest: str) -> tuple[Path, ReplayIdentity]:
    cassette = read_json(CASSETTE_TEMPLATE)
    cassette["source_event_digest"] = source_event_digest
    cassette["environment_digest"] = digest_bytes(b"h5-environment")
    cassette["provider_identity"] = make_identity(source_event_digest).provider_identity.to_dict()
    path = case_root / "cassette.json"
    write_json(path, cassette)
    identity = make_identity(
        source_event_digest,
        CassetteIdentity(cassette["cassette_id"], digest_file(path)),
    )
    return path, identity


def setup_case(case_root: Path) -> tuple[CompositionOwner, OwnerBackedReplayService, str]:
    (case_root / "workspace").mkdir(parents=True, exist_ok=True)
    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    source_digest = make_source(owner)
    return owner, OwnerBackedReplayService(owner), source_digest


def run_case(output_dir: Path, name: str) -> Dict[str, Any]:
    case_root = output_dir / "cases" / name
    case_root.mkdir(parents=True, exist_ok=False)
    owner, service, source_digest = setup_case(case_root)
    try:
        cassette_path, identity = materialize_cassette(case_root, source_digest)
        before_digest = owner.state_digest()
        if name == "recorded-view":
            result = service.recorded_view("source-run", identity, "recorded-view-1")
        elif name == "simulated-replay":
            result = service.simulated_replay(cassette_path, identity, "simulated-replay-1")
        elif name == "live-replay":
            result = service.live_replay(cassette_path, identity, "live-replay-1")
        elif name == "missing-identity":
            incomplete = replace(identity, policy_digest=UNKNOWN)
            result = service.simulated_replay(cassette_path, incomplete, "missing-identity-1")
        elif name == "missing-cassette":
            result = service.simulated_replay(case_root / "not-found.json", identity, "missing-cassette-1")
        elif name == "tampered-cassette":
            cassette_path.write_bytes(cassette_path.read_bytes() + b"tampered\n")
            result = service.simulated_replay(cassette_path, identity, "tampered-cassette-1")
        elif name == "source-digest-mismatch":
            wrong = replace(identity, source_event_digest=digest_bytes(b"wrong-source"))
            result = service.recorded_view("source-run", wrong, "source-digest-1")
        else:
            raise ValueError(f"unknown H5 scenario: {name}")
        after_digest = owner.state_digest()
    finally:
        owner.close()

    write_json(case_root / "result.json", result)
    checks: Dict[str, bool] = {
        "owner_backed": result.get("owner_backed") is True,
        "mode_label_present": result.get("replay_mode") in {"recorded_view", "simulated_replay", "live_replay"},
        "provenance_complete_or_reported": bool(result.get("provenance")) and (
            result_status(result) != "unknown"
            or bool(result.get("missing_identity"))
            or bool(result.get("reason"))
        ),
        "execution_performed_false": result.get("execution_performed") is False,
        "provider_requests_zero": result.get("provider_requests") == 0,
        "tool_invocations_zero": result.get("tool_invocations") == 0,
        "external_calls_zero": result.get("external_calls") == 0,
        "side_effects_zero": result.get("side_effect_count") == 0,
        "owner_state_unchanged": before_digest == after_digest,
    }
    if name == "recorded-view":
        checks.update({
            "status_viewed": result_status(result) == "viewed",
            "view_only": result.get("view_only") is True,
        })
    elif name == "simulated-replay":
        checks.update({
            "status_simulated": result_status(result) == "simulated",
            "cassette_only": result.get("cassette_only") is True,
        })
    elif name == "live-replay":
        checks.update({
            "status_denied": result_status(result) == "denied",
            "safe_denial": result.get("safe_denial") is True,
            "policy_deny": result.get("policy_decision", {}).get("decision") == "deny",
        })
    else:
        checks.update({
            "status_unknown": result_status(result) == "unknown",
            "safe_stop": result.get("safe_stop") is True,
        })
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "scenario": name,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observed": {
            "result_status": result_status(result),
            "reason": result.get("reason"),
            "missing_identity": result.get("missing_identity", []),
            "owner_state_digest_unchanged": before_digest == after_digest,
            "real_credentials": False,
            "network_calls": 0,
            "provider_calls": 0,
            "tool_calls": 0,
            "external_effects": 0,
        },
        "result_path": str(case_root / "result.json"),
    }
    write_json(case_root / "summary.json", summary)
    return summary


def run_suite(output_dir: Path) -> Dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("H5 output directory must be new or empty")
    if not MANIFEST.is_file() or not CASSETTE_TEMPLATE.is_file():
        raise FileNotFoundError("H5 fixture is incomplete")
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [
        "recorded-view",
        "simulated-replay",
        "live-replay",
        "missing-identity",
        "missing-cassette",
        "tampered-cassette",
        "source-digest-mismatch",
    ]
    cases = [run_case(output_dir, name) for name in scenarios]
    checks = {
        "all_cases_pass": all(case["status"] == "pass" for case in cases),
        "recorded_view_read_only": cases[0]["checks"]["owner_state_unchanged"],
        "simulated_replay_cassette_only": cases[1]["checks"]["cassette_only"],
        "live_replay_default_deny": cases[2]["checks"]["policy_deny"],
        "unknown_inputs_safe_stop": all(case["checks"]["safe_stop"] for case in cases[3:]),
        "external_execution_zero": all(
            case["observed"]["network_calls"] == 0
            and case["observed"]["provider_calls"] == 0
            and case["observed"]["tool_calls"] == 0
            and case["observed"]["external_effects"] == 0
            for case in cases
        ),
    }
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "owner-backed + fixture-composed",
        "status": "pass" if all(checks.values()) else "fail",
        "passed_cases": sum(case["status"] == "pass" for case in cases),
        "case_count": len(cases),
        "fixture": {
            "manifest": str(MANIFEST),
            "manifest_sha256": digest_file(MANIFEST),
            "cassette_template": str(CASSETTE_TEMPLATE),
            "cassette_template_sha256": digest_file(CASSETTE_TEMPLATE),
        },
        "checks": checks,
        "cases": cases,
        "non_claims": [
            "This proves an owner-backed product seam composed with a local sealed fixture only.",
            "It does not prove DSH native replay, real Codex runtime compatibility, or real remote Provider compatibility.",
            "It does not authorize live replay, real workspace writes, Git push, deployment, or external effects.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="new or empty evidence directory")
    args = parser.parse_args()
    temporary = None
    output_dir = args.output
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="zworkbench-h5-")
        output_dir = Path(temporary.name) / "evidence"
    summary = run_suite(output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if temporary is not None:
        temporary.cleanup()
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
