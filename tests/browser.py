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

#: A dispatched key is processed asynchronously; reading ``activeElement``
#: immediately after the write can observe the focus that preceded it.
KEY_SETTLE_SECONDS = 0.05

#: Only the keys the review contracts need. Each entry is the full identity a
#: real key press carries: an engine that receives a partial descriptor may
#: accept the event and then act on nothing.
_KEYS = {
    "Tab": {"code": "Tab", "vk": 9, "modifiers": 0},
    "ShiftTab": {"code": "Tab", "vk": 9, "modifiers": 8},
    "Escape": {"code": "Escape", "vk": 27, "modifiers": 0},
    "ArrowUp": {"code": "ArrowUp", "vk": 38, "modifiers": 0},
    # Ctrl+C as the keyboard plan declares it; ``text`` makes Chrome treat it
    # as a character chord rather than a bare raw key.
    "CtrlC": {"code": "KeyC", "key": "c", "vk": 67, "modifiers": 2, "text": "c"},
    "ArrowDown": {"code": "ArrowDown", "vk": 40, "modifiers": 0},
    # ``text`` is what makes Enter activate the focused control. Without it
    # Chrome delivers the key event but performs no default action, so a button
    # never sees a click and a keyboard activation test quietly asserts nothing.
    "Enter": {"code": "Enter", "vk": 13, "modifiers": 0, "text": "\r"},
}


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
        # A headless window never gains OS focus, so the document reports
        # itself unfocused: focus/blur events do not fire and :focus-visible
        # never matches. That is a property of the harness, not of the page,
        # and leaving it in place would make every focus assertion measure the
        # window manager instead of the product.
        self._connection.call("Emulation.setFocusEmulationEnabled", enabled=True)
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

    def press(self, key: str) -> None:
        """Dispatch one real key press to the page.

        ``rawKeyDown`` is used rather than ``keyDown`` because the latter
        expects the text of a character key; for navigation keys Chrome then
        ignores the event and focus does not move, silently turning a focus
        order assertion into a measurement of the initial focus.
        """
        descriptor = _KEYS[key]
        text = descriptor.get("text")
        for kind in ("keyDown" if text else "rawKeyDown", "keyUp"):
            event = {
                "type": kind,
                # DOM ``key`` is the character ("c"), ``code`` the physical
                # key ("KeyC"); for navigation keys the two coincide.
                "key": descriptor.get("key", descriptor["code"]),
                "code": descriptor["code"],
                "windowsVirtualKeyCode": descriptor["vk"],
                "nativeVirtualKeyCode": descriptor["vk"],
                "modifiers": descriptor["modifiers"],
            }
            if text and kind == "keyDown":
                event["text"] = text
            self._connection.call("Input.dispatchKeyEvent", **event)
            time.sleep(KEY_SETTLE_SECONDS)

    def move(self, x: float, y: float) -> None:
        """Dispatch a real mouse move at viewport coordinates.

        Hover is an engine decision: only a dispatched move says which element
        the engine considers hovered, which is what a preview highlight must
        track.
        """
        self._connection.call(
            "Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y
        )
        time.sleep(KEY_SETTLE_SECONDS)

    def click(self, x: float, y: float, modifiers: int = 0) -> None:
        """Dispatch a real mouse click at viewport coordinates.

        Hit testing says which element sits under a point; only a dispatched
        click says which element the engine delivers the event to. The two can
        disagree when a layer is transparent to hit testing but still receives
        input, which is precisely the failure passthrough must exclude.
        """
        for kind in ("mousePressed", "mouseReleased"):
            self._connection.call(
                "Input.dispatchMouseEvent",
                type=kind,
                x=x,
                y=y,
                button="left",
                buttons=1 if kind == "mousePressed" else 0,
                clickCount=1,
                modifiers=modifiers,
            )
        time.sleep(KEY_SETTLE_SECONDS)

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
