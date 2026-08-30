#!/usr/bin/env python3
"""Deterministic schedule/idempotency fixture for W6 C3.

This is acceptance infrastructure only.  A trigger is supplied by the runner
as an external deterministic scheduler.  The fixture persists the schedule,
attempt, result, and effect ledgers, and delivers at most one local
loopback-sink request for one idempotency key.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen


SCHEMA = "zworkbench-w6-c3-idempotency/v1"
SCHEDULE_ID = "daily-summary-v1"
LOGICAL_TRIGGER_TIME = "2026-08-30T00:00:00Z"
IDEMPOTENCY_KEY = f"{SCHEDULE_ID}:{LOGICAL_TRIGGER_TIME}"
RESULT_VERSION = "daily-summary-v1:2026-08-30"


def now():
    return datetime.now(timezone.utc).isoformat()


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


class IdempotentScheduleRun:
    def __init__(self, run_dir: Path, run_id: str, sink_url: str, sink_output: Path):
        self.run_dir = run_dir
        self.run_id = run_id
        self.sink_url = sink_url
        self.sink_output = sink_output
        self.state_path = run_dir / "state.json"
        self.events_path = run_dir / "events.jsonl"
        self.schedule_path = run_dir / "schedule.jsonl"
        self.attempts_path = run_dir / "attempts.jsonl"
        self.faults_path = run_dir / "faults.jsonl"
        self.effects_path = run_dir / "effects.jsonl"
        self.results_path = run_dir / "results.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self):
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state["run_id"] != self.run_id:
                raise ValueError("run_id does not match durable state")
            return state
        state = {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "schedule_id": SCHEDULE_ID,
            "logical_trigger_time": LOGICAL_TRIGGER_TIME,
            "idempotency_key": IDEMPOTENCY_KEY,
            "result_version": RESULT_VERSION,
            "status": "pending",
            "effect_status": "none",
            "sink_delivery_count": 0,
            "invocation_count": 0,
            "attempt_count": 0,
            "safe_replay": True,
            "last_trigger_kind": None,
        }
        self._write_state(state)
        self._event("run.created", schedule_id=SCHEDULE_ID, idempotency_key=IDEMPOTENCY_KEY)
        return state

    def _write_state(self, state=None):
        state = state or self.state
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with temporary.open("r+", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)
        directory_fd = os.open(str(self.run_dir), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _event(self, event_type: str, **payload):
        event = {
            "schema": SCHEMA,
            "seq": len(read_jsonl(self.events_path)) + 1,
            "at": now(),
            "run_id": self.run_id,
            "type": event_type,
            **payload,
        }
        append_jsonl(self.events_path, event)
        if event_type == "schedule.trigger.received":
            append_jsonl(self.schedule_path, event)
        if event_type == "fault.injected":
            append_jsonl(self.faults_path, event)
        return event

    def _attempt(self, attempt_id: str, trigger_kind: str, phase: str, outcome: str, **payload):
        append_jsonl(
            self.attempts_path,
            {
                "schema": SCHEMA,
                "at": now(),
                "run_id": self.run_id,
                "attempt_id": attempt_id,
                "schedule_id": SCHEDULE_ID,
                "logical_trigger_time": LOGICAL_TRIGGER_TIME,
                "idempotency_key": IDEMPOTENCY_KEY,
                "trigger_kind": trigger_kind,
                "phase": phase,
                "outcome": outcome,
                **payload,
            },
        )

    def _sink_records(self):
        return [item for item in read_jsonl(self.sink_output) if item.get("idempotency_key") == IDEMPOTENCY_KEY]

    def _deliver_once(self, trigger_kind: str):
        payload = {
            "schedule_id": SCHEDULE_ID,
            "logical_trigger_time": LOGICAL_TRIGGER_TIME,
            "idempotency_key": IDEMPOTENCY_KEY,
            "result_version": RESULT_VERSION,
            "trigger_kind": trigger_kind,
            "message_kind": "fixture-local-result",
        }
        request = Request(self.sink_url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={"content-type": "application/json"})
        with urlopen(request, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"fake sink returned {response.status}")
        return payload

    def _commit_result(self, attempt_id: str, trigger_kind: str, source: str):
        sink_count = len(self._sink_records())
        if sink_count != 1:
            raise RuntimeError(f"expected one sink delivery before commit, got {sink_count}")
        if not read_jsonl(self.effects_path):
            append_jsonl(
                self.effects_path,
                {
                    "schema": SCHEMA,
                    "at": now(),
                    "run_id": self.run_id,
                    "schedule_id": SCHEDULE_ID,
                    "idempotency_key": IDEMPOTENCY_KEY,
                    "result_version": RESULT_VERSION,
                    "physical_sink_deliveries": sink_count,
                    "commit_source": source,
                },
            )
        self.state["effect_status"] = "applied"
        self.state["sink_delivery_count"] = sink_count
        self.state["status"] = "completed"
        self.state["last_trigger_kind"] = trigger_kind
        self._write_state()
        if not read_jsonl(self.results_path):
            append_jsonl(
                self.results_path,
                {
                    "schema": SCHEMA,
                    "at": now(),
                    "run_id": self.run_id,
                    "schedule_id": SCHEDULE_ID,
                    "logical_trigger_time": LOGICAL_TRIGGER_TIME,
                    "idempotency_key": IDEMPOTENCY_KEY,
                    "result_version": RESULT_VERSION,
                    "source": source,
                },
            )
        self._event(
            "result.committed",
            schedule_id=SCHEDULE_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            result_version=RESULT_VERSION,
            source=source,
        )
        self._attempt(attempt_id, trigger_kind, "terminal", "completed", side_effect="one")

    def _reconcile_pending(self, attempt_id: str, trigger_kind: str):
        sink_count = len(self._sink_records())
        if sink_count == 1:
            self._event("side_effect.reconciled", idempotency_key=IDEMPOTENCY_KEY, sink_delivery_count=sink_count)
            self._commit_result(attempt_id, trigger_kind, "sink-observation-reconcile")
            return
        if sink_count == 0:
            self._deliver_once(trigger_kind)
            self._commit_result(attempt_id, trigger_kind, "resume-delivery")
            return
        raise RuntimeError(f"duplicate sink deliveries observed during reconcile: {sink_count}")

    def trigger(self, trigger_kind: str, fault: Optional[str]):
        self.state["invocation_count"] += 1
        self.state["attempt_count"] += 1
        self.state["last_trigger_kind"] = trigger_kind
        attempt_id = f"{self.run_id}:attempt-{self.state['attempt_count']:03d}"
        self._write_state()
        self._attempt(attempt_id, trigger_kind, "started", "received")
        self._event(
            "schedule.trigger.received",
            schedule_id=SCHEDULE_ID,
            logical_trigger_time=LOGICAL_TRIGGER_TIME,
            idempotency_key=IDEMPOTENCY_KEY,
            trigger_kind=trigger_kind,
            missed=trigger_kind == "missed",
            delivery_semantics="run-once-late" if trigger_kind == "missed" else "scheduled",
        )
        if self.state["status"] == "completed":
            self._event("idempotency.duplicate", idempotency_key=IDEMPOTENCY_KEY, trigger_kind=trigger_kind)
            self._attempt(attempt_id, trigger_kind, "terminal", "deduplicated", side_effect="zero")
            return {"outcome": "deduplicated", "status": "completed"}
        if self.state["effect_status"] == "in_progress":
            self._reconcile_pending(attempt_id, trigger_kind)
            return {"outcome": "reconciled", "status": "completed"}
        self.state["effect_status"] = "in_progress"
        self._write_state()
        self._event("idempotency.claimed", idempotency_key=IDEMPOTENCY_KEY, attempt_id=attempt_id)
        self._deliver_once(trigger_kind)
        if fault == "process_interrupt":
            self._event("fault.injected", fault=fault, point="after_sink_before_result_commit", attempt_id=attempt_id)
            self._attempt(attempt_id, trigger_kind, "terminal", "interrupted", side_effect="one-observed")
            os.kill(os.getpid(), signal.SIGTERM)
            return {"outcome": "unreachable"}
        self._commit_result(attempt_id, trigger_kind, "first-delivery")
        return {"outcome": "completed", "status": "completed"}

    def resume(self):
        self.state["invocation_count"] += 1
        self.state["attempt_count"] += 1
        attempt_id = f"{self.run_id}:attempt-{self.state['attempt_count']:03d}"
        trigger_kind = "resume-after-interrupt"
        self._write_state()
        self._attempt(attempt_id, trigger_kind, "started", "resume")
        if self.state["status"] == "completed":
            self._event("idempotency.duplicate", idempotency_key=IDEMPOTENCY_KEY, trigger_kind=trigger_kind)
            self._attempt(attempt_id, trigger_kind, "terminal", "deduplicated", side_effect="zero")
            return {"outcome": "deduplicated", "status": "completed"}
        if self.state["effect_status"] != "in_progress":
            raise RuntimeError(f"resume expected in_progress effect, got {self.state['effect_status']}")
        self._reconcile_pending(attempt_id, trigger_kind)
        return {"outcome": "reconciled", "status": "completed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sink-url", required=True)
    parser.add_argument("--sink-output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=["trigger", "resume"])
    parser.add_argument("--trigger-kind", default="trigger")
    parser.add_argument("--fault", choices=["process_interrupt"])
    args = parser.parse_args()
    runner = IdempotentScheduleRun(args.run_dir, args.run_id, args.sink_url, args.sink_output)
    result = runner.trigger(args.trigger_kind, args.fault) if args.mode == "trigger" else runner.resume()
    print(json.dumps({"run_id": args.run_id, **result}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
