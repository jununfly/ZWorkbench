"""The workbench host: a read-only loopback entry point for the three views.

ADR 0003 makes this a deliberately thin seam. The host serves server-rendered
HTML over ``http://127.0.0.1`` and owns nothing: no session, no canonical state
and no business action. It renders an already-redacted presentation model and
returns it; a request can never create a run, an effect or an approval.

Two properties here are load-bearing rather than incidental. Serving over
loopback keeps the page in a secure context, without which the clipboard
surface cannot exist at all. Emitting a viewport meta keeps a narrow-viewport
measurement honest, because a document without one is laid out at the engine's
fallback width no matter what viewport was requested.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .ui_home import home_manifest, render_home
from .ui_record_view import record_manifest, render_record_view
from .ui_task_detail import render_task_detail, task_detail_manifest


DOCUMENT = (
    "<!DOCTYPE html>\n"
    '<html lang="zh-CN"><head><meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    "<title>{title}</title></head>\n"
    "<body>{body}</body></html>\n"
)

#: Route -> (title, manifest factory, renderer). The host exposes exactly the
#: three declared views; an unlisted path is not a view and is refused.
ROUTES: Dict[str, Tuple[str, Callable[[], Dict[str, Any]], Callable[..., str]]] = {
    "/home": ("工作台首页", home_manifest, render_home),
    "/task-detail": ("任务详情", task_detail_manifest, render_task_detail),
    "/record-view": ("记录视图", record_manifest, render_record_view),
}


def render_document(route: str, view: Mapping[str, Any]) -> str:
    """Wrap one rendered view in a complete document."""
    title, manifest_of, render = ROUTES[route]
    return DOCUMENT.format(title=title, body=render(view, manifest=manifest_of()))


class WorkbenchHost:
    """A running host. Obtain one through :func:`serve_workbench`."""

    def __init__(self, server: HTTPServer, thread: threading.Thread) -> None:
        self._server = server
        self._thread = thread
        host, port = server.server_address[0], server.server_address[1]
        self.base_url = "http://{0}:{1}".format(host, port)

    def close(self) -> None:
        """Stop serving and release the socket. Safe to call twice."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def serve_workbench(
    view_source: Optional[Callable[[str], Mapping[str, Any]]] = None,
) -> WorkbenchHost:
    """Start a read-only host on an ephemeral loopback port.

    ``view_source`` supplies the redacted presentation model for a route. The
    host never reads owner storage itself; until the control-plane facade
    lands, callers pass their own already-redacted model.
    """
    resolve_view = view_source or (lambda route: {})

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            route = self.path.split("?", 1)[0]
            if route not in ROUTES:
                self.send_error(404, "unknown view")
                return
            body = render_document(route, resolve_view(route)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            """Keep the test output clean; the host is not an evidence source."""

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return WorkbenchHost(server, thread)
