#!/usr/bin/env python3
"""Pause a command long enough for an external runner to inspect its ancestry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


SCHEMA = "zworkbench-w8-process-tree-probe/v1"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    write_json(args.ready, {"schema": SCHEMA, "pid": os.getpid(), "ppid": os.getppid(), "status": "waiting"})
    deadline = time.monotonic() + 15
    while not args.release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not args.release.exists():
        print(json.dumps({"schema": SCHEMA, "status": "release_timeout"}, ensure_ascii=False))
        return 74
    print(json.dumps({"schema": SCHEMA, "pid": os.getpid(), "ppid": os.getppid(), "status": "released"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
