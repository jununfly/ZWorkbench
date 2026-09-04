#!/usr/bin/env python3
"""Run one narrow host-boundary probe without emitting secret contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Dict


SCHEMA = "zworkbench-w8-host-boundary-probe/v1"
HOST_DENIED = 71
UNOBSERVED = 72


def emit(payload: Dict[str, Any], code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return code


def error_record(exc: BaseException) -> Dict[str, Any]:
    return {
        "error_type": type(exc).__name__,
        "errno": getattr(exc, "errno", None),
    }


def run_secret_read(secret: Path) -> int:
    try:
        value = secret.read_bytes()
    except OSError as exc:
        return emit({"schema": SCHEMA, "probe": "secret_read", "status": "host_denied", **error_record(exc)}, HOST_DENIED)
    # A digest is enough for a local control, and avoids putting the fixture
    # secret itself in stdout, stderr, or any evidence file.
    return emit(
        {
            "schema": SCHEMA,
            "probe": "secret_read",
            "status": "read",
            "bytes_read": len(value),
            "content_sha256": hashlib.sha256(value).hexdigest(),
        },
        UNOBSERVED,
    )


def run_network_connect(host: str, port: int) -> int:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except OSError as exc:
        if isinstance(exc, PermissionError):
            return emit({"schema": SCHEMA, "probe": "network_connect", "status": "host_denied", **error_record(exc)}, HOST_DENIED)
        return emit({"schema": SCHEMA, "probe": "network_connect", "status": "not_connected", **error_record(exc)}, UNOBSERVED)
    return emit({"schema": SCHEMA, "probe": "network_connect", "status": "connected"}, UNOBSERVED)


def run_dns_lookup(host: str) -> int:
    try:
        socket.getaddrinfo(host, None)
    except OSError as exc:
        if isinstance(exc, PermissionError):
            return emit({"schema": SCHEMA, "probe": "dns_lookup", "status": "host_denied", **error_record(exc)}, HOST_DENIED)
        return emit({"schema": SCHEMA, "probe": "dns_lookup", "status": "resolution_error", **error_record(exc)}, UNOBSERVED)
    return emit({"schema": SCHEMA, "probe": "dns_lookup", "status": "resolved"}, UNOBSERVED)


def run_child_exec(child: str) -> int:
    try:
        completed = subprocess.run([child, "w8-child-must-not-run"], capture_output=True, text=True, check=False, timeout=2)
    except OSError as exc:
        if isinstance(exc, PermissionError):
            return emit({"schema": SCHEMA, "probe": "child_exec", "status": "host_denied", **error_record(exc)}, HOST_DENIED)
        return emit({"schema": SCHEMA, "probe": "child_exec", "status": "not_started", **error_record(exc)}, UNOBSERVED)
    return emit(
        {
            "schema": SCHEMA,
            "probe": "child_exec",
            "status": "child_started",
            "returncode": completed.returncode,
            "stdout_marker_observed": "w8-child-must-not-run" in completed.stdout,
            "stderr_marker_observed": "w8-child-must-not-run" in completed.stderr,
        },
        UNOBSERVED,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", choices=("secret_read", "network_connect", "dns_lookup", "child_exec"), required=True)
    parser.add_argument("--secret")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--child")
    args = parser.parse_args()
    if args.probe == "secret_read":
        if not args.secret:
            raise SystemExit("--secret is required")
        return run_secret_read(Path(args.secret).expanduser().resolve())
    if args.probe == "network_connect":
        if not args.host or args.port is None:
            raise SystemExit("--host and --port are required")
        return run_network_connect(args.host, args.port)
    if args.probe == "dns_lookup":
        return run_dns_lookup(args.host or "w8-denied.invalid")
    if not args.child:
        raise SystemExit("--child is required")
    return run_child_exec(args.child)


if __name__ == "__main__":
    sys.exit(main())
