#!/usr/bin/env python3
"""Minimal loopback-only OpenAI-compatible fake provider for W6."""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    provider_id = "fake-a"
    fault = None
    fault_used = False
    verbose = False
    response_number = 0
    scenario = "plain"
    request_log = None
    c2_plan = None

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "provider_id": self.provider_id})
            return
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "fake-model", "model": "fake-model"}]})
            return
        if self.path == "/api/version":
            self._send(200, {"version": "0.13.4"})
            return
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": "fake-model", "object": "model", "owned_by": self.provider_id}]})
            return
        if self.path == "/v1/capabilities":
            self._record_control_request(self.path)
            self._send(200, {
                "provider_id": self.provider_id,
                "model": "fake-model",
                "capabilities": self._capabilities(),
            })
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path not in {"/v1/chat/completions", "/v1/responses", "/api/chat"}:
            self._send(404, {"error": "not_found"})
            return
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        if self.verbose:
            print(json.dumps({"path": self.path, "body": body}, sort_keys=True), flush=True)
        fault_injected = self.fault and not self.fault_used
        self._record_request(body, fault_injected=fault_injected)
        if fault_injected and self.fault == "timeout_once":
            self.__class__.fault_used = True
            # The router has a deliberately short read timeout.  Sleeping here
            # makes this a transport timeout rather than a merely scripted 503.
            time.sleep(2.0)
            self._send(503, {"error": {"type": self.fault, "provider": self.provider_id}})
            return
        stream_interrupted = fault_injected and self.fault == "stream_interrupt_once"
        if stream_interrupted:
            self.__class__.fault_used = True
        if body.get("response_format") and "structured_output" not in self._capabilities():
            self._send(400, {
                "error": {
                    "type": "structured_output_unsupported",
                    "provider": self.provider_id,
                    "capability": "structured_output",
                }
            })
            return
        model = body.get("model", "fake-model")
        if self.path == "/api/chat":
            self._send(200, {
                "model": model,
                "created_at": "2026-08-30T00:00:00Z",
                "message": {"role": "assistant", "content": self._response_content(body)},
                "done": True,
                "done_reason": "stop",
            })
            return
        if self.path == "/v1/responses":
            self.__class__.response_number += 1
            response_id = f"fake-response-{self.response_number:03d}"
            message_id = f"fake-message-{self.response_number:03d}"
            function_call = self._next_function_call(body, self.response_number)
            output = [function_call] if function_call else [{
                "type": "message",
                "id": message_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "fixture-ok", "annotations": []}],
            }]
            response = {
                "id": response_id,
                "object": "response",
                "created_at": 1788048000,
                "status": "completed",
                "model": model,
                "output": output,
                "output_text": "" if function_call else "fixture-ok",
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            }
            if body.get("stream", True):
                events = [
                    {"type": "response.created", "response": {"id": response_id, "object": "response", "status": "in_progress", "model": model}},
                ]
                if function_call:
                    events.extend([
                        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "id": function_call["id"], "status": "in_progress", "call_id": function_call["call_id"], "name": function_call["name"], "arguments": ""}},
                        {"type": "response.function_call_arguments.delta", "item_id": function_call["id"], "output_index": 0, "delta": function_call["arguments"]},
                        {"type": "response.function_call_arguments.done", "item_id": function_call["id"], "output_index": 0, "arguments": function_call["arguments"]},
                        {"type": "response.output_item.done", "output_index": 0, "item": function_call},
                    ])
                else:
                    events.extend([
                        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "id": message_id, "status": "in_progress", "role": "assistant", "content": []}},
                        {"type": "response.content_part.added", "item_id": message_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
                        {"type": "response.output_text.delta", "item_id": message_id, "output_index": 0, "content_index": 0, "delta": "fixture-ok"},
                        {"type": "response.output_text.done", "item_id": message_id, "output_index": 0, "content_index": 0, "text": "fixture-ok"},
                        {"type": "response.content_part.done", "item_id": message_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "fixture-ok", "annotations": []}},
                        {"type": "response.output_item.done", "output_index": 0, "item": response["output"][0]},
                    ])
                events.append({"type": "response.completed", "response": response})
                self._send_sse(events, interrupted=stream_interrupted)
            else:
                self._send(200, response)
            return
        response = {
            "id": "fake-response-001",
            "object": "chat.completion",
            "model": model,
            "choices": [self._chat_choice(body)],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }
        if body.get("stream", True):
            self._send_chat_sse(body, response, interrupted=stream_interrupted)
            return
        self._send(200, response)

    def log_message(self, *_args):
        if self.verbose:
            print(*_args, flush=True)

    def _send(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send_sse(self, events, interrupted=False):
        try:
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "keep-alive")
            self.end_headers()
            for index, event in enumerate(events):
                encoded = ("event: %s\ndata: %s\n\n" % (event["type"], json.dumps(event, separators=(",", ":")))).encode("utf-8")
                self.wfile.write(encoded)
                self.wfile.flush()
                if interrupted and index == 0:
                    self.close_connection = True
                    return
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _next_function_call(self, body, sequence):
        if self.scenario == "c2":
            plan = self._load_c2_plan()
            completed = sum(1 for item in body.get("input", []) if item.get("type") == "function_call_output")
            if completed >= len(plan):
                return None
            item = plan[completed]
            arguments = {"cmd": item["command"], "description": item.get("description", "C2 guarded action")}
            return {
                "type": "function_call",
                "id": f"fake-function-{sequence:03d}",
                "call_id": f"fake-call-{sequence:03d}",
                "name": "exec_command",
                "arguments": json.dumps(arguments, separators=(",", ":")),
                "status": "completed",
            }
        if self.scenario != "c1":
            return None
        completed = sum(1 for item in body.get("input", []) if item.get("type") == "function_call_output")
        if completed >= 2:
            return None
        if completed == 0:
            arguments = {"command": "python3 -c 'from pathlib import Path; p=Path(\"src/tinycalc/normalize.py\"); p.write_text(p.read_text().replace(\"\\\"_\\\".join\", \"\\\"-\\\".join\")); t=Path(\"tests/test_normalize.py\"); s=t.read_text(); marker=\"\\n\\nif __name__ == \\\"__main__\\\":\"; addition=\"\\n\\n    def test_empty_label_is_stable(self):\\n        self.assertEqual(normalize_label(\\\"\\\"), \\\"\\\")\"; t.write_text(s.replace(marker, addition + marker) if \"test_empty_label_is_stable\" not in s else s)'", "description": "Fix label normalization and add regression test"}
        else:
            arguments = {"command": "PYTHONPATH=src python3 -m unittest discover -s tests -v", "description": "Run the Python test suite"}
        if "command" in arguments:
            arguments = {"cmd": arguments["command"]}
        return {
            "type": "function_call",
            "id": f"fake-function-{sequence:03d}",
            "call_id": f"fake-call-{sequence:03d}",
            "name": "exec_command",
            "arguments": json.dumps(arguments, separators=(",", ":")),
            "status": "completed",
        }

    def _load_c2_plan(self):
        if not self.c2_plan:
            return []
        return json.loads(Path(self.c2_plan).read_text(encoding="utf-8"))

    def _capabilities(self):
        capabilities = ["tool_calls", "streaming"]
        if self.provider_id == "fake-a":
            capabilities.append("structured_output")
        if self.fault == "structured_output_unsupported":
            capabilities = [item for item in capabilities if item != "structured_output"]
        return capabilities

    def _response_content(self, body):
        if body.get("response_format"):
            return json.dumps({
                "answer": "fixture-ok",
                "task": "provider-failover-v1",
                "schema_version": "v1",
            }, separators=(",", ":"))
        return "fixture-ok"

    def _record_control_request(self, path):
        if not self.request_log:
            return
        with self.request_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "provider_id": self.provider_id,
                "path": path,
                "kind": "capability_probe",
                "model": "fake-model",
                "capabilities": self._capabilities(),
            }, sort_keys=True) + "\n")

    def _record_request(self, body, fault_injected=False):
        if not self.request_log:
            return
        request = {
            "provider_id": self.provider_id,
            "path": self.path,
            "model": body.get("model"),
            "stream": body.get("stream"),
            "response_format": body.get("response_format"),
            "structured_output_requested": bool(body.get("response_format")),
            "fault_configured": self.fault,
            "fault_injected": bool(fault_injected),
            "input_types": [item.get("type") for item in body.get("input", []) if isinstance(item, dict)],
            "function_call_output_count": sum(1 for item in body.get("input", []) if isinstance(item, dict) and item.get("type") == "function_call_output"),
        }
        if self.scenario == "c2":
            plan = self._load_c2_plan()
            request["scripted_call"] = plan[request["function_call_output_count"]]["action"] if request["function_call_output_count"] < len(plan) else None
        with self.request_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(request, sort_keys=True) + "\n")

    def _chat_choice(self, body):
        """Return the same two-step C1 script over Chat Completions."""
        if self.scenario == "c2":
            plan = self._load_c2_plan()
            messages = body.get("messages", [])
            completed = sum(1 for item in messages if item.get("role") == "tool")
            if completed >= len(plan):
                return {
                    "index": 0,
                    "message": {"role": "assistant", "content": "fixture-ok"},
                    "finish_reason": "stop",
                }
            item = plan[completed]
            arguments = {"command": item["command"], "description": item.get("description", "C2 guarded action")}
            return {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"fake-chat-call-{completed + 1:03d}",
                        "type": "function",
                        "function": {"name": "bash", "arguments": json.dumps(arguments, separators=(",", ":"))},
                    }],
                },
                "finish_reason": "tool_calls",
            }
        if self.scenario != "c1":
            return {
                "index": 0,
                "message": {"role": "assistant", "content": self._response_content(body)},
                "finish_reason": "stop",
            }
        messages = body.get("messages", [])
        completed = sum(1 for item in messages if item.get("role") == "tool")
        if completed >= 2:
            return {
                "index": 0,
                "message": {"role": "assistant", "content": "fixture-ok"},
                "finish_reason": "stop",
            }
        if completed == 0:
            arguments = {"cmd": "python3 -c 'from pathlib import Path; p=Path(\"src/tinycalc/normalize.py\"); p.write_text(p.read_text().replace(\"\\\"_\\\".join\", \"\\\"-\\\".join\")); t=Path(\"tests/test_normalize.py\"); s=t.read_text(); marker=\"\\n\\nif __name__ == \\\"__main__\\\":\"; addition=\"\\n\\n    def test_empty_label_is_stable(self):\\n        self.assertEqual(normalize_label(\\\"\\\"), \\\"\\\")\"; t.write_text(s.replace(marker, addition + marker) if \"test_empty_label_is_stable\" not in s else s)'"}
        else:
            arguments = {"cmd": "PYTHONPATH=src python3 -m unittest discover -s tests -v"}
        if "cmd" in arguments:
            description = "Fix label normalization and add regression test" if "normalize.py" in arguments["cmd"] else "Run the Python test suite"
            arguments = {"command": arguments["cmd"], "description": description}
        return {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"fake-chat-call-{completed + 1:03d}",
                    "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps(arguments, separators=(",", ":"))},
                }],
            },
            "finish_reason": "tool_calls",
        }

    def _send_chat_sse(self, body, response, interrupted=False):
        choice = response["choices"][0]
        response_id = response["id"]
        model = response["model"]
        events = []
        if choice["finish_reason"] == "tool_calls":
            call = choice["message"]["tool_calls"][0]
            function = call["function"]
            events.extend([
                {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": call["id"], "type": "function", "function": {"name": function["name"], "arguments": function["arguments"]}}]}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": response["usage"]},
            ])
        else:
            events.extend([
                {"choices": [{"index": 0, "delta": {"role": "assistant", "content": self._response_content(body)}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": response["usage"]},
            ])
        try:
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "keep-alive")
            self.end_headers()
            for index, event in enumerate(events):
                encoded = ("data: %s\n\n" % json.dumps(event, separators=(",", ":"))).encode("utf-8")
                self.wfile.write(encoded)
                self.wfile.flush()
                if interrupted and index == 0:
                    self.close_connection = True
                    return
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--provider-id", default="fake-a")
    parser.add_argument("--fault")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--scenario", default="plain")
    parser.add_argument("--request-log", type=Path)
    parser.add_argument("--c2-plan", type=Path)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    Handler.provider_id = args.provider_id
    Handler.fault = args.fault
    Handler.fault_used = False
    Handler.response_number = 0
    Handler.verbose = args.verbose
    Handler.scenario = args.scenario
    Handler.request_log = args.request_log
    Handler.c2_plan = args.c2_plan
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    if args.ready_file:
        args.ready_file.write_text(json.dumps({"host": args.host, "port": server.server_port}), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
