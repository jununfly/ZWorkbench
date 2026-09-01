#!/usr/bin/env python3
"""Loopback Chat Completions provider for the DeepSeek ACP parity runner."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time


SCHEMA = "zworkbench-w8-deepseek-c34-provider/v1"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def append_jsonl(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()


class ProviderHandler(BaseHTTPRequestHandler):
    provider_id = "w8-deepseek-fake"
    request_log: Path | None = None
    mode = "normal"
    command = "printf fixture-ok"
    retry_command = "printf fixture-ok"
    request_number = 0
    first_fault_used = False

    def log_message(self, *_args):
        return

    def send_json(self, status, payload):
        body = encode(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "provider_id": self.provider_id})
            return
        if self.path == "/v1/models":
            self.send_json(200, {"object": "list", "data": [{"id": "deepseek-v4-flash", "object": "model", "owned_by": self.provider_id}]})
            return
        if self.path == "/v1/capabilities":
            self.send_json(200, {"provider_id": self.provider_id, "model": "deepseek-v4-flash", "capabilities": ["tool_calls", "streaming"]})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": "not_found"})
            return
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        messages = body.get("messages", [])
        tool_result_count = sum(1 for item in messages if isinstance(item, dict) and item.get("role") == "tool")
        last_user = ""
        for item in reversed(messages):
            if isinstance(item, dict) and item.get("role") == "user":
                content = item.get("content", "")
                last_user = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                break

        # A bounded retry is an explicit composition decision. The resumed
        # conversation already contains the failed tool result, so checking
        # tool_result_count first would incorrectly turn RETRY_TOOL into a
        # plain assistant message and skip the retry effect entirely.
        retry_requested = "RETRY_TOOL" in last_user
        type_name = "function_call" if retry_requested or (tool_result_count == 0 and "NO_TOOL" not in last_user) else "message"
        configured_command = self.__class__.retry_command if "RETRY_TOOL" in last_user else self.__class__.command
        self.__class__.request_number += 1
        request_number = self.request_number
        fault_injected = False
        if self.mode in {"turn_interrupt", "provider_timeout"} and not self.first_fault_used:
            self.__class__.first_fault_used = True
            fault_injected = True
        append_jsonl(self.request_log, {
            "schema": SCHEMA,
            "provider_id": self.provider_id,
            "path": self.path,
            "model": body.get("model"),
            "stream": body.get("stream"),
            "request_number": request_number,
            "tool_result_count": tool_result_count,
            "response_kind": type_name,
            "fault_configured": self.mode,
            "fault_injected": fault_injected,
            "last_user_marker": next((marker for marker in ("RETRY_TOOL", "RECONCILE_NO_TOOL", "INITIAL") if marker in last_user), None),
        })
        if fault_injected:
            # Log admission before sleeping so the runner can inject cancel
            # while the model request is genuinely in flight.
            time.sleep(2.0)
        if self.mode == "process_interrupt" and tool_result_count > 0:
            # The runner kills ACP after observing the tool result and this
            # second Provider request, before a turn-completion response.
            time.sleep(5.0)

        if type_name == "function_call":
            call = {
                "id": f"w8-dsh-function-{request_number:03d}",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({
                        "command": configured_command,
                        "description": "W8 DeepSeek parity case-local effect",
                    }, separators=(",", ":")),
                },
            }
            choice = {
                "index": 0,
                "delta": {"tool_calls": [{"index": 0, **call}]},
                "finish_reason": None,
            }
            finish = {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}
        else:
            choice = {
                "index": 0,
                "delta": {"role": "assistant", "content": "fixture-ok"},
                "finish_reason": None,
            }
            finish = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}

        events = [
            {"choices": [choice]},
            finish,
        ]
        if body.get("stream", True):
            try:
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "keep-alive")
                self.end_headers()
                for event in events:
                    self.wfile.write(("data: " + encode(event) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            return
        response_id = f"w8-dsh-response-{request_number:03d}"
        payload = {
            "id": response_id,
            "object": "chat.completion",
            "model": body.get("model", "deepseek-v4-flash"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "fixture-ok"} if type_name == "message" else {"role": "assistant", "content": None, "tool_calls": [call]},
                "finish_reason": "stop" if type_name == "message" else "tool_calls",
            }],
            "usage": finish["usage"],
        }
        self.send_json(200, payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--provider-id", default="w8-deepseek-fake")
    parser.add_argument("--mode", choices=["normal", "turn_interrupt", "provider_timeout", "tool_timeout", "process_interrupt"], default="normal")
    parser.add_argument("--command", required=True)
    parser.add_argument("--retry-command", required=True)
    parser.add_argument("--request-log", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    args = parser.parse_args()
    ProviderHandler.provider_id = args.provider_id
    ProviderHandler.request_log = args.request_log
    ProviderHandler.mode = args.mode
    ProviderHandler.command = args.command
    ProviderHandler.retry_command = args.retry_command
    ProviderHandler.request_number = 0
    ProviderHandler.first_fault_used = False
    server = ThreadingHTTPServer((args.host, args.port), ProviderHandler)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(encode({"host": args.host, "port": server.server_port, "provider_id": args.provider_id}) + "\n", encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
