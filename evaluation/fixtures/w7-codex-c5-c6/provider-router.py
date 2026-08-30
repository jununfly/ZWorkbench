#!/usr/bin/env python3
"""Case-local Provider router for the real Codex OSS endpoint."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


SCHEMA = "zworkbench-w7-codex-c56-router/v1"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path: Path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()


def backend_request(endpoint, method, path, body=None, timeout=0.45):
    parsed = urlparse(endpoint)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    headers = {}
    if body is not None:
        headers["content-type"] = "application/json"
        headers["content-length"] = str(len(body))
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        return response.status, response.getheader("content-type", "application/json"), data
    finally:
        connection.close()


class RouterHandler(BaseHTTPRequestHandler):
    config = {}
    event_log = None
    request_number = 0

    def log_message(self, *_args):
        return

    def event(self, event_type, **payload):
        append_jsonl(self.event_log, {"schema": SCHEMA, "type": event_type, **payload})

    def send_bytes(self, status, content_type, data):
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        if self.path == "/health":
            self.send_bytes(200, "application/json", encode({"ok": True, "router": "w7-codex-c56"}).encode("utf-8"))
            return
        provider = self.config["providers"][self.config["primary"]]
        try:
            status, content_type, data = backend_request(provider["endpoint"], "GET", self.path)
            self.send_bytes(status, content_type, data)
        except Exception as exc:
            self.event("provider.request.failed", method="GET", path=self.path, reason=type(exc).__name__)
            self.send_bytes(502, "application/json", encode({"error": "provider_unavailable"}).encode("utf-8"))

    def dispatch(self, provider_id, body, attempt_number):
        provider = self.config["providers"][provider_id]
        self.event("provider.attempt", attempt=attempt_number, provider_id=provider_id, model="fake-model", endpoint=provider["endpoint"], status="started")
        try:
            status, content_type, data = backend_request(provider["endpoint"], "POST", "/v1/responses", body)
            if status != 200:
                raise RuntimeError(f"http_status_{status}")
            if b"data: [DONE]" not in data:
                raise RuntimeError("stream_interrupt")
            self.event("provider.attempt", attempt=attempt_number, provider_id=provider_id, model="fake-model", endpoint=provider["endpoint"], status="succeeded")
            return status, content_type, data, None
        except (OSError, socket.timeout, TimeoutError, RuntimeError) as exc:
            reason = "timeout" if isinstance(exc, (socket.timeout, TimeoutError)) else str(exc)
            self.event("provider.attempt", attempt=attempt_number, provider_id=provider_id, model="fake-model", endpoint=provider["endpoint"], status="failed", reason=reason)
            return None, None, None, reason

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_bytes(404, "application/json", encode({"error": "not_found"}).encode("utf-8"))
            return
        size = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(size)
        self.__class__.request_number += 1
        request_number = self.request_number
        primary = self.config["primary"]
        fallback = self.config.get("fallback")
        status, content_type, data, reason = self.dispatch(primary, body, request_number)
        if reason and fallback:
            self.event("provider.fallback", from_provider=primary, to_provider=fallback, reason=reason, attempt=request_number)
            status, content_type, data, second_reason = self.dispatch(fallback, body, request_number + 1)
            if second_reason:
                self.send_bytes(502, "application/json", encode({"error": "provider_fallback_failed"}).encode("utf-8"))
                return
        if reason and not fallback:
            self.send_bytes(502, "application/json", encode({"error": "provider_unavailable", "reason": reason}).encode("utf-8"))
            return
        self.send_bytes(status, content_type, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--event-log", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.event_log.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(args.event_log, {"schema": SCHEMA, "type": "router.started", "primary": config["primary"], "fallback": config.get("fallback"), "pre_dispatch_reason": config.get("pre_dispatch_reason")})
    RouterHandler.config = config
    RouterHandler.event_log = args.event_log
    RouterHandler.request_number = 0
    server = ThreadingHTTPServer((args.host, args.port), RouterHandler)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(encode({"host": args.host, "port": server.server_port}) + "\n", encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
