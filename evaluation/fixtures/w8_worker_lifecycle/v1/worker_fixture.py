#!/usr/bin/env python3
"""Deterministic process tree used to probe the H4 Worker lifecycle seam."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


SCHEMA = "zworkbench.worker.v1"


def send_handshake(request: dict) -> None:
    identity = dict(request["identity"])
    identity.update(
        {
            "codex_thread_id": "lifecycle-thread-1",
            "codex_turn_id": "lifecycle-turn-1",
            "event_id": "lifecycle-event-1",
        }
    )
    response = dict(request)
    response.update(
        {
            "schema": SCHEMA,
            "message_type": "handshake.response",
            "identity": identity,
            "payload": {"status": "ready"},
        }
    )
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")), flush=True)


def spawn_descendant() -> subprocess.Popen[bytes]:
    child_code = (
        "import signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(60)"
    )
    return subprocess.Popen([sys.executable, "-c", child_code])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=("success", "crash", "crash-once", "hang", "spawn-descendant", "ignore-term"),
        default="success",
    )
    scenario = parser.parse_args().scenario
    request = json.loads(input())
    workspace = Path.cwd()

    if scenario == "crash":
        return 23
    if scenario == "crash-once":
        marker = workspace / "crash-once.marker"
        if not marker.exists():
            marker.write_text("first attempt\n", encoding="utf-8")
            return 23
    if scenario == "spawn-descendant":
        descendant = spawn_descendant()
        (workspace / "descendant.pid").write_text(str(descendant.pid), encoding="utf-8")
        time.sleep(60)
        return 0
    if scenario == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
        return 0
    if scenario == "hang":
        time.sleep(60)
        return 0

    send_handshake(request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
