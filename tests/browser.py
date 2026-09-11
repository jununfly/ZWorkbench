"""A minimal CDP client, used to observe the host in a real engine.

ADR 0004 records why the evidence comes from a local browser: layout, computed
style, focus order and clipboard behaviour do not exist in a string, so any
assertion about them made against markup is measuring the test's own model of
a browser rather than a browser.

This is test support, not a product dependency. Chrome is an external tool for
the verification stage; ``pyproject.toml`` stays dependency-free. When Chrome
is absent the caller skips and the surface stays ``unknown`` -- an unavailable
engine is not evidence of correct behaviour.

Three ordering rules are encoded here because each one fails silently:

* ``setDeviceMetricsOverride`` must follow ``Page.navigate``. Reversed, the
  viewport collapses to 1x1 and ``elementFromPoint`` returns null everywhere.
* The page must be reached over ``http://127.0.0.1``. ``data:`` and ``file:``
  are not secure contexts, so ``navigator.clipboard`` is undefined there.
* The browser is only exposed as a context manager. Skipping cleanup leaves a
  live process and a temporary profile directory behind.
* The debugging target must be selected, never taken as ``targets[0]``. Chrome
  lists component-extension background pages alongside the tab, in an order
  that is not stable, so an unfiltered pick attaches to an empty extension
  document and every query answers about that document instead.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

#: Only the stable CDP 1.3 domains are used: Page, Runtime, Emulation.
NAVIGATION_SETTLE_SECONDS = 0.3


def chrome_available() -> bool:
    """Whether the verification-stage browser is present on this machine."""
    return os.path.exists(CHROME)


def _select_page(targets):
    """Pick the actual tab out of the debugging target list.

    Anything that is not a ``page``, and any page served from a
    ``chrome-extension://`` or ``devtools://`` origin, belongs to the browser
    rather than to the document under test.
    """
    for target in targets:
        url = target.get("url", "")
        if target.get("type") != "page":
            continue
        if url.startswith("chrome-extension://") or url.startswith("devtools://"):
            continue
        if not target.get("webSocketDebuggerUrl"):
            continue
        return target
    return None


class _WebSocket:
    """Just enough RFC 6455 to carry CDP frames over one connection."""

    def __init__(self, url: str) -> None:
        _, rest = url.split("://", 1)
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self._sock = socket.create_connection((host, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self._sock.sendall(
            (
                "GET /{0} HTTP/1.1\r\nHost: {1}\r\nUpgrade: websocket\r\n"
                "Connection: Upgrade\r\nSec-WebSocket-Key: {2}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).format(path, hostport, key).encode()
        )
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            buffer += self._sock.recv(4096)
        self._next_id = 0

    def _send(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        size = len(data)
        header = b"\x81"
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", size)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        self._sock.sendall(header + mask + masked)

    def _receive(self) -> dict:
        def read(count: int) -> bytes:
            chunk = b""
            while len(chunk) < count:
                chunk += self._sock.recv(count - len(chunk))
            return chunk

        _, second = read(2)
        size = second & 0x7F
        if size == 126:
            size = struct.unpack(">H", read(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", read(8))[0]
        return json.loads(read(size).decode())

    def call(self, method: str, **params) -> dict:
        self._next_id += 1
        message_id = self._next_id
        self._send({"id": message_id, "method": method, "params": params})
        while True:
            message = self._receive()
            if message.get("id") == message_id:
                return message

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()


class Browser:
    """A headless engine driving one page. Obtain one via :func:`browser`."""

    def __init__(self, connection: "_WebSocket") -> None:
        self._connection = connection

    def open(self, url: str, viewport=None) -> None:
        """Navigate to a loopback URL, then apply the viewport override.

        The order matters: overriding device metrics before navigation leaves
        the page at a 1x1 viewport, which quietly breaks hit testing.
        """
        self._connection.call("Page.enable")
        self._connection.call("Page.navigate", url=url)
        time.sleep(NAVIGATION_SETTLE_SECONDS)
        if viewport is not None:
            width, height = viewport
            self._connection.call(
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=height,
                deviceScaleFactor=1,
                mobile=False,
            )
            time.sleep(NAVIGATION_SETTLE_SECONDS)

    def evaluate(self, expression: str):
        """Evaluate an expression in the page and return it by value."""
        response = self._connection.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        result = response["result"]
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"].get("text", "page error"))
        return result["result"].get("value")


@contextlib.contextmanager
def browser():
    """Start a headless browser and guarantee the process and profile go away."""
    profile = tempfile.mkdtemp(prefix="zworkbench-ui-")
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    process = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            # Component extensions publish background pages as debugging
            # targets; without this the target list is noisy and racy.
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--remote-debugging-port={0}".format(port),
            "--user-data-dir=" + profile,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection = None
    try:
        listing = "http://127.0.0.1:{0}/json/list".format(port)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            try:
                targets = json.load(opener.open(listing, timeout=1))
            except Exception:
                time.sleep(0.2)
                continue
            page = _select_page(targets)
            if page is not None:
                connection = _WebSocket(page["webSocketDebuggerUrl"])
                break
            time.sleep(0.2)
        if connection is None:
            raise RuntimeError("the browser did not expose a page target")
        yield Browser(connection)
    finally:
        if connection is not None:
            connection.close()
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)
