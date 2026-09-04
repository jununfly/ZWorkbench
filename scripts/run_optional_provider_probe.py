#!/usr/bin/env python3
"""Run a bounded Ark read-only staging sequence without persisting the API key.

The key is read from stdin, kept in process memory, and never written to the
result.  The result contains only redacted metadata, digests, response shape,
and a boolean semantic-fixture check.  This is an on-demand validation helper,
not a ZWorkbench Provider adapter or production request path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


SCHEMA = "zworkbench-optional-real-provider-probe/v1"
PROVIDER = "volcengine-ark"
DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/coding/v3/responses"
DEFAULT_MODEL = "ark-code-latest"
DEFAULT_REGION = "cn-beijing"
FIXTURE_ID = "staging-fixture-001"
FIXTURE_PROMPT = (
    'Return exactly JSON with keys "status" and "answer". '
    'Use status="ok" and answer="staging-fixture-001". '
    "Do not call tools, access files, create tasks, send callbacks, or write anything."
)
MAX_RESPONSE_BYTES = 1_000_000
MAX_REQUESTS = 5
REQUIRED_PREFLIGHT_GATES = (
    "key_scope_confirmed",
    "data_retention_confirmed",
    "remote_inventory_confirmed",
    "exit_path_confirmed",
    "one_time_authorization_confirmed",
)


class NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so the credential cannot follow a new destination."""

    def http_error_301(self, req: Request, fp: Any, code: int, msg: str, headers: Any) -> Any:
        raise RuntimeError("redirect disallowed")

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        raise ValueError("endpoint must use https")
    if parsed.hostname != "ark.cn-beijing.volces.com":
        raise ValueError("endpoint host is not the fixed Ark staging host")
    if parsed.path != "/api/coding/v3/responses" or parsed.query or parsed.fragment:
        raise ValueError("endpoint path is not the fixed Coding Responses path")


def read_bounded(response: Any) -> Tuple[bytes, bool]:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    return body[:MAX_RESPONSE_BYTES], len(body) > MAX_RESPONSE_BYTES


def response_shape(body: bytes) -> Dict[str, Any]:
    shape: Dict[str, Any] = {
        "body_sha256": digest(body),
        "body_bytes": len(body),
        "fixture_token_present": FIXTURE_ID.encode("utf-8") in body,
    }
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        shape["json"] = False
        return shape
    shape["json"] = True
    if isinstance(decoded, dict):
        shape["top_level_keys"] = sorted(str(key) for key in decoded.keys())
        if isinstance(decoded.get("id"), str):
            shape["response_id_sha256"] = digest(decoded["id"].encode("utf-8"))
        if isinstance(decoded.get("model"), str):
            shape["response_model"] = decoded["model"]
        error = decoded.get("error")
        if isinstance(error, Mapping):
            code = error.get("code")
            error_type = error.get("type")
            if isinstance(code, str) and len(code) <= 128 and re.fullmatch(r"[A-Za-z0-9_.:-]+", code):
                shape["error_code"] = code
            if isinstance(error_type, str) and len(error_type) <= 128 and re.fullmatch(r"[A-Za-z0-9_.:-]+", error_type):
                shape["error_type"] = error_type
    else:
        shape["top_level_type"] = type(decoded).__name__
    semantic = _semantic_shape(decoded)
    shape.update(
        {
            "response_status_ok": semantic["status_ok"],
            "response_answer_fixture": semantic["answer_ok"],
            "semantic_fixture_exact": semantic["semantic_fixture_exact"],
        }
    )
    return shape


def _semantic_shape(value: Any) -> Dict[str, bool]:
    """Extract only booleans for the fixed synthetic response contract."""

    status_ok = False
    answer_ok = False
    exact = False
    if isinstance(value, Mapping):
        exact = value.get("status") == "ok" and value.get("answer") == FIXTURE_ID
        for key, nested in value.items():
            if key == "status" and nested == "ok":
                status_ok = True
            if key == "answer" and nested == FIXTURE_ID:
                answer_ok = True
            nested_shape = _semantic_shape(nested)
            status_ok = status_ok or nested_shape["status_ok"]
            answer_ok = answer_ok or nested_shape["answer_ok"]
            exact = exact or nested_shape["semantic_fixture_exact"]
    elif isinstance(value, list):
        for nested in value:
            nested_shape = _semantic_shape(nested)
            status_ok = status_ok or nested_shape["status_ok"]
            answer_ok = answer_ok or nested_shape["answer_ok"]
            exact = exact or nested_shape["semantic_fixture_exact"]
    elif isinstance(value, str):
        try:
            nested = json.loads(value)
        except json.JSONDecodeError:
            nested = None
        if nested is not None:
            nested_shape = _semantic_shape(nested)
            status_ok = nested_shape["status_ok"]
            answer_ok = nested_shape["answer_ok"]
            exact = nested_shape["semantic_fixture_exact"]
    return {
        "status_ok": status_ok,
        "answer_ok": answer_ok,
        "semantic_fixture_exact": exact,
    }


def validate_preflight(preflight: Mapping[str, Any], *, repeats: int = 1) -> Dict[str, Any]:
    """Validate non-secret human gates before any credential is read or sent."""

    if not isinstance(preflight, Mapping):
        raise ValueError("real-provider preflight must be an object")
    region = preflight.get("region")
    if not isinstance(region, str) or not region.strip() or len(region.strip()) > 64:
        raise ValueError("real-provider region must be a short non-empty value")
    if region.strip() != DEFAULT_REGION:
        raise ValueError(f"region must be {DEFAULT_REGION} for the fixed Ark staging endpoint")
    project_fingerprint = preflight.get("project_fingerprint")
    if not isinstance(project_fingerprint, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", project_fingerprint):
        raise ValueError("project_fingerprint must be a 64-character SHA-256 hex fingerprint")
    if not isinstance(repeats, int) or not 1 <= repeats <= MAX_REQUESTS:
        raise ValueError(f"repeats must be between 1 and {MAX_REQUESTS}")
    budget_requests = preflight.get("budget_requests")
    if not isinstance(budget_requests, int) or budget_requests < repeats or budget_requests > MAX_REQUESTS:
        raise ValueError("budget_requests must cover repeats and be at most the staging limit")
    max_duration_seconds = preflight.get("max_duration_seconds")
    if not isinstance(max_duration_seconds, int) or not 1 <= max_duration_seconds <= 30:
        raise ValueError("max_duration_seconds must be between 1 and 30")
    for gate in REQUIRED_PREFLIGHT_GATES:
        if preflight.get(gate) is not True:
            raise ValueError(f"preflight gate is not confirmed: {gate}")
    return {
        "status": "verified",
        "region": region.strip(),
        "project_fingerprint": project_fingerprint.lower(),
        "budget_requests": budget_requests,
        "max_duration_seconds": max_duration_seconds,
        "gates": {gate: True for gate in REQUIRED_PREFLIGHT_GATES},
    }


def base_result(
    endpoint: str,
    model: str,
    key: bytes,
    preflight: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    request_bytes = json.dumps(
        {"model": model, "input": FIXTURE_PROMPT, "store": False},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema": SCHEMA,
        "classification": "external/on-demand; not a ZWorkbench product gate",
        "at": now(),
        "provider": PROVIDER,
        "endpoint": endpoint,
        "model": model,
        "credential": {"fingerprint_algorithm": "SHA-256", "api_key_fingerprint": digest(key)},
        "synthetic_fixture": {"id": FIXTURE_ID, "request_payload_sha256": digest(request_bytes)},
        "request_count": 0,
        "retry_count": 0,
        "compatibility_status": "not-run",
        "raw_request_or_response_persisted": False,
        "remote_resource_inventory": "not performed by this one-shot probe",
        # Do not copy caller-provided preflight text before it is validated;
        # only the verified, normalized record is emitted below.
        "preflight": {"status": "unverified" if preflight is not None else "not-provided"},
    }


def run(
    endpoint: str,
    model: str,
    key: bytes,
    *,
    preflight: Optional[Mapping[str, Any]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    result = base_result(endpoint, model, key, preflight)
    if not key:
        result["outcome"] = "input_empty"
        result["error_type"] = "EmptyCredential"
        return result
    try:
        verified_preflight = validate_preflight(preflight or {}, repeats=1)
    except ValueError as exc:
        result["outcome"] = "preflight_blocked"
        result["error_type"] = "PreflightError"
        result["error_detail"] = str(exc)
        return result
    result["preflight"] = verified_preflight
    if not isinstance(timeout, int) or not 1 <= timeout <= verified_preflight["max_duration_seconds"]:
        result["outcome"] = "preflight_blocked"
        result["error_type"] = "TimeoutBudgetError"
        return result
    try:
        key_text = key.decode("utf-8")
    except UnicodeDecodeError:
        result["outcome"] = "input_invalid_encoding"
        result["error_type"] = "CredentialEncodingError"
        return result

    payload = json.dumps(
        {"model": model, "input": FIXTURE_PROMPT, "store": False},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={"Authorization": "Bearer " + key_text, "Content-Type": "application/json"},
        method="POST",
    )
    opener = build_opener(NoRedirectHandler(), ProxyHandler({}))
    result["request_count"] = 1
    try:
        with opener.open(request, timeout=timeout) as response:
            body, truncated = read_bounded(response)
            result["http_status"] = int(response.status)
            result["outcome"] = "http_success" if 200 <= response.status < 300 else "http_error"
            result["response_truncated"] = truncated
            result["response"] = response_shape(body)
    except HTTPError as exc:
        body, truncated = read_bounded(exc)
        result["http_status"] = int(exc.code)
        result["outcome"] = "http_error"
        result["response_truncated"] = truncated
        result["response"] = response_shape(body)
    except (URLError, TimeoutError, OSError, RuntimeError) as exc:
        result["outcome"] = "transport_error"
        result["error_type"] = type(exc).__name__
    response = result.get("response") if isinstance(result.get("response"), dict) else {}
    result["compatibility_status"] = "transport-and-semantic-partial" if result["outcome"] == "http_success" and response.get("semantic_fixture_exact") is True else "unknown/stop"
    return result


def run_repeated(
    endpoint: str,
    model: str,
    key: bytes,
    *,
    preflight: Mapping[str, Any],
    repeats: int,
) -> Dict[str, Any]:
    """Run an explicitly requested bounded sequence; never retries a failure."""

    result = base_result(endpoint, model, key, preflight)
    try:
        verified_preflight = validate_preflight(preflight, repeats=repeats)
    except ValueError as exc:
        result.update({"outcome": "preflight_blocked", "error_type": "PreflightError", "error_detail": str(exc)})
        return result
    if not key:
        result.update({"outcome": "input_empty", "error_type": "EmptyCredential", "preflight": verified_preflight})
        return result
    if digest(key) == verified_preflight["project_fingerprint"]:
        result.update(
            {
                "outcome": "preflight_blocked",
                "error_type": "CredentialProjectIdentityCollisionError",
                "error_detail": "project_fingerprint matches api_key_fingerprint; provide the hash of the Ark Project/billing ID, not the API Key",
                "preflight": verified_preflight,
            }
        )
        return result
    started = time.monotonic()
    attempts = []
    for _ in range(repeats):
        remaining = verified_preflight["max_duration_seconds"] - int(time.monotonic() - started)
        if remaining < 1:
            attempts.append({"outcome": "time_budget_exhausted"})
            break
        attempt = run(
                endpoint,
                model,
                key,
                preflight=preflight,
                timeout=min(30, remaining),
            )
        attempts.append(attempt)
        if attempt.get("outcome") != "http_success" or (attempt.get("response") or {}).get("semantic_fixture_exact") is not True:
            break
    http_success = len(attempts) == repeats and all(item.get("outcome") == "http_success" for item in attempts)
    semantic = http_success and all(
        (item.get("response") or {}).get("semantic_fixture_exact") is True for item in attempts
    )
    result.update(
        {
            "preflight": verified_preflight,
            "requested_count": repeats,
            "request_count": sum(int(item.get("request_count", 0)) for item in attempts),
            "retry_count": 0,
            "attempts": [
                {
                    "outcome": item.get("outcome"),
                    "http_status": item.get("http_status"),
                    "response": item.get("response"),
                    "error_type": item.get("error_type"),
                }
                for item in attempts
            ],
            "response": {
                "attempt_count": len(attempts),
                "all_json": bool(attempts) and all((item.get("response") or {}).get("json") is True for item in attempts),
                "all_fixture_token_present": bool(attempts) and all((item.get("response") or {}).get("fixture_token_present") is True for item in attempts),
                "all_semantic_fixture_exact": semantic,
                "response_models": sorted({(item.get("response") or {}).get("response_model") for item in attempts if (item.get("response") or {}).get("response_model")}),
            },
            "outcome": "http_success" if semantic else "semantic_mismatch" if http_success else (attempts[-1].get("outcome") if attempts else "transport_error"),
            "compatibility_status": "verified-for-authorized-read-only-staging" if semantic and repeats >= 5 else "transport-and-semantic-partial" if semantic else "unknown/stop",
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--region", required=True)
    parser.add_argument("--project-fingerprint", required=True)
    parser.add_argument("--budget-requests", type=int, required=True)
    parser.add_argument("--max-duration-seconds", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=1)
    for gate in REQUIRED_PREFLIGHT_GATES:
        parser.add_argument(f"--{gate.replace('_', '-')}", action="store_true")
    args = parser.parse_args()
    try:
        validate_endpoint(args.endpoint)
    except ValueError as exc:
        raise SystemExit(str(exc))
    preflight = {
        "region": args.region,
        "project_fingerprint": args.project_fingerprint,
        "budget_requests": args.budget_requests,
        "max_duration_seconds": args.max_duration_seconds,
        **{gate: getattr(args, gate) for gate in REQUIRED_PREFLIGHT_GATES},
    }
    try:
        validate_preflight(preflight, repeats=args.repeats)
    except ValueError as exc:
        raise SystemExit(str(exc))
    key = sys.stdin.buffer.read().strip()
    result = run_repeated(args.endpoint, args.model, key, preflight=preflight, repeats=args.repeats)
    write_json(args.output / "summary.json", result)
    print(json.dumps({"summary": str((args.output / "summary.json").resolve()), "outcome": result["outcome"]}, ensure_ascii=False))
    return 0 if result["outcome"] == "http_success" else 1


if __name__ == "__main__":
    sys.exit(main())
