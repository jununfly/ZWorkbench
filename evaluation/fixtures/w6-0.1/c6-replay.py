#!/usr/bin/env python3
"""Candidate-independent C6 replay-mode boundary fixture.

The three modes intentionally have no Provider, tool, subprocess, or network
implementation.  They only read the supplied ledger/cassette and write a
mode-labelled result into the case output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPLAY_VERSION = "w6-c6-replay/v1"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_mode_event(path: Path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def common_result(mode, source_run_id, source_path, guard_before):
    return {
        "schema": "zworkbench-w6-c6-mode-result/v1",
        "replay_version": REPLAY_VERSION,
        "replay_mode": mode,
        "source_run_id": source_run_id,
        "source": str(source_path),
        "source_sha256": digest(source_path),
        "execution_performed": False,
        "provider_requests": 0,
        "tool_invocations": 0,
        "external_calls": 0,
        "side_effect_count": 0,
        "guard_before": guard_before,
        "guard_after": guard_before,
    }


def recorded_view(ledger_path: Path, output_dir: Path, guard):
    ledger = read_jsonl(ledger_path)
    if not ledger:
        raise SystemExit("recorded ledger is empty")
    run_id = ledger[0]["run_id"]
    required_types = sorted({event["type"] for event in ledger})
    result = common_result("recorded_view", run_id, ledger_path, guard)
    result.update({
        "status": "viewed",
        "view_event_count": len(ledger),
        "view_event_types": required_types,
        "semantic_result": next(event["semantic_result"] for event in ledger if event["type"] == "run.completed"),
        "view_only": True,
    })
    write_json(output_dir / "mode-result.json", result)
    write_mode_event(output_dir / "mode-events.jsonl", {
        "type": "replay.mode_completed",
        "mode": "recorded_view",
        "execution_performed": False,
        "source_sha256": result["source_sha256"],
    })
    return result


def simulated_replay(cassette_path: Path, output_dir: Path, guard):
    cassette = read_json(cassette_path)
    expected = cassette["expected_semantic_result"]
    result = common_result("simulated_replay", cassette["source_run_id"], cassette_path, guard)
    result.update({
        "status": "simulated",
        "cassette_id": cassette["cassette_id"],
        "replayed_interaction_count": len(cassette["interactions"]),
        "replayed_tool_result_count": len(cassette["tool_results"]),
        "semantic_result": expected,
        "expected_semantic_result": expected,
        "cassette_only": True,
    })
    write_json(output_dir / "mode-result.json", result)
    write_mode_event(output_dir / "mode-events.jsonl", {
        "type": "replay.mode_completed",
        "mode": "simulated_replay",
        "execution_performed": False,
        "cassette_id": cassette["cassette_id"],
    })
    return result


def live_replay(cassette_path: Path, output_dir: Path, guard):
    cassette = read_json(cassette_path)
    result = common_result("live_replay", cassette["source_run_id"], cassette_path, guard)
    policy = {
        "replay_mode": "live_replay",
        "approval_required": True,
        "approval_granted": False,
        "decision": "deny",
        "reason": "live_replay_requires_explicit_approval",
    }
    result.update({
        "status": "denied",
        "policy_decision": policy,
        "safe_denial": True,
    })
    write_json(output_dir / "mode-result.json", result)
    write_json(output_dir / "policy-decision.json", policy)
    write_mode_event(output_dir / "mode-events.jsonl", {
        "type": "replay.mode_denied",
        "mode": "live_replay",
        "execution_performed": False,
        "reason": policy["reason"],
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("recorded_view", "simulated_replay", "live_replay"), required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--cassette", type=Path)
    parser.add_argument("--effect-guard", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    guard = read_json(args.effect_guard)
    if args.mode == "recorded_view":
        if not args.ledger:
            raise SystemExit("recorded_view requires --ledger")
        result = recorded_view(args.ledger, args.output_dir, guard)
    elif args.mode == "simulated_replay":
        if not args.cassette:
            raise SystemExit("simulated_replay requires --cassette")
        result = simulated_replay(args.cassette, args.output_dir, guard)
    else:
        if not args.cassette:
            raise SystemExit("live_replay requires --cassette")
        result = live_replay(args.cassette, args.output_dir, guard)
    print(json.dumps({
        "mode": result["replay_mode"],
        "status": result["status"],
        "execution_performed": result["execution_performed"],
        "side_effect_count": result["side_effect_count"],
        "result": str(args.output_dir / "mode-result.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
