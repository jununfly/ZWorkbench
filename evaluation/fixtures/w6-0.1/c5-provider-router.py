#!/usr/bin/env python3
"""Candidate-independent Provider failover contract for W6 C5.

This is an acceptance fixture, not ZWorkbench product code.  It only talks to
the two loopback fake Providers supplied by the C5 runner and writes an
auditable attempt/fallback ledger for one deterministic task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUTER_VERSION = "w6-c5-provider-router/v1"
STRUCTURED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "task", "schema_version"],
    "properties": {
        "answer": {"type": "string"},
        "task": {"type": "string"},
        "schema_version": {"type": "string"},
    },
}


class ProviderFailure(Exception):
    def __init__(self, reason, detail="", status=None, raw_body=""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason
        self.status = status
        self.raw_body = raw_body


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def append_jsonl(path: Path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local_endpoint(endpoint):
    return endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")


def parse_error_body(error):
    try:
        payload = json.loads(error.read().decode("utf-8"))
        return payload, json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, ""


class ProviderClient:
    def __init__(self, provider_id, endpoint, model, output_dir, timeout=0.6):
        self.provider_id = provider_id
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.output_dir = output_dir
        self.timeout = timeout

    def metadata(self):
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "endpoint": self.endpoint,
        }

    def capabilities(self):
        started = time.monotonic()
        event = {
            "type": "provider.capability_detection",
            "observed_at": utc_now(),
            **self.metadata(),
            "capability_endpoint": f"{self.endpoint}/v1/capabilities",
        }
        try:
            request = Request(f"{self.endpoint}/v1/capabilities", method="GET")
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            provider_id = payload.get("provider_id")
            capabilities = payload.get("capabilities")
            if provider_id != self.provider_id or not isinstance(capabilities, list):
                raise ProviderFailure("capability_metadata_invalid", "Provider identity or capability list mismatch")
            event.update({
                "status": "success",
                "capabilities": sorted(str(item) for item in capabilities),
                "duration_ms": round((time.monotonic() - started) * 1000),
            })
            append_jsonl(self.output_dir / "capability-detection.jsonl", event)
            return set(event["capabilities"])
        except HTTPError as error:
            payload, raw_body = parse_error_body(error)
            event.update({
                "status": "error",
                "reason": "capability_probe_http_error",
                "http_status": error.code,
                "response": payload,
                "raw_response_sha256": hashlib.sha256(raw_body.encode()).hexdigest(),
                "duration_ms": round((time.monotonic() - started) * 1000),
            })
            append_jsonl(self.output_dir / "capability-detection.jsonl", event)
            raise ProviderFailure("capability_probe_http_error", raw_body or str(error), error.code, raw_body)
        except (ProviderFailure, socket.timeout, TimeoutError, URLError, OSError, json.JSONDecodeError) as error:
            reason = error.reason if isinstance(error, ProviderFailure) else "capability_probe_error"
            event.update({
                "status": "error",
                "reason": reason,
                "detail": str(error),
                "duration_ms": round((time.monotonic() - started) * 1000),
            })
            append_jsonl(self.output_dir / "capability-detection.jsonl", event)
            raise ProviderFailure(reason, str(error))

    def complete(self, task, capabilities, attempt_number):
        structured = bool(task.get("requires_structured_output"))
        body = {
            "model": self.model,
            "stream": True,
            "messages": [{
                "role": "user",
                "content": "Return the deterministic W6 C5 fixture answer for provider-failover-v1.",
            }],
        }
        if structured:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "provider_failover_v1",
                    "strict": True,
                    "schema": STRUCTURED_SCHEMA,
                },
            }
        request_event = {
            "type": "provider.request",
            "observed_at": utc_now(),
            "attempt": attempt_number,
            **self.metadata(),
            "path": "/v1/chat/completions",
            "stream": True,
            "structured_output_requested": structured,
            "request": body,
            "request_sha256": sha256_json(body),
        }
        append_jsonl(self.output_dir / "provider-events.jsonl", request_event)
        attempt = {
            "attempt": attempt_number,
            "phase": "provider_request",
            "status": "started",
            "started_at": utc_now(),
            **self.metadata(),
            "structured_output_requested": structured,
        }
        started = time.monotonic()
        try:
            request = Request(
                f"{self.endpoint}/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                response_status = response.status
                response_type = response.headers.get("content-type", "")
                if "text/event-stream" in response_type:
                    chunks = []
                    while True:
                        line = response.readline()
                        if not line:
                            break
                        chunks.append(line)
                        if line.strip() == b"data: [DONE]":
                            break
                    raw = b"".join(chunks)
                else:
                    raw = response.read()
            content, response_metadata = self._decode_response(raw, response_type, structured)
            semantic = normalize_semantic(content, structured)
            response_event = {
                "type": "provider.response",
                "observed_at": utc_now(),
                "attempt": attempt_number,
                **self.metadata(),
                "http_status": response_status,
                "content_type": response_type,
                "response": response_metadata,
                "semantic_result": semantic,
                "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
            }
            append_jsonl(self.output_dir / "provider-events.jsonl", response_event)
            attempt.update({
                "status": "success",
                "finished_at": utc_now(),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "semantic_result": semantic,
                "semantic_signature": sha256_json(semantic),
                "http_status": response_status,
                "response_metadata": response_metadata,
            })
            append_jsonl(self.output_dir / "attempt-history.jsonl", attempt)
            return {"semantic_result": semantic, "attempt": attempt}
        except HTTPError as error:
            payload, raw_body = parse_error_body(error)
            reason = str(payload.get("error", {}).get("type", "http_error")) if isinstance(payload.get("error"), dict) else "http_error"
            failure = ProviderFailure(reason, raw_body or str(error), error.code, raw_body)
            return self._record_failure(attempt, request_event, failure, started)
        except (socket.timeout, TimeoutError) as error:
            return self._record_failure(attempt, request_event, ProviderFailure("timeout", str(error)), started)
        except URLError as error:
            reason = "timeout" if isinstance(error.reason, (socket.timeout, TimeoutError)) else "provider_unreachable"
            return self._record_failure(attempt, request_event, ProviderFailure(reason, str(error)), started)
        except ProviderFailure as error:
            return self._record_failure(attempt, request_event, error, started)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return self._record_failure(attempt, request_event, ProviderFailure("response_decode_error", str(error)), started)

    def _record_failure(self, attempt, request_event, failure, started):
        error_event = {
            "type": "provider.error",
            "observed_at": utc_now(),
            "attempt": attempt["attempt"],
            **self.metadata(),
            "reason": failure.reason,
            "detail": failure.detail,
            "http_status": failure.status,
            "raw_response_sha256": hashlib.sha256(failure.raw_body.encode()).hexdigest() if failure.raw_body else None,
        }
        append_jsonl(self.output_dir / "provider-events.jsonl", error_event)
        attempt.update({
            "status": "failed",
            "finished_at": utc_now(),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "reason": failure.reason,
            "detail": failure.detail,
            "http_status": failure.status,
        })
        append_jsonl(self.output_dir / "attempt-history.jsonl", attempt)
        return {"failure": failure, "attempt": attempt}

    def _decode_response(self, raw, content_type, structured):
        text = raw.decode("utf-8")
        if "text/event-stream" not in content_type:
            payload = json.loads(text)
            choices = payload.get("choices", [])
            content = choices[0].get("message", {}).get("content") if choices else None
            if content is None:
                raise ProviderFailure("response_semantics_invalid", "response has no assistant content")
            return content, {
                "protocol": "chat-completions",
                "stream_complete": True,
                "finish_reason": choices[0].get("finish_reason") if choices else None,
                "content": content,
            }
        content_parts = []
        finish_reason = None
        saw_done = False
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                saw_done = True
                continue
            payload = json.loads(data)
            for choice in payload.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    content_parts.append(delta["content"])
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        if not saw_done or finish_reason != "stop":
            raise ProviderFailure(
                "stream_interrupt",
                f"incomplete stream: done={saw_done}, finish_reason={finish_reason}",
            )
        content = "".join(content_parts)
        if not content:
            raise ProviderFailure("response_semantics_invalid", "stream has no assistant content")
        return content, {
            "protocol": "chat-completions",
            "stream_complete": True,
            "finish_reason": finish_reason,
            "content": content,
        }


def normalize_semantic(content, structured):
    if structured:
        semantic = json.loads(content)
        expected = {
            "answer": "fixture-ok",
            "task": "provider-failover-v1",
            "schema_version": "v1",
        }
        if semantic != expected:
            raise ProviderFailure("semantic_result_mismatch", f"expected {expected}, got {semantic}")
        return semantic
    if content != "fixture-ok":
        raise ProviderFailure("semantic_result_mismatch", f"expected fixture-ok, got {content!r}")
    return {"answer": "fixture-ok"}


def run(task, clients, primary_id, fallback_id, output_dir):
    primary = clients[primary_id]
    fallback = clients.get(fallback_id) if fallback_id else None
    attempts = []
    fallback_events = []
    degradation_events = []
    capability_records = {}
    expected_structured = bool(task.get("requires_structured_output"))

    def detect(client):
        try:
            capabilities = client.capabilities()
            capability_records[client.provider_id] = {
                **client.metadata(),
                "status": "success",
                "capabilities": sorted(capabilities),
            }
            return capabilities
        except ProviderFailure as error:
            capability_records[client.provider_id] = {
                **client.metadata(),
                "status": "error",
                "reason": error.reason,
                "detail": error.detail,
            }
            return set()

    primary_capabilities = detect(primary)
    decision_reason = None
    if expected_structured and "structured_output" not in primary_capabilities:
        decision_reason = "capability_missing:structured_output"
        degradation_events.append({
            "type": "provider.degradation",
            "observed_at": utc_now(),
            "from_provider": primary.provider_id,
            "to_provider": fallback.provider_id if fallback else None,
            "reason": decision_reason,
            "required_capability": "structured_output",
            "action": "fallback" if fallback else "safe_failure",
        })
    else:
        response = primary.complete(task, primary_capabilities, 1)
        attempts.append(response["attempt"])
        if "failure" not in response:
            final = response
        else:
            decision_reason = response["failure"].reason

    if decision_reason:
        if fallback:
            fallback_capabilities = detect(fallback)
            if expected_structured and "structured_output" not in fallback_capabilities:
                degradation_events.append({
                    "type": "provider.degradation",
                    "observed_at": utc_now(),
                    "from_provider": fallback.provider_id,
                    "to_provider": None,
                    "reason": "capability_missing:structured_output",
                    "required_capability": "structured_output",
                    "action": "safe_failure",
                })
                final = None
            else:
                fallback_reason = decision_reason
                fallback_event = {
                    "type": "provider.fallback",
                    "observed_at": utc_now(),
                    "from_provider": primary.provider_id,
                    "to_provider": fallback.provider_id,
                    "reason": fallback_reason,
                    "retry_policy": "switch-provider-no-same-provider-retry",
                    "required_capability": "structured_output" if expected_structured else None,
                }
                fallback_events.append(fallback_event)
                append_jsonl(output_dir / "fallback-ledger.jsonl", fallback_event)
                response = fallback.complete(task, fallback_capabilities, len(attempts) + 1)
                attempts.append(response["attempt"])
                final = response if "failure" not in response else None
        else:
            final = None

    for event in degradation_events:
        append_jsonl(output_dir / "degradation-ledger.jsonl", event)

    expected_semantic = (
        {"answer": "fixture-ok", "task": "provider-failover-v1", "schema_version": "v1"}
        if expected_structured
        else {"answer": "fixture-ok"}
    )
    final_semantic = final["semantic_result"] if final else None
    final_attempt = final["attempt"] if final else None
    silent_semantic_change = bool(final_semantic is not None and final_semantic != expected_semantic)
    result = {
        "schema": "zworkbench-w6-c5-case/v1",
        "router_version": ROUTER_VERSION,
        "status": "completed" if final else "safe_failed",
        "task": task,
        "primary_provider": primary.metadata(),
        "fallback_provider": fallback.metadata() if fallback else None,
        "capability_detection": list(capability_records.values()),
        "attempt_history": attempts,
        "fallback_ledger": fallback_events,
        "degradation_ledger": degradation_events,
        "final": {
            "provider": final_attempt["provider_id"] if final_attempt else None,
            "model": final_attempt["model"] if final_attempt else None,
            "endpoint": final_attempt["endpoint"] if final_attempt else None,
            "semantic_result": final_semantic,
            "semantic_signature": sha256_json(final_semantic) if final_semantic is not None else None,
            "expected_semantic_result": expected_semantic,
            "silent_semantic_change": silent_semantic_change,
        },
        "decision": {
            "outcome": "fallback" if fallback_events else ("degraded_safe_failure" if decision_reason else "primary_success"),
            "reason": decision_reason,
            "same_provider_retry": False,
        },
        "local_only": all(local_endpoint(client.endpoint) for client in clients.values()),
    }
    write_json(output_dir / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--primary-id", required=True)
    parser.add_argument("--primary-url", required=True)
    parser.add_argument("--fallback-id")
    parser.add_argument("--fallback-url")
    parser.add_argument("--model", default="fake-model")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    task = json.loads(args.task.read_text(encoding="utf-8"))
    clients = {
        args.primary_id: ProviderClient(args.primary_id, args.primary_url, args.model, args.output_dir),
    }
    if args.fallback_id and args.fallback_url:
        clients[args.fallback_id] = ProviderClient(args.fallback_id, args.fallback_url, args.model, args.output_dir)
    result = run(task, clients, args.primary_id, args.fallback_id, args.output_dir)
    print(json.dumps({
        "status": result["status"],
        "primary_provider": args.primary_id,
        "final_provider": result["final"]["provider"],
        "fallback_count": len(result["fallback_ledger"]),
        "decision_reason": result["decision"]["reason"],
        "result": str(args.output_dir / "result.json"),
    }, ensure_ascii=False, indent=2))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
