#!/usr/bin/env python3
"""Loopback-only sink; writes received test payloads to a caller-owned file."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    output = None

    def do_POST(self):
        size = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(size) or b"{}")
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        response = b'{"accepted":true}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    Handler.output = args.output
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    args.ready_file.write_text(json.dumps({"host": args.host, "port": server.server_port}), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
