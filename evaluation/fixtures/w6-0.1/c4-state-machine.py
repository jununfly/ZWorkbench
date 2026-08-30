#!/usr/bin/env python3
"""Deterministic durable-run state machine for the W6 C4 acceptance fixture.

This is evaluation infrastructure only.  It does not execute shell commands,
contact a real provider, or perform an external side effect.  The only
"effects" are records in the disposable case directory.  The fixture models
the durable seams that a real runner must expose: provider attempts, tool
attempts, state transitions, fault injections, tool results, and a
deduplicated side-effect ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "zworkbench-w6-c4-state/v1"
INJECTED_EXIT = 75

TOOL_CLASSES = {
    "read-only": {
        "tool_name": "read_metadata",
        "requires_approval": False,
        "replay_safe": True,
    },
    "idempotent": {
        "tool_name": "write_idempotent_result",
        "requires_approval": False,
        "replay_safe": True,
    },
    "approval-required": {
        "tool_name": "publish_approved_result",
        "requires_approval": True,
        "replay_safe": False,
    },
}

FAULTS = {
    "before_tool",
    "after_tool_before_commit",
    "committed_before_next_step",
    "provider_timeout",
    "tool_timeout",
    "process_interrupt",
}

ALLOWED_TRANSITIONS = {
    "ready": {"provider_succeeded"},
    "provider_succeeded": {"tool_started"},
    "tool_started": {"committed", "safe_stopped"},
    "committed": {"completed"},
    "safe_stopped": set(),
    "completed": set(),
}


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
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            values.append(json.loads(line))
    return values


class DurableRun:
    def __init__(self, run_dir: Path, run_id: str, tool_class: str, fault: str):
        if tool_class not in TOOL_CLASSES:
            raise ValueError(f"unsupported tool class: {tool_class}")
        if fault not in FAULTS:
            raise ValueError(f"unsupported fault: {fault}")
        self.run_dir = run_dir
        self.run_id = run_id
        self.tool_class = tool_class
        self.fault = fault
        self.tool_spec = TOOL_CLASSES[tool_class]
        self.state_path = run_dir / "state.json"
        self.events_path = run_dir / "events.jsonl"
        self.transitions_path = run_dir / "transitions.jsonl"
        self.faults_path = run_dir / "faults.jsonl"
        self.attempts_path = run_dir / "attempts.jsonl"
        self.results_path = run_dir / "tool-results.jsonl"
        self.effects_path = run_dir / "effects.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self):
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state["run_id"] != self.run_id:
                raise ValueError("run_id does not match durable state")
            if state["tool"]["side_effect_class"] != self.tool_class:
                raise ValueError("tool class does not match durable state")
            if state["fault"] != self.fault:
                raise ValueError("fault does not match durable state")
            return state
        state = {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "fault": self.fault,
            "tool": {
                "name": self.tool_spec["tool_name"],
                "side_effect_class": self.tool_class,
                "operation_id": f"{self.run_id}:operation-1",
                "requires_approval": self.tool_spec["requires_approval"],
                "replay_safe": self.tool_spec["replay_safe"],
            },
            "phase": "ready",
            "status": "running",
            "invocation_count": 0,
            "provider_attempts": 0,
            "tool_attempts": 0,
            "retry_count": 0,
            "approval_granted": self.tool_spec["requires_approval"],
            "last_checkpoint": "ready",
            "safe_stop_reason": None,
        }
        self._write_state(state)
        self._event("run.created", phase="ready")
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
        if event_type == "state.transition":
            append_jsonl(self.transitions_path, event)
        if event_type == "fault.injected":
            append_jsonl(self.faults_path, event)
        if event_type == "invocation.attempt":
            append_jsonl(self.attempts_path, event)
        if event_type == "tool.result":
            append_jsonl(self.results_path, event)
        return event

    def _transition(self, new_phase: str, reason: str, **payload):
        old_phase = self.state["phase"]
        if new_phase not in ALLOWED_TRANSITIONS.get(old_phase, set()):
            raise RuntimeError(f"invalid transition {old_phase} -> {new_phase}")
        event = self._event(
            "state.transition",
            from_phase=old_phase,
            to_phase=new_phase,
            reason=reason,
            **payload,
        )
        self.state["phase"] = new_phase
        self.state["last_checkpoint"] = new_phase
        self._write_state()
        return event

    def _record_invocation(self, mode: str):
        self.state["invocation_count"] += 1
        self._write_state()
        self._event(
            "invocation.attempt",
            mode=mode,
            invocation=self.state["invocation_count"],
            phase=self.state["phase"],
        )

    def _effect_records(self):
        return read_jsonl(self.effects_path)

    def _find_effect(self):
        operation_id = self.state["tool"]["operation_id"]
        return next((item for item in self._effect_records() if item.get("operation_id") == operation_id), None)

    def _apply_effect(self, tool_attempt: int):
        if self.tool_class == "read-only":
            return {"effect_action": "none", "logical_effect_count": 0}
        existing = self._find_effect()
        if existing:
            self._event(
                "side_effect.deduplicated",
                operation_id=existing["operation_id"],
                tool_attempt=tool_attempt,
                side_effect_class=self.tool_class,
            )
            return {"effect_action": "deduplicated", "logical_effect_count": 1}
        effect = {
            "schema": SCHEMA,
            "at": now(),
            "run_id": self.run_id,
            "operation_id": self.state["tool"]["operation_id"],
            "side_effect_class": self.tool_class,
            "replay_safe": self.tool_spec["replay_safe"],
            "physical_effect_count": 1,
            "payload": "fixture-local-only",
        }
        append_jsonl(self.effects_path, effect)
        self._event(
            "side_effect.applied",
            operation_id=effect["operation_id"],
            tool_attempt=tool_attempt,
            side_effect_class=self.tool_class,
        )
        return {"effect_action": "applied", "logical_effect_count": 1}

    def _start_tool(self):
        self._transition("tool_started", "tool execution checkpoint")

    def _execute_tool(self, outcome="success"):
        self.state["tool_attempts"] += 1
        tool_attempt = self.state["tool_attempts"]
        self._write_state()
        effect = self._apply_effect(tool_attempt)
        event = self._event(
            "tool.attempt",
            tool=self.tool_spec["tool_name"],
            side_effect_class=self.tool_class,
            tool_attempt=tool_attempt,
            outcome=outcome,
            effect_action=effect["effect_action"],
        )
        if outcome == "success":
            result = {
                "result": "fixture-ok",
                "tool": self.tool_spec["tool_name"],
                "side_effect_class": self.tool_class,
                "effect_action": effect["effect_action"],
                "tool_attempt": tool_attempt,
            }
            self._event("tool.result", tool_attempt=tool_attempt, result=result)
            return result
        return {"timed_out": True, "tool_attempt": tool_attempt, **effect}

    def _commit_and_complete(self, reason: str):
        self._transition("committed", reason)
        self._transition("completed", "next step completed")
        self.state["status"] = "completed"
        self._write_state()
        self._event("run.completed", status="completed", reason=reason)

    def _safe_stop(self, reason: str):
        self.state["safe_stop_reason"] = reason
        self.state["status"] = "safe_stopped"
        self._write_state()
        self._transition("safe_stopped", reason)
        self.state["status"] = "safe_stopped"
        self._write_state()
        self._event("run.safe_stopped", status="safe_stopped", reason=reason)

    def _provider(self):
        self.state["provider_attempts"] += 1
        attempt = self.state["provider_attempts"]
        self._write_state()
        if self.fault == "provider_timeout" and attempt == 1:
            self._inject("provider_timeout", "fake Provider timeout before a response")
            self._event("provider.timeout", provider="fake-provider-a", provider_attempt=attempt)
            self.state["retry_count"] += 1
            self._write_state()
            self._event(
                "retry.decided",
                scope="provider",
                retry_number=self.state["retry_count"],
                reason="provider timeout; one bounded retry is safe before tool execution",
            )
            self.state["provider_attempts"] += 1
            attempt = self.state["provider_attempts"]
            self._write_state()
        self._event("provider.response", provider="fake-provider-a", provider_attempt=attempt)
        self._transition("provider_succeeded", "provider response durably recorded")

    def _inject(self, point: str, reason: str):
        self._event("fault.injected", fault=self.fault, point=point, reason=reason)

    def _resume_pending_tool(self):
        result_records = [item for item in read_jsonl(self.results_path) if item.get("run_id") == self.run_id]
        effect = self._find_effect()
        if result_records:
            self._event("tool.reconciled", source="tool-results-ledger", tool_attempt=result_records[-1]["tool_attempt"])
            self._commit_and_complete("reconciled durable tool result")
            return
        if effect:
            self._event(
                "tool.reconciled",
                source="side-effect-ledger",
                operation_id=effect["operation_id"],
                replay="no re-execution",
            )
            self._commit_and_complete("reconciled durable side effect")
            return
        if self.tool_class == "approval-required":
            self._safe_stop("tool result unknown and approval-required effect cannot be replayed automatically")
            return
        self.state["retry_count"] += 1
        self._write_state()
        self._event(
            "retry.decided",
            scope="tool",
            retry_number=self.state["retry_count"],
            reason="durable tool result absent; replay-safe tool can be retried once",
        )
        self._execute_tool("success")
        self._commit_and_complete("replayed replay-safe tool")

    def initial(self):
        self._record_invocation("initial")
        if self.state["status"] != "running":
            return {"outcome": "already-terminal", "status": self.state["status"]}
        if self.state["phase"] == "ready":
            self._provider()
        if self.state["phase"] == "provider_succeeded":
            if self.fault == "before_tool":
                self._inject("before_tool", "fault before any tool execution")
                return {"outcome": "fault-injected", "exit_code": INJECTED_EXIT}
            self._start_tool()
        if self.fault == "after_tool_before_commit":
            self._execute_tool("success")
            self._inject("after_tool_before_commit", "tool result exists but commit is not durable")
            return {"outcome": "fault-injected", "exit_code": INJECTED_EXIT}
        if self.fault == "committed_before_next_step":
            self._execute_tool("success")
            self._transition("committed", "tool result committed")
            self._inject("committed_before_next_step", "commit durable before next step")
            return {"outcome": "fault-injected", "exit_code": INJECTED_EXIT}
        if self.fault == "tool_timeout":
            timeout_result = self._execute_tool("timeout")
            self._inject("tool_timeout", "tool result timeout after the attempt boundary")
            self._event(
                "tool.timeout",
                tool_attempt=timeout_result["tool_attempt"],
                effect_action=timeout_result["effect_action"],
                side_effect_class=self.tool_class,
            )
            if self.tool_class == "approval-required":
                self._safe_stop("tool timeout leaves approval-required effect outcome uncertain")
                return {"outcome": "safe-stopped", "status": "safe_stopped"}
            self.state["retry_count"] += 1
            self._write_state()
            self._event(
                "retry.decided",
                scope="tool",
                retry_number=self.state["retry_count"],
                reason="tool timeout; replay-safe tool permits one retry",
            )
            self._execute_tool("success")
            self._commit_and_complete("bounded retry after tool timeout")
            return {"outcome": "completed", "status": "completed"}
        if self.fault == "process_interrupt":
            interrupted = self._execute_tool("pending-result")
            self._inject("process_interrupt", "SIGTERM after durable effect boundary and before result commit")
            # The effect ledger is fsync'd before the signal.  The process is
            # intentionally terminated so the runner must resume the same run.
            os.kill(os.getpid(), signal.SIGTERM)
            return {"outcome": "unreachable", "tool_attempt": interrupted["tool_attempt"]}
        self._execute_tool("success")
        self._commit_and_complete("normal completion")
        return {"outcome": "completed", "status": "completed"}

    def resume(self):
        self._record_invocation("resume")
        if self.state["status"] != "running":
            return {"outcome": "already-terminal", "status": self.state["status"]}
        if self.state["phase"] == "provider_succeeded":
            self._start_tool()
            self._execute_tool("success")
            self._commit_and_complete("resumed from provider checkpoint")
            return {"outcome": "completed", "status": "completed"}
        if self.state["phase"] == "tool_started":
            self._resume_pending_tool()
            return {"outcome": self.state["status"], "status": self.state["status"]}
        if self.state["phase"] == "committed":
            self._transition("completed", "resumed after committed checkpoint")
            self.state["status"] = "completed"
            self._write_state()
            self._event("run.completed", status="completed", reason="resumed next step")
            return {"outcome": "completed", "status": "completed"}
        if self.state["phase"] == "ready":
            self._provider()
            self._start_tool()
            self._execute_tool("success")
            self._commit_and_complete("resumed from ready checkpoint")
            return {"outcome": "completed", "status": "completed"}
        raise RuntimeError(f"cannot resume from phase {self.state['phase']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tool-class", required=True, choices=sorted(TOOL_CLASSES))
    parser.add_argument("--fault", required=True, choices=sorted(FAULTS))
    parser.add_argument("--mode", required=True, choices=["initial", "resume"])
    args = parser.parse_args()
    runner = DurableRun(args.run_dir, args.run_id, args.tool_class, args.fault)
    result = runner.initial() if args.mode == "initial" else runner.resume()
    print(json.dumps({"run_id": args.run_id, **result}, ensure_ascii=False, sort_keys=True))
    if result.get("exit_code"):
        raise SystemExit(result["exit_code"])


if __name__ == "__main__":
    main()
