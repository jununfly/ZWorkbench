#!/usr/bin/env python3
"""Deterministic process used to probe the H2 Worker handshake seam."""

from __future__ import annotations

import argparse
import json
import time


SCHEMA = "zworkbench.worker.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=(
            "success",
            "unknown",
            "mismatch",
            "identity-mismatch",
            "provenance-mismatch",
            "unknown-message",
            "unknown-field",
            "nonzero",
            "crash",
            "hang",
            "malformed",
        ),
        default="success",
    )
    scenario = parser.parse_args().scenario
    line = input()
    if scenario == "malformed":
        print("not-json", flush=True)
        return 0
    if scenario == "crash":
        return 17

    request = json.loads(line)
    identity = dict(request["identity"])
    identity.update(
        {
            "codex_thread_id": "codex-thread-1",
            "codex_turn_id": "codex-turn-1",
            "event_id": "worker-event-1",
        }
    )
    if scenario == "unknown":
        identity["codex_thread_id"] = "unknown"
    if scenario == "identity-mismatch":
        identity["parent_run_id"] = "other-parent"
    response = {
        "schema": SCHEMA if scenario != "mismatch" else "future.worker.v2",
        "message_type": "handshake.future" if scenario == "unknown-message" else "handshake.response",
        "identity": identity,
        "provider_identity": request["provider_identity"],
        "replay_mode": request["replay_mode"],
        "policy_digest": request["policy_digest"],
        "environment_digest": request["environment_digest"],
        "workspace_digest": request["workspace_digest"],
        "worker_artifact_identity": request["worker_artifact_identity"],
        "worker_schema_identity": request["worker_schema_identity"],
        "capability_request": None,
        "payload": {"status": "ready"},
    }
    if scenario == "provenance-mismatch":
        response["policy_digest"] = "sha256:" + "f" * 64
    if scenario == "unknown-field":
        response["unexpected"] = True
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)
    if scenario == "hang":
        time.sleep(60)
    return 7 if scenario == "nonzero" else 0


if __name__ == "__main__":
    raise SystemExit(main())
