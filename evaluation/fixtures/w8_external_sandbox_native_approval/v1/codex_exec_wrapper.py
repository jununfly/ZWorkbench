#!/usr/bin/env python3
"""Capture the sandboxed app-server PID, then exec the real Codex process."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: codex_exec_wrapper.py PID_FILE EXECUTABLE [ARGS ...]")
    pid_file = Path(sys.argv[1]).expanduser().resolve()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    with pid_file.open("r+", encoding="utf-8") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.execv(sys.argv[2], sys.argv[2:])
    return 127


if __name__ == "__main__":
    sys.exit(main())
