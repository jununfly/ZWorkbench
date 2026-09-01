#!/usr/bin/env python3
"""Attempt one direct write so a host profile can expose a real denial."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from host_broker import process_ancestry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--content", required=True)
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()
    pid_file_name = os.environ.get("ZWB_HOST_CODEX_PID_FILE")
    expected_codex_pid = None
    if pid_file_name:
        try:
            expected_codex_pid = int(Path(pid_file_name).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
    ancestry = process_ancestry()
    try:
        target.write_text(args.content, encoding="utf-8")
    except OSError as exc:
        print(json.dumps({
            "schema": "zworkbench-w8-host-direct-probe/v1",
            "status": "host_denied",
            "target": str(target),
            "error_type": type(exc).__name__,
            "errno": exc.errno,
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "expected_codex_pid": expected_codex_pid,
            "ancestry": ancestry,
        }, ensure_ascii=False, sort_keys=True))
        return 73
    print(json.dumps({
        "schema": "zworkbench-w8-host-direct-probe/v1",
        "status": "written",
        "target": str(target),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "expected_codex_pid": expected_codex_pid,
        "ancestry": ancestry,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
