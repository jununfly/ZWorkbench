#!/usr/bin/env python3
"""Deterministic external process used by the H1 adapter tests."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


SCHEMA = "zworkbench.dsh.bootstrap/v1"


def message(message_type: str, status: str) -> None:
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "message_type": message_type,
                "identity": {
                    "parent_run_id": os.environ["ZWORKBENCH_RUN_ID"],
                    "dsh_session_id": "fixture-dsh-session-1",
                },
                "payload": {"status": status, "profile_id": os.environ["ZWORKBENCH_DSH_PROFILE"]},
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("success", "unknown", "nonzero", "hang"), default="success")
    scenario = parser.parse_args().scenario
    if scenario == "unknown":
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "message_type": "bootstrap.future",
                    "identity": {
                        "parent_run_id": os.environ["ZWORKBENCH_RUN_ID"],
                        "dsh_session_id": "fixture-dsh-session-1",
                    },
                    "payload": {"status": "future", "profile_id": os.environ["ZWORKBENCH_DSH_PROFILE"]},
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        # Keep the process alive long enough for the adapter to exercise its
        # fail-closed termination path. Returning immediately races protocol
        # rejection with a natural exit(0), making cleanup timing-dependent.
        time.sleep(60)
        return 0
    message("bootstrap.started", "started")
    if scenario == "hang":
        sys.stdin.read()
    message("bootstrap.ready", "ready")
    return 7 if scenario == "nonzero" else 0


if __name__ == "__main__":
    raise SystemExit(main())
