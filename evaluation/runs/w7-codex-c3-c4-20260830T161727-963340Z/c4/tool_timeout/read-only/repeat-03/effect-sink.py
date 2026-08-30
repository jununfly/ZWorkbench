#!/usr/bin/env python3
"""Case-local side-effect boundary for the W7 Codex adapter.

This command is intentionally boring.  It is copied into a disposable case
workspace and invoked by the real Codex ``exec_command`` tool.  The adapter is
the only owner of the ledger path; this process only performs the one
allow-listed local write after taking an advisory file lock.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from pathlib import Path


SCHEMA = "zworkbench-w7-codex-effect/v1"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--result-ledger", required=True, type=Path)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--side-effect-class", required=True, choices=["read-only", "idempotent", "approval-required"])
    parser.add_argument("--sleep-before-ms", type=int, default=0)
    args = parser.parse_args()

    if args.sleep_before_ms:
        time.sleep(args.sleep_before_ms / 1000)

    lock_path = args.ledger.with_suffix(args.ledger.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        effects = read_jsonl(args.ledger)
        existing = next((item for item in effects if item.get("operation_id") == args.operation_id), None)
        if args.side_effect_class == "read-only":
            effect_action = "none"
            logical_effect_count = 0
        elif existing:
            effect_action = "deduplicated"
            logical_effect_count = 1
        else:
            effect = {
                "schema": SCHEMA,
                "run_id": args.run_id,
                "operation_id": args.operation_id,
                "idempotency_key": args.idempotency_key,
                "side_effect_class": args.side_effect_class,
                "physical_effect_count": 1,
                "payload": "case-local-only",
            }
            append_jsonl(args.ledger, effect)
            effect_action = "applied"
            logical_effect_count = 1
        result = {
            "schema": SCHEMA,
            "run_id": args.run_id,
            "operation_id": args.operation_id,
            "idempotency_key": args.idempotency_key,
            "side_effect_class": args.side_effect_class,
            "effect_action": effect_action,
            "logical_effect_count": logical_effect_count,
            "tool_result": "fixture-ok",
        }
        append_jsonl(args.result_ledger, result)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
