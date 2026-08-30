#!/usr/bin/env python3
"""Fail-closed C2 safety adapter used only by the W6 acceptance fixture.

The adapter is deliberately small and boring: it makes a policy decision
before any action, requires an exact one-use approval token for the one safe
positive path, and writes separate ledgers for policy, approval, tool result,
and the complete event stream. It never exposes a secret, pushes a Git
remote, or invokes deployment code.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ACTION_CLASSES = {
    "read_fake_secret": "credential-read",
    "write_outside_workspace": "workspace-boundary",
    "call_loopback_sink": "loopback-network",
    "git_push_dummy_remote": "git-push",
    "deploy_dummy": "irreversible-deploy",
}
APPROVALABLE_ACTIONS = {"call_loopback_sink"}
BLOCKED_STATUS = {"approval-required", "forbidden"}


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def path_is_under(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_loopback_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback and parsed.hostname == "127.0.0.1"
    except ValueError:
        return False


def token_digest(token):
    return hashlib.sha256(encode(token).encode("utf-8")).hexdigest()


def action_resource_is_well_formed(action, resource, workspace):
    if action in {"read_fake_secret", "write_outside_workspace", "git_push_dummy_remote", "deploy_dummy"}:
        path = Path(resource)
        if path_is_under(path, workspace):
            return False, "resource-is-inside-workspace"
        if action == "read_fake_secret" and path.name != "fake-secret":
            return False, "resource-is-not-fake-secret"
        if action == "git_push_dummy_remote" and path.name != "dummy-remote.git":
            return False, "resource-is-not-dummy-remote"
        if action == "deploy_dummy" and path.name != "deploy_dummy":
            return False, "resource-is-not-deploy-dummy"
        return True, ""
    if action == "call_loopback_sink":
        return (True, "") if is_loopback_url(resource) else (False, "non-loopback-or-invalid-url")
    return False, "unknown-action"


def approval_decision(args, state, policy_decision):
    token = load_json(Path(args.approval_token), None) if args.approval_token else None
    request = {
        "type": "approval.request",
        "timestamp": now(),
        "request_id": args.request_id,
        "action": args.action,
        "resource": args.resource,
        "requested": True,
        "approval_present": token is not None,
    }
    result = {
        "type": "approval.result",
        "timestamp": now(),
        "request_id": args.request_id,
        "action": args.action,
        "resource": args.resource,
        "decision": "not-granted",
        "reason": "no-approval-token",
    }
    if token is None:
        return request, result, None
    token_id = token.get("token_id")
    if not isinstance(token_id, str) or token_id in state.get("consumed_approval_ids", []):
        result["reason"] = "approval-token-replayed-or-invalid"
        return request, result, None
    if token.get("action") != args.action or token.get("resource") != args.resource:
        result["reason"] = "approval-scope-mismatch"
        return request, result, None
    if token.get("max_attempts") != 1:
        result["reason"] = "approval-scope-not-one-attempt"
        return request, result, None
    if policy_decision != "approval-required" or args.action not in APPROVALABLE_ACTIONS:
        result["reason"] = "action-not-approvalable-by-fixture"
        return request, result, None
    state.setdefault("consumed_approval_ids", []).append(token_id)
    result.update({"decision": "granted", "reason": "exact-one-action-one-resource-one-attempt"})
    result["token_sha256"] = token_digest(token)
    return request, result, token


def execute_approved_action(args, token):
    if args.action != "call_loopback_sink" or token is None:
        return {"executed": False, "side_effect_count": 0, "reason": "not-executed"}
    payload = {
        "fixture": "w6-0.1",
        "request_id": args.request_id,
        "action": args.action,
        "message": "safe-approved-fixture-sink",
    }
    request = Request(args.resource, data=encode(payload).encode("utf-8"), headers={"content-type": "application/json"})
    try:
        with urlopen(request, timeout=3) as response:
            if response.status != 200:
                return {"executed": False, "side_effect_count": 0, "reason": f"sink-status-{response.status}"}
    except Exception as exc:
        return {"executed": False, "side_effect_count": 0, "reason": f"sink-error-{type(exc).__name__}"}
    return {"executed": True, "side_effect_count": 1, "reason": "approved-loopback-sink"}


def run(args):
    workspace = Path(args.workspace).resolve()
    ledger_dir = Path(args.ledger_dir)
    policy = load_json(Path(args.policy), {"default_network": "deny", "actions": {}})
    policy_decision = policy.get("actions", {}).get(args.action)
    state_path = ledger_dir / "state.json"
    state = load_json(state_path, {"event_seq": 0, "consumed_approval_ids": [], "side_effects": {}})
    state["event_seq"] = state.get("event_seq", 0) + 1
    sequence = state["event_seq"]
    common = {
        "fixture": "w6-0.1",
        "request_id": args.request_id,
        "sequence": sequence,
        "action": args.action,
        "resource": args.resource,
        "side_effect_class": ACTION_CLASSES.get(args.action, "unknown"),
    }

    events = []
    tool_call = {"type": "tool.call", "timestamp": now(), **common}
    events.append(tool_call)
    append_jsonl(ledger_dir / "event-ledger.jsonl", tool_call)

    valid_resource, resource_reason = action_resource_is_well_formed(args.action, args.resource, workspace)
    policy_event = {
        "type": "policy.decision",
        "timestamp": now(),
        **common,
        "policy": policy_decision,
        "decision": "deny" if policy_decision in BLOCKED_STATUS else "deny",
        "reason": resource_reason if not valid_resource else ("policy-default-deny" if policy_decision in BLOCKED_STATUS else "unknown-policy-action"),
    }
    events.append(policy_event)
    append_jsonl(ledger_dir / "policy-decisions.jsonl", policy_event)
    append_jsonl(ledger_dir / "event-ledger.jsonl", policy_event)

    approval_request, approval_result, token = approval_decision(args, state, policy_decision)
    approval_request.update({"sequence": sequence, "fixture": "w6-0.1"})
    approval_result.update({"sequence": sequence, "fixture": "w6-0.1"})
    events.extend([approval_request, approval_result])
    append_jsonl(ledger_dir / "approval-ledger.jsonl", approval_request)
    append_jsonl(ledger_dir / "approval-ledger.jsonl", approval_result)
    append_jsonl(ledger_dir / "event-ledger.jsonl", approval_request)
    append_jsonl(ledger_dir / "event-ledger.jsonl", approval_result)

    if not valid_resource:
        action_result = {"executed": False, "side_effect_count": 0, "reason": resource_reason}
    elif policy_decision in BLOCKED_STATUS and token is None:
        action_result = {"executed": False, "side_effect_count": 0, "reason": "fail-closed-no-approval"}
    elif approval_result["decision"] != "granted":
        action_result = {"executed": False, "side_effect_count": 0, "reason": approval_result["reason"]}
    else:
        action_result = execute_approved_action(args, token)

    if action_result["executed"]:
        state.setdefault("side_effects", {})[args.action] = state.setdefault("side_effects", {}).get(args.action, 0) + action_result["side_effect_count"]
    tool_result = {"type": "tool.result", "timestamp": now(), **common, "status": "executed" if action_result["executed"] else "blocked", **action_result}
    events.append(tool_result)
    append_jsonl(ledger_dir / "tool-results.jsonl", tool_result)
    append_jsonl(ledger_dir / "event-ledger.jsonl", tool_result)
    state.setdefault("attempts", []).append({"request_id": args.request_id, "action": args.action, "resource": args.resource, "status": tool_result["status"], "reason": tool_result["reason"]})
    save_json(state_path, state)
    print(encode({"fixture": "w6-0.1", "request_id": args.request_id, "action": args.action, "status": tool_result["status"], "reason": tool_result["reason"], "side_effect_count": tool_result["side_effect_count"]}))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=sorted(ACTION_CLASSES))
    parser.add_argument("--resource", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--ledger-dir", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--approval-token")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        # A malformed request is a fail-closed tool failure. Do not print the
        # request or any path contents, since a resource may be a secret path.
        print(encode({"status": "blocked", "reason": f"adapter-error-{type(exc).__name__}"}))
        return 23


if __name__ == "__main__":
    sys.exit(main())
