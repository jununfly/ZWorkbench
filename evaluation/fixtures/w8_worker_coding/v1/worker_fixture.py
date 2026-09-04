#!/usr/bin/env python3
"""Deterministic Worker process for the H3 read-only coding contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time


SCHEMA = "zworkbench.worker.v1"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=(
            "success",
            "result-unknown",
            "artifact-mismatch",
            "artifact-extra",
            "workspace-mutation",
            "extra-message",
            "nonzero",
            "malformed",
            "hang",
        ),
        default="success",
    )
    scenario = parser.parse_args().scenario
    request_line = input()
    if scenario == "malformed":
        print("not-json", flush=True)
        return 0
    request = json.loads(request_line)
    if scenario == "hang":
        time.sleep(60)
        return 0
    identity = dict(request["identity"])
    identity.update(
        {
            "codex_thread_id": "codex-thread-1",
            "codex_turn_id": "codex-turn-1",
            "event_id": "worker-event-1",
        }
    )
    handshake = dict(request)
    handshake.update({"message_type": "handshake.response", "identity": identity, "payload": {"status": "ready"}})
    print(json.dumps(handshake, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)

    if scenario == "nonzero":
        return 7
    if scenario == "extra-message":
        print(json.dumps(handshake, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
        return 0

    artifact_root = Path(os.environ["ZWORKBENCH_ARTIFACT_ROOT"]).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    diff = artifact_root / "diff.patch"
    tests = artifact_root / "tests.txt"
    summary = artifact_root / "semantic-result.json"
    runtime_events = artifact_root / "runtime-events.jsonl"
    diff.write_text("", encoding="utf-8")
    tests.write_text("read-only fixture tests: 1 passed\n", encoding="utf-8")
    summary.write_text(json.dumps({"status": "completed", "text": "fixture-ok"}, sort_keys=True) + "\n", encoding="utf-8")
    runtime_events.write_text('{"event":"fixture.turn.completed"}\n', encoding="utf-8")
    artifacts = {
        "diff": {"path": "diff.patch", "digest": sha256(diff), "bytes": diff.stat().st_size},
        "tests": {"path": "tests.txt", "digest": sha256(tests), "bytes": tests.stat().st_size},
        "semantic": {"path": "semantic-result.json", "digest": sha256(summary), "bytes": summary.stat().st_size},
        "runtime_events": {"path": "runtime-events.jsonl", "digest": sha256(runtime_events), "bytes": runtime_events.stat().st_size},
    }
    if scenario == "artifact-mismatch":
        artifacts["diff"]["digest"] = "sha256:" + "f" * 64
    if scenario == "artifact-extra":
        extra = artifact_root / "undeclared.txt"
        extra.write_text("must be rejected\n", encoding="utf-8")
    result_identity = dict(identity)
    result_identity["event_id"] = "worker-result-event-1"
    result_identity["artifact_id"] = "worker-coding-artifact-1"
    if scenario == "result-unknown":
        result_identity["codex_turn_id"] = "unknown"
    result = {
        "schema": SCHEMA,
        "message_type": "result",
        "identity": result_identity,
        "provider_identity": request["provider_identity"],
        "replay_mode": request["replay_mode"],
        "policy_digest": request["policy_digest"],
        "environment_digest": request["environment_digest"],
        "workspace_digest": request["workspace_digest"],
        "worker_artifact_identity": request["worker_artifact_identity"],
        "worker_schema_identity": request["worker_schema_identity"],
        "capability_request": None,
        "payload": {
            "status": "completed",
            "operation": "read_only_coding",
            "semantic_result": {"status": "completed", "text": "fixture-ok"},
            "artifacts": artifacts,
        },
    }
    if scenario == "workspace-mutation":
        workspace = Path.cwd() / "worker-must-not-write.txt"
        workspace.write_text("forbidden\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
