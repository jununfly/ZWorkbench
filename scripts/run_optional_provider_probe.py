#!/usr/bin/env python3
"""Run one deliberately small Ark request without persisting the API key.

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
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


SCHEMA = "zworkbench-optional-real-provider-probe/v1"
PROVIDER = "volcengine-ark"
DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/coding/v3/responses"
DEFAULT_MODEL = "ark-code-latest"
FIXTURE_ID = "staging-fixture-001"
FIXTURE_PROMPT = (
    'Return exactly JSON with keys "status" and "answer". '
    'Use status="ok" and answer="staging-fixture-001". '
    "Do not call tools, access files, create tasks, send callbacks, or write anything."
)
MAX_RESPONSE_BYTES = 1_000_000


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
    else:
        shape["top_level_type"] = type(decoded).__name__
    return shape


def base_result(endpoint: str, model: str, key: bytes) -> Dict[str, Any]:
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
        "raw_request_or_response_persisted": False,
        "remote_resource_inventory": "not performed by this one-shot probe",
    }


def run(endpoint: str, model: str, key: bytes) -> Dict[str, Any]:
    result = base_result(endpoint, model, key)
    if not key:
        result["outcome"] = "input_empty"
        result["error_type"] = "EmptyCredential"
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
        with opener.open(request, timeout=30) as response:
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
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        validate_endpoint(args.endpoint)
    except ValueError as exc:
        raise SystemExit(str(exc))
    key = sys.stdin.buffer.read().strip()
    result = run(args.endpoint, args.model, key)
    write_json(args.output / "summary.json", result)
    print(json.dumps({"summary": str((args.output / "summary.json").resolve()), "outcome": result["outcome"]}, ensure_ascii=False))
    return 0 if result["outcome"] == "http_success" else 1


if __name__ == "__main__":
    sys.exit(main())
