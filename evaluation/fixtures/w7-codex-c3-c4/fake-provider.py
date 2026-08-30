#!/usr/bin/env python3
"""Deterministic loopback Responses provider for the W7 Codex adapter.

It emits one local ``exec_command`` call and then ``fixture-ok``.  Delay
injection is controlled by the case and never leaves loopback.  The provider
does not perform tools or effects itself.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def append_jsonl(path: Path | None, value):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


class ProviderHandler(BaseHTTPRequestHandler):
    provider_id = "w7-fake-codex"
    request_log: Path | None = None
    mode = "normal"
    script_command = ""
    retry_script_command = ""
    initial_delay_ms = 0
    post_tool_delay_ms = 0
    timeout_delay_ms = 0
    request_count = 0

    def log_message(self, *_args):
        return

    def do_GET(self):
        if self.path == "/v1/models":
            self.send_json(200, {"object": "list", "data": [{"id": "fake-model", "object": "model", "owned_by": self.provider_id}]})
            return
        if self.path == "/health":
            self.send_json(200, {"ok": True, "provider_id": self.provider_id})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_json(404, {"error": "not_found"})
            return
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        inputs = body.get("input", [])
        output_count = sum(1 for item in inputs if isinstance(item, dict) and item.get("type") == "function_call_output")
        text = " ".join(
            item.get("text", "")
            for item in inputs
            if isinstance(item, dict) and item.get("type") == "message"
            for item in item.get("content", [])
            if isinstance(item, dict) and item.get("type") == "input_text"
        )
        self.__class__.request_count += 1
        request = {
            "provider_id": self.provider_id,
            "path": self.path,
            "model": body.get("model"),
            "stream": body.get("stream"),
            "function_call_output_count": output_count,
            "request_number": self.request_count,
            "mode": self.mode,
            "prompt_markers": [marker for marker in ("W7_RECONCILE_NO_TOOL", "W7_RETRY_TOOL", "W7_INITIAL") if marker in text],
        }
        append_jsonl(self.request_log, request)

        if "W7_RECONCILE_NO_TOOL" in text:
            self.respond_message(body)
            return
        retrying = "W7_RETRY_TOOL" in text
        if self.mode == "provider_timeout" and output_count == 0 and not retrying:
            time.sleep(self.timeout_delay_ms / 1000)
        elif output_count == 0 and not retrying:
            time.sleep(self.initial_delay_ms / 1000)
        elif output_count > 0:
            time.sleep(self.post_tool_delay_ms / 1000)

        if output_count == 0:
            self.respond_function_call(body, self.retry_script_command if retrying else self.script_command)
        else:
            self.respond_message(body)

    def send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def send_sse(self, events):
        try:
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            # The Responses stream is complete after [DONE].  Closing the
            # loopback connection makes EOF explicit for app-server clients
            # that wait for both response.completed and stream termination.
            self.send_header("connection", "close")
            self.end_headers()
            for event in events:
                payload = (f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n").encode("utf-8")
                self.wfile.write(payload)
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def respond_function_call(self, body, command):
        call = {
            "type": "function_call",
            "id": f"w7-function-{self.request_count:03d}",
            "call_id": f"w7-call-{self.request_count:03d}",
            "name": "exec_command",
            "arguments": command,
            "status": "completed",
        }
        response = {
            "id": f"w7-response-{self.request_count:03d}",
            "object": "response",
            "created_at": 1788048000,
            "status": "completed",
            "model": body.get("model", "fake-model"),
            "output": [call],
            "output_text": "",
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        }
        if body.get("stream", True):
            self.send_sse([
                {"type": "response.created", "response": {"id": response["id"], "object": "response", "status": "in_progress", "model": response["model"]}},
                {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "id": call["id"], "status": "in_progress", "call_id": call["call_id"], "name": call["name"], "arguments": ""}},
                {"type": "response.function_call_arguments.delta", "item_id": call["id"], "output_index": 0, "delta": call["arguments"]},
                {"type": "response.function_call_arguments.done", "item_id": call["id"], "output_index": 0, "arguments": call["arguments"]},
                {"type": "response.output_item.done", "output_index": 0, "item": call},
                {"type": "response.completed", "response": response},
            ])
        else:
            self.send_json(200, response)

    def respond_message(self, body):
        message = {
            "type": "message",
            "id": f"w7-message-{self.request_count:03d}",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "fixture-ok", "annotations": []}],
        }
        response = {
            "id": f"w7-response-{self.request_count:03d}",
            "object": "response",
            "created_at": 1788048000,
            "status": "completed",
            "model": body.get("model", "fake-model"),
            "output": [message],
            "output_text": "fixture-ok",
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        }
        if body.get("stream", True):
            self.send_sse([
                {"type": "response.created", "response": {"id": response["id"], "object": "response", "status": "in_progress", "model": response["model"]}},
                {"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "id": message["id"], "status": "in_progress", "role": "assistant", "content": []}},
                {"type": "response.content_part.added", "item_id": message["id"], "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
                {"type": "response.output_text.delta", "item_id": message["id"], "output_index": 0, "content_index": 0, "delta": "fixture-ok"},
                {"type": "response.output_text.done", "item_id": message["id"], "output_index": 0, "content_index": 0, "text": "fixture-ok"},
                {"type": "response.content_part.done", "item_id": message["id"], "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "fixture-ok", "annotations": []}},
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": response},
            ])
        else:
            self.send_json(200, response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--provider-id", default="w7-fake-codex")
    parser.add_argument("--mode", choices=["normal", "before_tool", "provider_timeout", "after_tool", "process_interrupt", "tool_timeout"], default="normal")
    parser.add_argument("--command", required=True)
    parser.add_argument("--retry-command")
    parser.add_argument("--request-log", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    ProviderHandler.provider_id = args.provider_id
    ProviderHandler.mode = args.mode
    ProviderHandler.script_command = args.command
    ProviderHandler.retry_script_command = args.retry_command or args.command
    ProviderHandler.request_log = args.request_log
    ProviderHandler.initial_delay_ms = 800 if args.mode == "before_tool" else 0
    ProviderHandler.post_tool_delay_ms = 900 if args.mode in {"after_tool", "process_interrupt"} else 0
    ProviderHandler.timeout_delay_ms = 1600
    server = ThreadingHTTPServer((args.host, args.port), ProviderHandler)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(json.dumps({"host": args.host, "port": server.server_port, "provider_id": args.provider_id}) + "\n", encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
