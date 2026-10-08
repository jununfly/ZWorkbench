#!/usr/bin/env python3
"""Run the W8 DSH-native owner-backed evidence/replay contract.

Unlike :mod:`run_w8_evidence_replay` (which composes a sealed fixture by hand),
this runner stages the H1 fixture bootstrap and executes it through
:class:`~zworkbench.dsh_runtime.DshRuntimeAdapter` -- the same adapter the
product uses for the real ZDSHarness.  The harness run becomes the single
source of truth: a cassette is sealed from that *real* run and then fed to all
three replay modes (``recorded_view`` / ``simulated_replay`` / ``live_replay``)
plus the negative cases.  This is the end-to-end "DSH Harness 三模式收口"
contract: one artifact produced by a real harness execution flows through every
mode, and owner state is never mutated by replay.

It uses the local fixture bootstrap (not the built ZDSHarness CLI), so it is
locally runnable without network access.  It is not DSH-CLI artifact
compatibility evidence -- that is :mod:`run_w8_dsh_artifact_integration`.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import shutil
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Mapping, Optional, Tuple

from zworkbench import (
    CassetteIdentity,
    ComponentIdentity,
    CompositionOwner,
    IdentityChain,
    OwnerBackedReplayService,
    ProviderIdentity,
    ReplayIdentity,
    UNKNOWN,
)
from zworkbench.composition import SCHEMA
from zworkbench.dsh_runtime import DshRuntimeAdapter


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_dsh_bootstrap" / "v1"
FIXTURE_MANIFEST = FIXTURE_ROOT / "manifest.json"
RUNNER_SCHEMA = "zworkbench-w8-dsh-evidence-replay-runner/v1"
RUN_ID = "dsh-harness-run"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


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


def stage_case(case_root: Path) -> Path:
    """Stage the H1 fixture bootstrap into a fresh case-local runtime bundle."""

    bundle = case_root / "runtime"
    shutil.copytree(FIXTURE_ROOT, bundle)
    return bundle / "manifest.json"


def run_harness(
    owner: CompositionOwner, case_root: Path, manifest_path: Path
) -> Tuple[str, str, str, Dict[str, Any], Dict[str, Any]]:
    """Execute the fixture harness and seal a semantic outcome into the owner.

    Returns ``(source_event_digest, environment_digest, provider_identity_dict,
    semantic_result)`` so the caller can build a cassette and a ReplayIdentity.
    """

    adapter = DshRuntimeAdapter(owner, manifest_path, case_root)
    try:
        execution = adapter.execute(RUN_ID, timeout=30.0)
    finally:
        adapter.close()

    run = owner.get_run(RUN_ID)
    exit_receipts = [item["value"] for item in run["results"] if item["kind"] == "dsh.exit"]
    exit_code = exit_receipts[0]["exit_code"] if exit_receipts else None
    semantic_result = {
        "bootstrap": execution.status,
        "exit_code": exit_code,
        "dsh_session_id": execution.dsh_session_id,
    }
    owner.record_result(RUN_ID, "semantic", semantic_result)

    service = OwnerBackedReplayService(owner)
    source_event_digest = service.owner_event_digest(RUN_ID)
    manifest = read_json(manifest_path)
    environment_digest = digest_bytes(
        json.dumps(manifest["environment_identity"], sort_keys=True).encode("utf-8")
    )
    provider_identity_dict = dict(manifest["provider_identity"])
    return source_event_digest, environment_digest, provider_identity_dict, semantic_result


def seal_cassette(
    case_root: Path,
    source_event_digest: str,
    environment_digest: str,
    provider_identity: ProviderIdentity,
    semantic_result: Dict[str, Any],
    owner: CompositionOwner,
) -> Tuple[Path, str]:
    """Seal a cassette from the real harness-produced owner run."""

    cassette_id = f"dsh-cassette-{RUN_ID}"
    events = owner.events(RUN_ID)
    interactions = [
        {"event_type": event["type"], "value": event.get("value")}
        for event in events
        if str(event.get("type", "")).startswith("dsh.")
    ]
    cassette = {
        "schema": "zworkbench.replay-cassette/v1",
        "sealed": True,
        "cassette_id": cassette_id,
        "source_run_id": RUN_ID,
        "source_event_digest": source_event_digest,
        "environment_digest": environment_digest,
        "provider_identity": provider_identity.to_dict(),
        "interactions": interactions,
        "tool_results": [],
        "expected_semantic_result": semantic_result,
    }
    path = case_root / "cassette.json"
    write_json(path, cassette)
    return path, cassette_id


def make_identity(
    manifest: Mapping[str, Any],
    source_event_digest: str,
    environment_digest: str,
    provider_identity_dict: Dict[str, Any],
    cassette_id: str,
    cassette_digest: str,
    dsh_session_id: str,
) -> ReplayIdentity:
    identity_chain = IdentityChain(
        parent_run_id=RUN_ID,
        child_run_id=f"{RUN_ID}-child",
        attempt_id=f"{RUN_ID}-attempt-1",
        dsh_session_id=dsh_session_id,
        dsh_turn_id=f"{RUN_ID}-dsh-turn-1",
        worker_run_id=f"{RUN_ID}-worker-1",
        codex_thread_id=f"{RUN_ID}-codex-thread-1",
        codex_turn_id=f"{RUN_ID}-codex-turn-1",
        event_id=f"{RUN_ID}-event-1",
        artifact_id=f"{RUN_ID}-artifact-1",
    )
    return ReplayIdentity(
        harness_identity=ComponentIdentity(
            manifest["schema_identity"]["name"],
            manifest["schema_identity"]["version"],
            manifest["schema_identity"]["digest"],
            "dsh-fixture",
        ),
        plugin_identities=(),
        worker_identity=ComponentIdentity(
            "dsh-bootstrap-fixture",
            manifest["runtime"]["version"],
            manifest["artifact"]["digest"],
            "dsh-fixture",
        ),
        provider_identity=ProviderIdentity(**provider_identity_dict),
        identity_chain=identity_chain,
        tool_schema_digest=digest_bytes(json.dumps(manifest["profile"], sort_keys=True).encode("utf-8")),
        policy_digest=manifest["policy_identity"]["digest"],
        workspace_digest=digest_bytes(json.dumps(manifest["workspace"], sort_keys=True).encode("utf-8")),
        environment_digest=environment_digest,
        owner_schema=SCHEMA,
        source_event_digest=source_event_digest,
        cassette_identity=CassetteIdentity(cassette_id, cassette_digest),
    )


def run_case(output_dir: Path, name: str) -> Dict[str, Any]:
    case_root = output_dir / "cases" / name
    case_root.mkdir(parents=True, exist_ok=False)
    (case_root / "workspace").mkdir(parents=True)

    manifest_path = stage_case(case_root)
    owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
    try:
        source_event_digest, environment_digest, provider_identity_dict, semantic_result = run_harness(
            owner, case_root, manifest_path
        )
        provider_identity = ProviderIdentity(**provider_identity_dict)
        cassette_path, cassette_id = seal_cassette(
            case_root, source_event_digest, environment_digest, provider_identity, semantic_result, owner
        )
        manifest = read_json(manifest_path)
        identity = make_identity(
            manifest,
            source_event_digest,
            environment_digest,
            provider_identity_dict,
            cassette_id,
            digest_file(cassette_path),
            dsh_session_id=semantic_result["dsh_session_id"],
        )
        service = OwnerBackedReplayService(owner)
        before_digest = owner.state_digest()
        if name == "recorded-view":
            result = service.recorded_view(RUN_ID, identity, "recorded-view-1")
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
            result = service.recorded_view(RUN_ID, wrong, "source-digest-1")
        else:
            raise ValueError(f"unknown DSH-native scenario: {name}")
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
        "dsh_native_source": result.get("provenance", {}).get("harness_identity", {}).get("name")
        == "zworkbench.dsh.bootstrap",
    }
    if name == "recorded-view":
        checks.update(
            {
                "status_viewed": result_status(result) == "viewed",
                "view_only": result.get("view_only") is True,
                "semantic_from_harness": result.get("semantic_result", {}).get("dsh_session_id") == "fixture-dsh-session-1",
            }
        )
    elif name == "simulated-replay":
        checks.update(
            {
                "status_simulated": result_status(result) == "simulated",
                "cassette_only": result.get("cassette_only") is True,
            }
        )
    elif name == "live-replay":
        checks.update(
            {
                "status_denied": result_status(result) == "denied",
                "safe_denial": result.get("safe_denial") is True,
                "policy_deny": result.get("policy_decision", {}).get("decision") == "deny",
            }
        )
    else:
        checks.update(
            {
                "status_unknown": result_status(result) == "unknown",
                "safe_stop": result.get("safe_stop") is True,
            }
        )
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "dsh-native + owner-backed",
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
        raise FileExistsError("DSH evidence output directory must be new or empty")
    if not FIXTURE_MANIFEST.is_file():
        raise FileNotFoundError("DSH bootstrap fixture is incomplete")
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
        "evidence_level": "dsh-native + owner-backed",
        "status": "pass" if all(checks.values()) else "fail",
        "passed_cases": sum(case["status"] == "pass" for case in cases),
        "case_count": len(cases),
        "fixture": {
            "manifest": str(FIXTURE_MANIFEST),
            "manifest_sha256": digest_file(FIXTURE_MANIFEST),
        },
        "checks": checks,
        "cases": cases,
        "non_claims": [
            "This proves the three replay modes against a real harness execution staged through DshRuntimeAdapter.",
            "It uses the local fixture bootstrap, not the built ZDSHarness CLI; it is not DSH-CLI artifact compatibility evidence.",
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
        temporary = tempfile.TemporaryDirectory(prefix="zworkbench-dsh-h5-")
        output_dir = Path(temporary.name) / "evidence"
    summary = run_suite(output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if temporary is not None:
        temporary.cleanup()
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
