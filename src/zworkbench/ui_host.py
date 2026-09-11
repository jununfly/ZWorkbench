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

import html
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .ui_home import home_manifest, render_home
from .ui_record_view import record_manifest, render_record_view
from .ui_review import PANEL_ACTIONS, ReviewMode
from .ui_style import stylesheet
from .ui_token import parse_deep_link
from .ui_task_detail import render_task_detail, task_detail_manifest

#: Where the style layer is served. Styling is a separate resource rather
#: than inline markup, so a selector can never be written against the
#: reference attributes the renderers emit.
STYLESHEET_ROUTE = "/static/workbench.css"


DOCUMENT = (
    "<!DOCTYPE html>\n"
    '<html lang="zh-CN"><head><meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    '<link rel="stylesheet" href="{stylesheet}">\n'
    "<title>{title}</title></head>\n"
    "<body>{body}</body></html>\n"
)

#: Route -> (title, manifest factory, renderer). The host exposes exactly the
#: three declared views; an unlisted path is not a view and is refused.
#: Shown when a link no longer locates anything. It states the outcome and
#: nothing about the input, and it does not redirect: landing silently on the
#: unparameterised page would leave two reviewers believing they were looking
#: at the same element.
LINK_NOTICE = '<p data-ui-link-outcome="{outcome}">链接已失效：{outcome}</p>'

#: The review layer. It names the manifest identity it was rendered against,
#: so a reviewer can tell whether their reference names the same build, and it
#: carries role="presentation" because the highlight conveys no content of its
#: own -- the panel that does is a separate, focusable region.
#: The review panel. Unlike the highlight layer this is a labelled region with
#: content, so it carries role="region" rather than presentation and it accepts
#: input. It states the manifest identity it was rendered against, so two
#: reviewers can tell whether a reference means the same thing to both.
PANEL = (
    '<section data-ui-panel="review" role="region" aria-label="评审面板">'
    '<p data-ui-panel-identity="{identity}">{identity}</p>'
    '<ul data-ui-panel-entries>{entries}</ul>'
    '<div data-ui-panel-actions>{controls}</div>'
    "</section>"
)

OVERLAY = (
    '<aside data-ui-overlay="review" role="{role}"'
    ' style="pointer-events:{pointer_events}">'
    '<span data-ui-overlay-identity="ui_map:{ui_map} build:{build}">'
    '评审模式 · 映射 {ui_map} · 构建 {build}</span>'
    "</aside>"
)

ROUTES: Dict[str, Tuple[str, Callable[[], Dict[str, Any]], Callable[..., str]]] = {
    "/home": ("工作台首页", home_manifest, render_home),
    "/task-detail": ("任务详情", task_detail_manifest, render_task_detail),
    "/record-view": ("记录视图", record_manifest, render_record_view),
}


def _marker(ref: str) -> str:
    """The attribute text an element carrying this reference must contain."""
    return 'data-ui-ref="{0}"'.format(ref)


def locate(
    manifest: Mapping[str, Any], query: str, rendered: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Interpret a review deep link against the view that was actually rendered.

    ``None`` means the request carried no link. Otherwise the outcome names
    what went wrong, because each way a link dies needs a different fix:

    * ``ui-map-mismatch`` -- the link came from another build; regenerate it.
    * ``unknown-reference`` -- it names something never declared; the link is
      wrong, or the declaration was removed.
    * ``unavailable`` -- the unit is declared but is not on this page, because
      the state that renders it does not hold (an empty list has no rows).
      The reviewer needs to reach that state, not fix the link.

    The last outcome is why ``rendered`` exists. A manifest says a unit exists
    somewhere in the view; only the document says it exists *here*. Deciding
    from the manifest alone reported success for a reference that no element
    carried, and the reviewer then saw an unmarked page with no explanation.

    ``rendered`` is optional so that a caller with no document can still check a
    link's structural validity, but such a call can never answer ``unavailable``.

    A rejection never echoes the input. A locator that reflects what it was
    given is how one turns into an injection point.
    """
    if not query:
        return None
    parsed = parse_deep_link("?" + query)
    if parsed["outcome"] != "valid":
        return {"outcome": parsed["outcome"]}
    if parsed["ui_map"] != manifest["ui_map"]:
        return {"outcome": "ui-map-mismatch"}
    if not any(entry["ref"] == parsed["ui_ref"] for entry in manifest["refs"]):
        return {"outcome": "unknown-reference"}
    if rendered is not None and _marker(parsed["ui_ref"]) not in rendered:
        return {"outcome": "unavailable", "ref": parsed["ui_ref"]}
    return {"outcome": "located", "ref": parsed["ui_ref"]}


def render_overlay(manifest: Mapping[str, Any]) -> str:
    """Render the review overlay as a sibling subtree of the business markup.

    Two properties make the layer honest rather than decorative. It is a
    sibling, so the business markup is byte-for-byte what normal mode serves --
    which is what lets a mode comparison subtract the overlay and find nothing
    else changed. And it declares ``pointer-events: none``, so it can cover the
    content without intercepting a click.

    The declaration is a contract, not evidence: only an engine can confirm it
    is honoured, which is why tests/test_ui_overlay.py hit-tests a real
    document.
    """
    entry = ReviewMode(dict(manifest)).overlay_descriptor()
    return OVERLAY.format(
        pointer_events=html.escape(entry["pointer-events"], quote=True),
        role=html.escape(entry["role"], quote=True),
        build=html.escape(manifest["build"][:12], quote=True),
        ui_map=html.escape(manifest["ui_map"][:12], quote=True),
    )


def render_panel(manifest: Mapping[str, Any], view: Mapping[str, Any]) -> str:
    """Render the review panel from the state machine's own decisions.

    The entries and the keyboard plan come from :class:`ReviewMode`, not from a
    second list maintained here: a panel that invented its own actions could
    drift from the machine that implements them while both stayed green.

    Every action is a real button, because an action reachable only by pointer
    is not reachable. Whether the resulting tab order is the one a reviewer
    expects is a host unknown (1-6-1) and is not claimed here.
    """
    mode = ReviewMode(dict(manifest))
    mode.enable()
    for index, record in enumerate(view.get("records") or ()):
        mode.mount("home.record-list.item", entity_key="row-{0}".format(index))
    plan = mode.keyboard_plan()

    entries = "".join(
        '<li data-ui-panel-entry="{ref}">{semantic}（{ref}）</li>'.format(
            ref=html.escape(entry["ref"], quote=True),
            semantic=html.escape(entry["semantic_zh"]),
        )
        for entry in mode.panel_entries()
    )
    controls = "".join(
        '<button type="button" data-ui-panel-action="{action}">'
        "{action} · {keys}</button>".format(
            action=html.escape(action, quote=True),
            keys=html.escape(plan[action]),
        )
        for action in PANEL_ACTIONS
    )
    mode.disable()
    return PANEL.format(
        identity="ui_map:{0} build:{1}".format(
            html.escape(manifest["ui_map"][:12], quote=True),
            html.escape(manifest["build"][:12], quote=True),
        ),
        entries=entries,
        controls=controls,
    )


def render_document(
    route: str, view: Mapping[str, Any], query: str = "", review: bool = False
) -> str:
    """Wrap one rendered view in a complete document.

    A deep link only annotates: the located element gains a marker attribute
    and nothing else moves. The view model is the facade's to decide, so
    following a link cannot load a run, restore state or start a review.
    """
    title, manifest_of, render = ROUTES[route]
    manifest = manifest_of()
    body = render(view, manifest=manifest)

    # Resolved against the rendered body rather than the manifest: see locate().
    outcome = locate(manifest, query, body)
    if outcome is not None and outcome["outcome"] == "located":
        body = body.replace(
            _marker(outcome["ref"]),
            '{0} data-ui-located="{1}"'.format(_marker(outcome["ref"]), outcome["ref"]),
            1,
        )
    elif outcome is not None:
        body = LINK_NOTICE.format(outcome=html.escape(outcome["outcome"])) + body
    if review:
        body = body + render_overlay(manifest) + render_panel(manifest, view)
    return DOCUMENT.format(title=title, stylesheet=STYLESHEET_ROUTE, body=body)


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
    bind: Tuple[str, int] = ("127.0.0.1", 0),
    review: bool = False,
) -> WorkbenchHost:
    """Start a read-only host, by default on an ephemeral loopback port.

    ``view_source`` supplies the redacted presentation model for a route. The
    host never reads owner storage itself; until the control-plane facade
    lands, callers pass their own already-redacted model.

    ``bind`` exists so a caller can request a specific port. Refusing a
    non-loopback address is the entry point's job, not this function's.

    ``review`` is a start-up choice on purpose. A request cannot turn the
    review layer on, so a deep link is structurally incapable of enabling it
    rather than merely lacking the parameter.
    """
    resolve_view = view_source or (lambda route: {})

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            route, _, query = self.path.partition("?")
            if route == STYLESHEET_ROUTE:
                self._respond(stylesheet().encode("utf-8"), "text/css; charset=utf-8")
                return
            if route not in ROUTES:
                self.send_error(404, "unknown view")
                return
            body = render_document(
                route, resolve_view(route), query, review
            ).encode("utf-8")
            self._respond(body, "text/html; charset=utf-8")

        def _respond(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            """Keep the test output clean; the host is not an evidence source."""

    server = HTTPServer(bind, Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return WorkbenchHost(server, thread)
