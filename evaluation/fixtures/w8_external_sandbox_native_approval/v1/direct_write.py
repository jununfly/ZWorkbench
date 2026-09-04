#!/usr/bin/env python3
"""Attempt one case-local write and report host-enforced denial precisely."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional


SCHEMA = "zworkbench-w8-external-sandbox-direct-probe/v1"


def process_ancestry(limit: int = 16) -> List[Dict[str, Any]]:
    pid = os.getpid()
    chain: List[Dict[str, Any]] = []
    seen = set()
    for _ in range(limit):
        if pid in seen or pid <= 0:
            break
        seen.add(pid)
        try:
            completed = subprocess.run(
                ["/bin/ps", "-o", "pid=,ppid=,comm=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            chain.append({"pid": pid, "ppid": os.getppid(), "command": None, "observed": False, "error_type": type(exc).__name__})
            break
        line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), "")
        parts = line.split(None, 2)
        if len(parts) != 3:
            chain.append({"pid": pid, "ppid": None, "command": None, "observed": False})
            break
        current_pid, parent_pid, command = parts
        record = {"pid": int(current_pid), "ppid": int(parent_pid), "command": command, "observed": True}
        chain.append(record)
        if int(parent_pid) in {0, int(current_pid)}:
            break
        pid = int(parent_pid)
    return chain


def expected_codex_pid() -> Optional[int]:
    value = os.environ.get("ZWB_EXTERNAL_SANDBOX_CODEX_PID_FILE")
    if not value:
        return None
    try:
        return int(Path(value).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def emit(status: str, target: Path, *, error: BaseException | None = None) -> int:
    expected_pid = expected_codex_pid()
    ancestry = process_ancestry()
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "target": str(target),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "expected_codex_pid": expected_pid,
        "ancestry": ancestry,
    }
    if error is not None:
        payload.update({"error_type": type(error).__name__, "errno": getattr(error, "errno", None)})
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 73 if status == "host_denied" else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--pause-seconds", type=float, default=0.0)
    parser.add_argument("--pid-file")
    parser.add_argument("--ready-file")
    parser.add_argument("--release-file")
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()
    if args.pid_file:
        Path(args.pid_file).write_text(
            json.dumps({"pid": os.getpid(), "ppid": os.getppid(), "expected_codex_pid": expected_codex_pid()}) + "\n",
            encoding="utf-8",
        )
    if args.ready_file:
        Path(args.ready_file).write_text(json.dumps({"pid": os.getpid(), "ppid": os.getppid()}) + "\n", encoding="utf-8")
    if args.release_file:
        release = Path(args.release_file)
        while not release.exists():
            time.sleep(0.01)
    if args.pause_seconds > 0:
        time.sleep(args.pause_seconds)
    try:
        target.write_text(args.content, encoding="utf-8")
    except OSError as exc:
        return emit("host_denied", target, error=exc)
    return emit("written", target)


if __name__ == "__main__":
    raise SystemExit(main())
