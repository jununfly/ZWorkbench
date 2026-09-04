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


SCHEMA = "zworkbench-provider-exit-receipt/v1"
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")
SECRET_LIKE = re.compile(r"(?:sk-|AKIA|Bearer\s+|fixture-secret)", re.IGNORECASE)
STATUSES = {
    "task": {"none-observed", "identified-stopped", "identified-pending", "unknown"},
    "webhook": {"none-observed", "disabled", "identified-active", "unknown"},
    "backup": {"none-observed", "exported", "deletion-requested", "retained-by-policy", "unknown"},
    "data": {"not-requested", "requested", "confirmed", "retained-by-policy", "unknown"},
    "key": {"not-touched", "disabled", "deleted", "unknown"},
    "billing": {"not-reviewed", "settled", "pending", "unknown"},
    "subscription": {"active", "cancelled", "unknown"},
    "account": {"active", "closure-submitted", "closed", "unknown"},
    "local": {"not-reviewed", "stopped-and-cleaned", "retained-for-evidence", "unknown"},
    "action": {"not-performed", "submitted", "confirmed", "unknown"},
}


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
    account_scope = validate_safe_text(args.account_scope, "account_scope")
    statuses = {
        "task_or_run": validate_status(args.task_status, "task"),
        "webhook_or_integration": validate_status(args.webhook_status, "webhook"),
        "backup_or_snapshot": validate_status(args.backup_status, "backup"),
        "coding_data": validate_status(args.data_status, "data"),
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
    unknown_fields.sort()
    if unknown_fields:
        exit_status = "unknown/safe-stop"
    elif args.exit_mode == "inventory-only":
        exit_status = "inventory-recorded-exit-not-performed"
    elif statuses["exit_action"] in {"submitted", "confirmed"}:
        exit_status = "provider-receipt-recorded-final-residue-unknown"
    else:
        exit_status = "unknown/safe-stop"
    return {
        "schema": SCHEMA,
        "recorded_at": now(),
        "classification": "acceptance/evaluation; human-supplied provider-side receipt",
        "provider": provider,
        "endpoint": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "region": args.region,
        "account_scope": account_scope,
        "project_fingerprint": project_fingerprint,
        "inventory_fingerprint": inventory_fingerprint,
        "evidence_fingerprint": evidence_fingerprint,
        "local_state_fingerprint": local_state_fingerprint,
        "exit_mode": args.exit_mode,
        "statuses": statuses,
        "exit_status": exit_status,
        "unknown_fields": unknown_fields,
        "provider_remote_zero_residue": "unknown/delegated",
        "notes": "No raw key, raw resource ID, prompt, response body, or remote API payload is recorded.",
        "non_claims": [
            "A key deletion or account closure receipt does not prove historical prompt/output/log/backup zero residue.",
            "A submitted deletion request is not a deletion completion proof.",
            "The receipt records account-owner evidence; ZWorkbench does not own Provider-side resources.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", default="volcengine-ark")
    parser.add_argument("--region", default="cn-beijing")
    parser.add_argument("--account-scope", default="personal")
    parser.add_argument("--project-fingerprint", required=True)
    parser.add_argument("--inventory-fingerprint", required=True)
    parser.add_argument("--evidence-fingerprint", required=True)
    parser.add_argument("--local-state-fingerprint", default="unknown")
    parser.add_argument("--exit-mode", choices=("inventory-only", "authorized-manual-exit"), required=True)
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
