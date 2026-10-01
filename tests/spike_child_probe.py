#!/usr/bin/python3
"""S0 spike probe child: run UNDER the enforcer (sandbox-exec).

Attempts a whitelisted write (argv[1], optional), a denied write, and a network
connect, then emits a single JSON line describing each attempt. The parent harness
parses this to capture auditable violation events (fail-closed criterion #3).
"""
import json
import os
import socket
import sys
from typing import Dict

sys.dont_write_bytecode = True

result: Dict[str, object] = {"attempts": []}


def record(kind: str, ok: bool, detail) -> None:
    result["attempts"].append({"kind": kind, "allowed": ok, "detail": detail})


# 1) whitelisted write (only succeeds when the parent allowed this path)
if len(sys.argv) > 1:
    allowed_path = sys.argv[1]
    try:
        with open(allowed_path, "w") as fh:
            fh.write("ok")
        record("file-write-allowed", True, allowed_path)
        try:
            os.remove(allowed_path)
        except OSError:
            pass
    except OSError as exc:
        record("file-write-allowed", False, {"path": allowed_path, "errno": exc.errno})

# 2) denied write (never whitelisted -> must be denied under default profile)
denied_path = "/tmp/spike_denied_write_" + str(os.getpid())
try:
    with open(denied_path, "w") as fh:
        fh.write("x")
    record("file-write", True, denied_path)
    try:
        os.remove(denied_path)
    except OSError:
        pass
except OSError as exc:
    record(
        "file-write",
        False,
        {"path": denied_path, "errno": exc.errno, "strerror": exc.strerror},
    )

# 3) network outbound (must be denied under default profile)
try:
    sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
    sock.close()
    record("network-outbound", True, "8.8.8.8:53")
except OSError as exc:
    record("network-outbound", False, {"errno": exc.errno, "strerror": exc.strerror})

print(json.dumps(result))
sys.exit(0)
