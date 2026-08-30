#!/usr/bin/env python3
"""Loopback Responses provider used by the W7 Codex C5/C6 fixture."""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCHEMA = "zworkbench-w7-codex-c56-provider/v1"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def append_jsonl(path: Path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode(value) + "\n")
        handle.flush()


class ProviderHandler(BaseHTTPRequestHandler):
    provider_id = "w7-fake-codex-c56"
    request_log = None
    mode = "normal"
    capabilities = []
    emit_tool = False
    fixture_command = "printf fixture-ok"
    request_count = 0

    def log_message(self, *_args):
        return

    def record(self, value):
        append_jsonl(self.request_log, {"schema": SCHEMA, "provider_id": self.provider_id, **value})

    def send_json(self, status, payload):
        data = encode(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def send_sse(self, events, include_done=True):
        try:
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "close")
            self.end_headers()
            for event in events:
                event_data = {"type": event["type"], **event["data"]}
                payload = f"event: {event['type']}\ndata: {encode(event_data)}\n\n".encode("utf-8")
                self.wfile.write(payload)
                self.wfile.flush()
            if include_done:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "provider_id": self.provider_id, "capabilities": self.capabilities})
            return
        if self.path == "/v1/models":
            self.send_json(200, {"object": "list", "data": [{"id": "fake-model", "object": "model", "owned_by": self.provider_id}]})
            return
        if self.path == "/v1/capabilities":
            self.record({"kind": "capability_probe", "path": self.path, "capabilities": self.capabilities})
            self.send_json(200, {"provider_id": self.provider_id, "model": "fake-model", "capabilities": self.capabilities})
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
        type_name = "message"
        if self.emit_tool and output_count == 0:
            type_name = "function_call"
        self.__class__.request_count += 1
        request_number = self.request_count
        self.record({
            "kind": "responses_request",
            "path": self.path,
            "model": body.get("model"),
            "stream": body.get("stream"),
            "request_number": request_number,
            "function_call_output_count": output_count,
            "response_kind": type_name,
            "mode": self.mode,
        })
        if self.mode == "timeout_once" and request_number == 1:
            time.sleep(2.0)
        if self.mode == "stream_interrupt_once" and request_number == 1:
            self.send_sse([
                {"type": "response.created", "data": {"response": {"id": f"c56-response-{request_number:03d}", "object": "response", "status": "in_progress", "model": "fake-model"}}},
                {"type": "response.output_text.delta", "data": {"delta": "partial"}},
            ], include_done=False)
            return
        if type_name == "function_call":
            call = {
                "type": "function_call",
                "id": f"c56-function-{request_number:03d}",
                "call_id": f"c56-call-{request_number:03d}",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": self.fixture_command}, separators=(",", ":")),
                "status": "completed",
            }
            response = {
                "id": f"c56-response-{request_number:03d}",
                "object": "response",
                "created_at": 1788048000,
                "status": "completed",
                "model": "fake-model",
                "output": [call],
                "output_text": "",
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            }
            events = [
                {"type": "response.created", "data": {"response": {"id": response["id"], "object": "response", "status": "in_progress", "model": "fake-model"}}},
                {"type": "response.output_item.added", "data": {"output_index": 0, "item": {"type": "function_call", "id": call["id"], "status": "in_progress", "call_id": call["call_id"], "name": call["name"], "arguments": ""}}},
                {"type": "response.function_call_arguments.delta", "data": {"item_id": call["id"], "output_index": 0, "delta": call["arguments"]}},
                {"type": "response.function_call_arguments.done", "data": {"item_id": call["id"], "output_index": 0, "arguments": call["arguments"]}},
                {"type": "response.output_item.done", "data": {"output_index": 0, "item": call}},
                {"type": "response.completed", "data": {"response": response}},
            ]
        else:
            message = {
                "type": "message",
                "id": f"c56-message-{request_number:03d}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "fixture-ok", "annotations": []}],
            }
            response = {
                "id": f"c56-response-{request_number:03d}",
                "object": "response",
                "created_at": 1788048000,
                "status": "completed",
                "model": "fake-model",
                "output": [message],
                "output_text": "fixture-ok",
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            }
            events = [
                {"type": "response.created", "data": {"response": {"id": response["id"], "object": "response", "status": "in_progress", "model": "fake-model"}}},
                {"type": "response.output_item.added", "data": {"output_index": 0, "item": {"type": "message", "id": message["id"], "status": "in_progress", "role": "assistant", "content": []}}},
                {"type": "response.content_part.added", "data": {"item_id": message["id"], "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}}},
                {"type": "response.output_text.delta", "data": {"item_id": message["id"], "output_index": 0, "content_index": 0, "delta": "fixture-ok"}},
                {"type": "response.output_text.done", "data": {"item_id": message["id"], "output_index": 0, "content_index": 0, "text": "fixture-ok"}},
                {"type": "response.content_part.done", "data": {"item_id": message["id"], "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "fixture-ok", "annotations": []}}},
                {"type": "response.output_item.done", "data": {"output_index": 0, "item": message}},
                {"type": "response.completed", "data": {"response": response}},
            ]
        self.record({"kind": "responses_result", "request_number": request_number, "status": "completed", "response_kind": type_name})
        if body.get("stream", True):
            self.send_sse(events)
        else:
            self.send_json(200, response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--mode", choices=["normal", "timeout_once", "stream_interrupt_once"], default="normal")
    parser.add_argument("--capabilities", default="tool_calls,streaming,structured_output")
    parser.add_argument("--emit-tool", action="store_true")
    parser.add_argument("--command", default="printf fixture-ok")
    parser.add_argument("--request-log", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    args = parser.parse_args()
    ProviderHandler.provider_id = args.provider_id
    ProviderHandler.request_log = args.request_log
    ProviderHandler.mode = args.mode
    ProviderHandler.capabilities = [item for item in args.capabilities.split(",") if item]
    ProviderHandler.emit_tool = args.emit_tool
    ProviderHandler.fixture_command = args.command
    ProviderHandler.request_count = 0
    server = ThreadingHTTPServer((args.host, args.port), ProviderHandler)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(encode({"host": args.host, "port": server.server_port, "provider_id": args.provider_id}) + "\n", encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
