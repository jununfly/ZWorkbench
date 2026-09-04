#!/usr/bin/env python3
"""A case-local, auditable capability broker for acceptance evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCHEMA = "zworkbench-w8-capability-broker/v1"
POLICY_SCHEMA = "zworkbench-w8-capability-broker-policy/v1"
DENIED_EXIT = 23
BROKER_ERROR_EXIT = 24
KNOWN_OPERATIONS = {"dns.resolve", "network.connect", "credential.read", "process.spawn", "effect.write"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def policy_digest(policy: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(policy)).hexdigest()


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def canonical_path(value: Any) -> Optional[Path]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    return Path(value).expanduser().resolve()


def within_workspace(target: Path, workspace: Path) -> bool:
    try:
        target.relative_to(workspace)
    except ValueError:
        return False
    return target != workspace


def text_field(request: Dict[str, Any], name: str, limit: int = 512) -> Optional[str]:
    value = request.get(name)
    return value if isinstance(value, str) and value and len(value) <= limit else None


def base_receipt(request: Dict[str, Any], digest: str) -> Dict[str, Any]:
    request_id = request.get("request_id")
    operation = request.get("operation")
    return {
        "schema": SCHEMA,
        "at": now(),
        "request_id": request_id if isinstance(request_id, str) and len(request_id) <= 200 else "invalid-request-id",
        "operation": operation if isinstance(operation, str) else "unknown",
        "resource_class": request.get("resource_class") if isinstance(request.get("resource_class"), str) else "unknown",
        "policy_sha256": digest,
        "decision": "deny",
        "reason": "unknown",
        "effect_status": "not-performed",
        "physical_effect_count": 0,
        "external_io_count": 0,
    }


def deny(receipt: Dict[str, Any], reason: str, target_class: str = "unknown") -> Dict[str, Any]:
    receipt.update({"decision": "deny", "reason": reason, "target_class": target_class})
    return receipt


def allow(receipt: Dict[str, Any], reason: str, target_class: str = "case-local") -> Dict[str, Any]:
    receipt.update({"decision": "allow", "reason": reason, "target_class": target_class})
    return receipt


def process_request(request: Any, policy: Dict[str, Any], audit_path: Path) -> Dict[str, Any]:
    """Make one policy decision and, if permitted, perform one case-local effect."""

    digest = policy_digest(policy)
    if not isinstance(request, dict):
        receipt = deny(base_receipt({}, digest), "request_not_object")
        append_jsonl(audit_path, receipt)
        return receipt

    receipt = base_receipt(request, digest)
    if policy.get("schema") != POLICY_SCHEMA:
        receipt = deny(receipt, "policy_schema_mismatch")
    elif not isinstance(request.get("schema"), str) or request.get("schema") != SCHEMA:
        receipt = deny(receipt, "request_schema_mismatch")
    elif not isinstance(request.get("request_id"), str) or not request.get("request_id"):
        receipt = deny(receipt, "request_id_required")
    elif request.get("operation") not in KNOWN_OPERATIONS:
        receipt = deny(receipt, "unknown_operation")
    else:
        operation = request["operation"]
        workspace = canonical_path(policy.get("workspace"))
        allowed_operations = policy.get("allowed_operations")
        if not isinstance(allowed_operations, list) or operation not in allowed_operations:
            receipt = deny(receipt, "operation_not_allowlisted", operation)
        elif operation == "credential.read":
            receipt = deny(receipt, "credential_access_not_allowlisted", "credential")
        elif operation == "dns.resolve":
            hostname = text_field(request, "hostname", 253)
            allowed_dns = policy.get("allowed_dns")
            if not hostname:
                receipt = deny(receipt, "hostname_required", "dns-name")
            elif not isinstance(allowed_dns, dict) or hostname not in allowed_dns:
                receipt = deny(receipt, "dns_name_not_allowlisted", "dns-name")
            elif not isinstance(allowed_dns[hostname], list) or not all(isinstance(item, str) for item in allowed_dns[hostname]):
                receipt = deny(receipt, "dns_allowlist_invalid", "dns-name")
            else:
                receipt = allow(receipt, "loopback_dns_static_allowlist", "dns-name")
                receipt["resolved_addresses"] = list(allowed_dns[hostname])
                receipt["resolution_mode"] = "static-broker-allowlist"
        elif operation == "network.connect":
            host = text_field(request, "host", 253)
            port = request.get("port")
            allowed_network = policy.get("allowed_network")
            endpoint = {"host": host, "port": port}
            if not host or not isinstance(port, int) or not (0 < port < 65536):
                receipt = deny(receipt, "network_endpoint_invalid", "network-endpoint")
            elif not isinstance(allowed_network, list) or endpoint not in allowed_network:
                receipt = deny(receipt, "network_endpoint_not_allowlisted", "network-endpoint")
            else:
                receipt = allow(receipt, "loopback_endpoint_allowlisted", "network-endpoint")
                receipt["execution_mode"] = "decision-only-no-connect"
        elif operation == "process.spawn":
            executable = text_field(request, "executable", 4096)
            allowed_processes = policy.get("allowed_processes")
            if not executable:
                receipt = deny(receipt, "executable_required", "process")
            elif not isinstance(allowed_processes, list) or executable not in allowed_processes:
                receipt = deny(receipt, "process_not_allowlisted", "process")
            else:
                receipt = allow(receipt, "process_allowlisted_decision_only", "process")
                receipt["execution_mode"] = "decision-only-no-spawn"
        elif operation == "effect.write":
            target = canonical_path(request.get("target"))
            content = request.get("content")
            if workspace is None:
                receipt = deny(receipt, "workspace_invalid", "path")
            elif target is None:
                receipt = deny(receipt, "target_invalid", "path")
            elif not within_workspace(target, workspace):
                receipt = deny(receipt, "target_outside_workspace", "path")
            elif not isinstance(content, str):
                receipt = deny(receipt, "content_not_text", "path")
            else:
                receipt = allow(receipt, "allowlisted_workspace_write", "workspace-path")
                receipt["phase"] = "decision"
                receipt["effect_status"] = "claimed"
                receipt["target_relative"] = str(target.relative_to(workspace))
                append_jsonl(audit_path, receipt)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("w", encoding="utf-8") as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                except OSError as exc:
                    failed = dict(receipt)
                    failed.update({"at": now(), "phase": "reconcile-required", "effect_status": "unknown", "physical_effect_count": None, "reason": "write_reconcile_required", "error_type": type(exc).__name__})
                    append_jsonl(audit_path, failed)
                    return failed
                completed = dict(receipt)
                completed.update({"at": now(), "phase": "complete", "effect_status": "completed", "physical_effect_count": 1})
                append_jsonl(audit_path, completed)
                return completed

    append_jsonl(audit_path, receipt)
    return receipt


def serve(socket_path: Path, policy_path: Path, audit_path: Path) -> int:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(8)
    try:
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                data = b""
                while b"\n" not in data:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                try:
                    request = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
                    response = process_request(request, policy, audit_path)
                except Exception as exc:
                    response = deny(base_receipt({}, policy_digest(policy)), "broker_protocol_error")
                    response["error_type"] = type(exc).__name__
                    append_jsonl(audit_path, response)
                connection.sendall((json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


def send_request(socket_path: Path, request: Dict[str, Any]) -> Dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(str(socket_path))
        connection.sendall((json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = connection.recv(65536)
            if not chunk:
                break
            data += chunk
    value = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("broker response must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    server = subparsers.add_parser("server")
    server.add_argument("--socket", type=Path, required=True)
    server.add_argument("--policy", type=Path, required=True)
    server.add_argument("--audit", type=Path, required=True)
    client = subparsers.add_parser("client")
    client.add_argument("--socket", type=Path, required=True)
    client.add_argument("--request-json", required=True)
    args = parser.parse_args()
    if args.mode == "server":
        return serve(args.socket.expanduser().resolve(), args.policy.expanduser().resolve(), args.audit.expanduser().resolve())
    try:
        request = json.loads(args.request_json)
        response = send_request(args.socket.expanduser().resolve(), request)
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "decision": "deny", "reason": "broker_unavailable", "error_type": type(exc).__name__}, ensure_ascii=False))
        return BROKER_ERROR_EXIT
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0 if response.get("decision") == "allow" else DENIED_EXIT


if __name__ == "__main__":
    sys.exit(main())
