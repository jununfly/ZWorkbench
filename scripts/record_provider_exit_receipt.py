#!/usr/bin/env python3
"""Write a redacted, human-supplied Provider exit inventory receipt.

This helper records facts the account owner observed in a Provider console or
support workflow.  It never calls a Provider API and never accepts raw keys,
resource IDs, account identifiers, prompt text, or response bodies.  Unknown
or partially observed states remain ``unknown/safe-stop``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict


SCHEMA = "zworkbench-provider-exit-receipt/v2"
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")
SECRET_LIKE = re.compile(r"(?:sk-|AKIA|Bearer\s+|fixture-secret)", re.IGNORECASE)
STATUSES = {
    "task": {"none-observed", "identified-stopped", "identified-pending", "not-exposed-by-provider", "unknown"},
    "webhook": {"none-observed", "disabled", "identified-active", "unknown"},
    "backup": {"none-observed", "exported", "deletion-requested", "retained-by-policy", "not-exposed-by-provider", "unknown"},
    "data": {"not-requested", "requested", "confirmed", "retained-by-policy", "not-exposed-by-provider", "unknown"},
    "key": {"not-touched", "disabled", "deleted", "unknown"},
    "billing": {"not-reviewed", "settled", "pending", "unknown"},
    "subscription": {"active", "cancelled", "unknown"},
    "account": {"active", "closure-submitted", "closed", "unknown"},
    "local": {"not-reviewed", "stopped-and-cleaned", "retained-for-evidence", "unknown"},
    "action": {"not-performed", "submitted", "confirmed", "unknown"},
}
ACCOUNT_SCOPES = {"personal", "team", "organization", "service-account", "unknown"}
EXIT_MODES = {"inventory-only", "authorized-manual-exit"}
CONSOLE_OBSERVATIONS = {"no-visible-error", "visible-error", "unknown"}
REQUEST_RESPONSE_SURFACES = {"exposed", "not-exposed-by-provider", "unknown"}
SURFACE_OBSERVATIONS = {"visible-with-status", "not-exposed-by-provider", "unknown"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_fingerprint(value: str, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ValueError(f"{field} must be a 64-character SHA-256 hex fingerprint")
    return value.lower()


def validate_optional_fingerprint(value: str, field: str) -> str:
    if value == "unknown":
        return value
    return validate_fingerprint(value, field)


def validate_status(value: str, kind: str) -> str:
    if value not in STATUSES[kind]:
        choices = ", ".join(sorted(STATUSES[kind]))
        raise ValueError(f"{kind} status must be one of: {choices}")
    return value


def validate_enum(value: str, field: str, choices: set[str]) -> str:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{field} must be one of: {allowed}")
    return value


def normalize_surface_status(value: str, surface: str, kind: str) -> str:
    status = validate_status(value, kind)
    if surface == "not-exposed-by-provider":
        if status not in {"unknown", "not-exposed-by-provider"}:
            raise ValueError(f"{kind} status must be unknown when its surface is not-exposed-by-provider")
        return "not-exposed-by-provider"
    if surface == "visible-with-status":
        if status in {"unknown", "not-exposed-by-provider"}:
            raise ValueError(f"{kind} status must be an observed status when its surface is visible-with-status")
        return status
    if status != "unknown":
        raise ValueError(f"{kind} status must be unknown when its surface is unknown")
    return status


def validate_safe_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    if SECRET_LIKE.search(value):
        raise ValueError(f"{field} looks like a raw credential or secret")
    return value.strip()


def build_receipt(args: argparse.Namespace) -> Dict[str, Any]:
    project_fingerprint = validate_fingerprint(args.project_fingerprint, "project_fingerprint")
    inventory_fingerprint = validate_fingerprint(args.inventory_fingerprint, "inventory_fingerprint")
    evidence_fingerprint = validate_fingerprint(args.evidence_fingerprint, "evidence_fingerprint")
    local_state_fingerprint = validate_optional_fingerprint(args.local_state_fingerprint, "local_state_fingerprint")
    if args.region != "cn-beijing":
        raise ValueError("region must be cn-beijing for the fixed Ark profile")
    provider = validate_safe_text(args.provider, "provider")
    account_scope = validate_enum(args.account_scope, "account_scope", ACCOUNT_SCOPES)
    exit_mode = validate_enum(args.exit_mode, "exit_mode", EXIT_MODES)
    console_observation = validate_enum(
        args.provider_console_observation,
        "provider_console_observation",
        CONSOLE_OBSERVATIONS,
    )
    request_response_surface = validate_enum(
        args.provider_request_response_surface,
        "provider_request_response_surface",
        REQUEST_RESPONSE_SURFACES,
    )
    task_surface_observation = validate_enum(
        args.task_surface_observation,
        "task_surface_observation",
        SURFACE_OBSERVATIONS,
    )
    backup_surface_observation = validate_enum(
        args.backup_surface_observation,
        "backup_surface_observation",
        SURFACE_OBSERVATIONS,
    )
    retention_surface_observation = validate_enum(
        args.retention_surface_observation,
        "retention_surface_observation",
        SURFACE_OBSERVATIONS,
    )
    statuses = {
        "task_or_run": normalize_surface_status(args.task_status, task_surface_observation, "task"),
        "webhook_or_integration": validate_status(args.webhook_status, "webhook"),
        "backup_or_snapshot": normalize_surface_status(args.backup_status, backup_surface_observation, "backup"),
        "coding_data": normalize_surface_status(args.data_status, retention_surface_observation, "data"),
        "api_key": validate_status(args.key_status, "key"),
        "billing": validate_status(args.billing_status, "billing"),
        "subscription": validate_status(args.subscription_status, "subscription"),
        "account": validate_status(args.account_status, "account"),
        "local_case": validate_status(args.local_status, "local"),
        "exit_action": validate_status(args.action_status, "action"),
    }
    unknown_fields = sorted(field for field, status in statuses.items() if status == "unknown")
    if local_state_fingerprint == "unknown":
        unknown_fields.append("local_state_fingerprint")
    if console_observation == "unknown":
        unknown_fields.append("provider_console_observation")
    if request_response_surface == "unknown":
        unknown_fields.append("provider_request_response_surface")
    if task_surface_observation == "unknown":
        unknown_fields.append("task_surface_observation")
    if backup_surface_observation == "unknown":
        unknown_fields.append("backup_surface_observation")
    if retention_surface_observation == "unknown":
        unknown_fields.append("retention_surface_observation")
    unknown_fields.sort()
    if unknown_fields:
        exit_status = "unknown/safe-stop"
    elif console_observation == "visible-error":
        exit_status = "unknown/safe-stop"
    elif exit_mode == "inventory-only":
        exit_status = "inventory-recorded-exit-not-performed"
    elif statuses["exit_action"] in {"submitted", "confirmed"}:
        exit_status = "provider-receipt-recorded-final-residue-unknown"
    else:
        exit_status = "unknown/safe-stop"
    provider_observability_status = (
        "unknown/safe-stop"
        if unknown_fields or console_observation == "visible-error"
        else "pass-with-owner-attestation"
    )
    return {
        "schema": SCHEMA,
        "recorded_at": now(),
        "classification": "acceptance/evaluation; human-supplied provider-side receipt",
        "provider": provider,
        "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "region": args.region,
        "account_scope": account_scope,
        "provider_console_observation": console_observation,
        "provider_request_response_surface": request_response_surface,
        "surface_observations": {
            "task_or_run": task_surface_observation,
            "backup_or_snapshot": backup_surface_observation,
            "retention_policy": retention_surface_observation,
        },
        "project_fingerprint": project_fingerprint,
        "inventory_fingerprint": inventory_fingerprint,
        "evidence_fingerprint": evidence_fingerprint,
        "local_state_fingerprint": local_state_fingerprint,
        "exit_mode": exit_mode,
        "statuses": statuses,
        "exit_status": exit_status,
        "provider_observability_status": provider_observability_status,
        "unknown_fields": unknown_fields,
        "provider_remote_zero_residue": "unknown/delegated",
        "notes": "No raw key, raw resource ID, prompt, response body, or remote API payload is recorded.",
        "non_claims": [
            "A key deletion or account closure receipt does not prove historical prompt/output/log/backup zero residue.",
            "A submitted deletion request is not a deletion completion proof.",
            "No-visible-error and not-exposed-by-provider describe product observability only; they do not prove backend retention is absent.",
            "The receipt records account-owner evidence; ZWorkbench does not own Provider-side resources.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", default="volcengine-ark")
    parser.add_argument("--region", default="cn-beijing")
    parser.add_argument("--account-scope", choices=sorted(ACCOUNT_SCOPES), default="personal")
    parser.add_argument(
        "--provider-console-observation",
        choices=sorted(CONSOLE_OBSERVATIONS),
        default="unknown",
    )
    parser.add_argument(
        "--provider-request-response-surface",
        choices=sorted(REQUEST_RESPONSE_SURFACES),
        default="unknown",
    )
    parser.add_argument(
        "--task-surface-observation",
        choices=sorted(SURFACE_OBSERVATIONS),
        default="unknown",
    )
    parser.add_argument(
        "--backup-surface-observation",
        choices=sorted(SURFACE_OBSERVATIONS),
        default="unknown",
    )
    parser.add_argument(
        "--retention-surface-observation",
        choices=sorted(SURFACE_OBSERVATIONS),
        default="unknown",
    )
    parser.add_argument("--project-fingerprint", required=True)
    parser.add_argument("--inventory-fingerprint", required=True)
    parser.add_argument("--evidence-fingerprint", required=True)
    parser.add_argument("--local-state-fingerprint", default="unknown")
    parser.add_argument("--exit-mode", choices=sorted(EXIT_MODES), required=True)
    parser.add_argument("--task-status", required=True)
    parser.add_argument("--webhook-status", required=True)
    parser.add_argument("--backup-status", required=True)
    parser.add_argument("--data-status", required=True)
    parser.add_argument("--key-status", required=True)
    parser.add_argument("--billing-status", required=True)
    parser.add_argument("--subscription-status", required=True)
    parser.add_argument("--account-status", required=True)
    parser.add_argument("--local-status", required=True)
    parser.add_argument("--action-status", required=True)
    args = parser.parse_args()
    try:
        output = args.output.expanduser().resolve()
        if output.exists():
            raise FileExistsError(f"receipt output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        receipt = build_receipt(args)
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"schema": SCHEMA, "status": "recorded", "receipt": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
