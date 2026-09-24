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
import json
import threading
from urllib.parse import parse_qsl, urlencode
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .ui_build import ROOT_SOURCES, build_receipt
from .ui_home import home_manifest, render_home
from .ui_record_view import record_manifest, render_record_view
from .ui_review import PANEL_ACTIONS, ReviewMode
from .ui_script import review_script
from .ui_style import stylesheet
from .ui_matrix import REQUIRED_VIEWPORTS
from .ui_token import build_token, parse_deep_link
from .ui_task_detail import render_task_detail, task_detail_manifest
from .ui_live import live_facts_payload, live_script
from .ui_run import (
    COMPOSER_SCRIPT_ROUTE,
    COMPOSER_SCRIPT_TAG,
    RUN_API_ROUTE,
    RUN_SCRIPT_ROUTE,
    RUN_SCRIPT_TAG,
    composer_script,
    run_trigger_script,
)
from .ui_approval import (
    APPROVAL_API_ROUTE,
    APPROVAL_SCRIPT_ROUTE,
    APPROVAL_SCRIPT_TAG,
    EFFECT_API_ROUTE,
    approval_script,
)

#: Where the style layer is served. Styling is a separate resource rather
#: than inline markup, so a selector can never be written against the
#: reference attributes the renderers emit.
STYLESHEET_ROUTE = "/static/workbench.css"

#: Where the review behaviour layer is served. It is linked only in review
#: mode, so a normal document carries no script at all rather than a script
#: that decides to do nothing.
REVIEW_SCRIPT_ROUTE = "/static/review.js"

#: F7/1-2-3 — the home live-values poller. Served for /home only (see the
#: module docstring in ui_live for why this is a scoped exception to the
#: "normal documents carry no script" convention).
LIVE_FACTS_ROUTE = "/api/home-facts"
LIVE_SCRIPT_ROUTE = "/static/live.js"
LIVE_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(LIVE_SCRIPT_ROUTE)


DOCUMENT = (
    "<!DOCTYPE html>\n"
    '<html lang="zh-CN"><head><meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    '<link rel="stylesheet" href="{stylesheet}">\n'
    "<title>{title}</title></head>\n"
    "<body>{body}{script}</body></html>\n"
)

REVIEW_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(REVIEW_SCRIPT_ROUTE)

#: Route -> (title, manifest factory, renderer). The host exposes exactly the
#: three declared views; an unlisted path is not a view and is refused.
#: Shown when a link no longer locates anything. It states the outcome and
#: nothing about the input, and it does not redirect: landing silently on the
#: unparameterised page would leave two reviewers believing they were looking
#: at the same element.
LINK_NOTICE = '<p data-ui-link-outcome="{outcome}">链接已失效：{outcome}</p>'

#: Shown when a link locates its target while review mode is off. The link
#: must never switch review mode on by itself -- so instead of an overlay the
#: page says how the reviewer enters the mode explicitly. The hint names no
#: flag: how review mode is enabled belongs to the entry point, and the page
#: must not pretend to know which one served it.
REVIEW_HINT = (
    '<p data-ui-review-hint="off">评审模式未开启：链接已完成定位，'
    "如需标注请显式开启评审模式</p>"
)

#: Route -> (list-item reference, view-model key) the panel mounts entries
#: from. A route absent here gets an empty panel rather than a crash or a
#: wrong-view token.
_PANEL_ENTRY_SOURCES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "/home": (("home.record-list.item", "records"),),
    "/record-view": (("record-view.event-list.item", "events"),),
}

#: The review layer. It names the manifest identity it was rendered against,
#: so a reviewer can tell whether their reference names the same build, and it
#: carries role="presentation" because the highlight conveys no content of its
#: own -- the panel that does is a separate, focusable region.
#: The review panel. Unlike the highlight layer this is a labelled region with
#: content, so it carries role="region" rather than presentation and it accepts
#: input. It states the manifest identity it was rendered against, so two
#: reviewers can tell whether a reference means the same thing to both.
#: ``aria-live`` on the status line, because the outcome of a copy is the one
#: thing here a reviewer may never look at: they pressed a button and turned to
#: paste. An unannounced failure reads as success.
PANEL = (
    '<section data-ui-panel="review" role="region" aria-label="评审面板" '
    "data-ui-panel-names='{names}' data-ui-panel-tokens='{token_map}'>"
    '<p data-ui-panel-identity="{identity}">{identity}</p>'
    '<p data-ui-panel-query>本地查询：zworkbench ui-ref --store '
    "&lt;manifest 目录&gt; resolve &lt;ref&gt; --ui-map {ui_map_full} "
    '--build {build_full}</p>'
    '<ul data-ui-panel-entries>{entries}</ul>'
    '<div data-ui-panel-actions>{controls}</div>'
    '<p data-ui-panel-status="idle" role="status" aria-live="polite"></p>'
    "</section>"
)

#: The control that opens review mode. It is also the focus fallback when the
#: element a reviewer came from is gone by the time the panel closes, so it is
#: rendered as a real focusable button rather than a label.
REVIEW_ENTRY = (
    '<button type="button" data-ui-review-entry="open" '
    'aria-pressed="true">评审模式</button>'
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

_BUSINESS_QUERY_KEYS = {
    "/record-view": frozenset({"run_id", "filter"}),
    "/task-detail": frozenset({"run_id"}),
}


def _locator_query(route: str, query: str) -> str:
    """Remove only the route's read-only selection fields before deep-linking."""

    business_keys = _BUSINESS_QUERY_KEYS.get(route, frozenset())
    if not query or not business_keys:
        return query
    pairs = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key not in business_keys
    ]
    return urlencode(pairs)


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
    parsed = parse_deep_link("/?" + query)
    if parsed["outcome"] != "valid":
        return {"outcome": parsed["outcome"]}
    if parsed["ui_map"] != manifest["ui_map"]:
        return {"outcome": "ui-map-mismatch"}
    entry = next(
        (item for item in manifest["refs"] if item["ref"] == parsed["ui_ref"]), None
    )
    if entry is None:
        return {"outcome": "unknown-reference"}
    if entry.get("retired"):
        # A retired reference is not "reach that state and it appears": no
        # state will ever render it again. The link needs the lifecycle
        # outcome, and the replacement when one was declared, so old feedback
        # stays interpretable (PRD story 9) instead of reading as a stale page.
        outcome = {"outcome": "retired", "ref": parsed["ui_ref"]}
        if entry.get("replaced_by"):
            outcome["replaced_by"] = entry["replaced_by"]
        return outcome
    if rendered is not None and _marker(parsed["ui_ref"]) not in rendered:
        return {"outcome": "unavailable", "ref": parsed["ui_ref"]}
    return {"outcome": "located", "ref": parsed["ui_ref"]}


def _panel_state(route: str, view: Mapping[str, Any]) -> str:
    """The state a token claims the reviewer saw, from the served view model.

    The value is validated against the token whitelist rather than trusted:
    a view model carrying a status the token contract does not know yields
    ``unknown``, because minting a state the contract rejects would be worse
    than honestly claiming nothing.
    """
    from .ui_token import STATES

    candidate = {
        "/home": (view.get("run_facts") or {}).get("status"),
        "/task-detail": (view.get("admission") or {}).get("status"),
        "/record-view": view.get("mode"),
    }.get(route)
    return str(candidate) if candidate in STATES else "unknown"


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


def render_panel(
    manifest: Mapping[str, Any], view: Mapping[str, Any], route: str = "/home"
) -> str:
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
    # Mount only references this route's manifest declares. Hard-coding one
    # view's reference here crashed any other route whose view model carried
    # the same key (mount raises on undeclared refs), and the failure surfaced
    # as a dropped connection, not an error a reviewer could read.
    for ref, items_key in _PANEL_ENTRY_SOURCES.get(route, ()):
        for index, item in enumerate(view.get(items_key) or ()):
            mode.mount(ref, entity_key="{0}-{1}".format(ref, index))
    plan = mode.keyboard_plan()

    # One token per viewport, both minted here by ui_token. The server cannot
    # know which viewport the engine will lay out, and minting in the page
    # would move the field whitelist out of the module whose tests enforce it.
    #
    # No instance handle is carried. A handle belongs to the ReviewMode session
    # that minted it, and that session ends with the response -- a served
    # handle would resolve as "expired" for every reviewer who used it, which
    # is worse than a token that honestly identifies the structural unit only.
    # It also kept the document from being reproducible across requests, and
    # that reproducibility is what tests/test_ui_review_lifecycle.py uses to
    # detect state accumulating in the host.
    state = _panel_state(route, view)

    entries = "".join(
        '<li data-ui-panel-entry="{ref}" data-ui-panel-semantic="{semantic}" '
        '{tokens}>{semantic}（{ref}）</li>'.format(
            ref=html.escape(entry["ref"], quote=True),
            semantic=html.escape(entry["semantic_zh"]),
            tokens=" ".join(
                'data-ui-panel-token-{0}="{1}"'.format(
                    viewport,
                    html.escape(
                        build_token(
                            dict(manifest),
                            entry["ref"],
                            viewport=viewport,
                            state=state,
                        ),
                        quote=True,
                    ),
                )
                for viewport in REQUIRED_VIEWPORTS
            ),
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
    # The whole manifest's ref -> Chinese semantic name map, so the page layer
    # can name any element a reviewer hovers -- not just the entries this
    # route mounts into the panel. Names stay server-rendered state-machine
    # data; the script displays them and never invents one.
    names = json.dumps(
        {
            entry["ref"]: entry["semantic_zh"]
            for entry in manifest["refs"]
            if not entry.get("retired")
        },
        ensure_ascii=False,
    )
    # One token per declared reference per viewport, not just for the entries
    # this route mounts: Tab traversal lets a keyboard reviewer focus -- and
    # copy -- any declared element, so every reference needs its token in the
    # page. Minting stays server-side; the script only ever picks one up.
    token_map = json.dumps(
        {
            entry["ref"]: {
                viewport: build_token(
                    dict(manifest), entry["ref"], viewport=viewport, state=state
                )
                for viewport in REQUIRED_VIEWPORTS
            }
            for entry in manifest["refs"]
            if not entry.get("retired")
        },
        ensure_ascii=False,
    )
    return PANEL.format(
        names=html.escape(names, quote=True),
        token_map=html.escape(token_map, quote=True),
        identity="ui_map:{0} build:{1}".format(
            html.escape(manifest["ui_map"][:12], quote=True),
            html.escape(manifest["build"][:12], quote=True),
        ),
        # The query hint carries the full digests: a truncated identity names
        # nothing a local lookup could resolve.
        ui_map_full=html.escape(manifest["ui_map"], quote=True),
        build_full=html.escape(manifest["build"], quote=True),
        entries=entries,
        controls=controls,
    )


def _expands(render: Callable[..., str]) -> bool:
    """Whether this view's renderer accepts an expansion request.

    Asked of the renderer rather than kept in a table here: a view that gains or
    loses a disclosure would otherwise need two places updated, and the table
    would be the one that silently went stale.
    """
    import inspect

    return "expand" in inspect.signature(render).parameters


#: The one build identity the host serves (ADR 0006): the whole-tree receipt,
#: computed once from the same function and sources the build hook uses. A
#: served token's build then matches what ``build_ui_artifacts`` stores, so a
#: reviewer’s copy resolves locally instead of answering manifest-missing.
#: Computed lazily so importing the module never touches the tree; an
#: unreadable source fails at serve time, not at token-parse time.
_SERVED_BUILD: Optional[str] = None


def _served_build() -> str:
    global _SERVED_BUILD
    if _SERVED_BUILD is None:
        root = Path(__file__).resolve().parents[2]
        _SERVED_BUILD = build_receipt(root, ROOT_SOURCES)["build"]
    return _SERVED_BUILD


def render_document(
    route: str,
    view: Mapping[str, Any],
    query: str = "",
    review: bool = False,
    build: Optional[str] = None,
    run_capable: bool = False,
    approval_capable: bool = False,
) -> str:
    """Wrap one rendered view in a complete document.

    A deep link only annotates: the located element gains a marker attribute
    and nothing else moves. The view model is the facade's to decide, so
    following a link cannot load a run, restore state or start a review.
    """
    title, manifest_of, render = ROUTES[route]
    manifest = manifest_of(build=build or _served_build())
    body = render(view, manifest=manifest)

    # Resolved against the rendered body, then rendered again if the target sits
    # behind a disclosure: the second pass serves that disclosure open, so the
    # link reveals its target without a click. Only the named reference is
    # expanded -- opening every disclosure would make "located" meaningless.
    outcome = locate(manifest, _locator_query(route, query), body)
    if outcome is not None and outcome["outcome"] == "located":
        if _expands(render):
            body = render(view, manifest=manifest, expand=(outcome["ref"],))
        body = body.replace(
            _marker(outcome["ref"]),
            '{0} data-ui-located="{1}"'.format(_marker(outcome["ref"]), outcome["ref"]),
            1,
        )
    elif outcome is not None:
        notice = LINK_NOTICE.format(outcome=html.escape(outcome["outcome"]))
        if outcome.get("replaced_by"):
            # Story 9 is only honoured if the reviewer can see what replaced
            # the retired reference; "retired" alone leaves old feedback
            # uninterpretable. The value comes from the manifest, not from
            # the link, and is escaped like everything else on the page.
            replacement = html.escape(outcome["replaced_by"], quote=True)
            notice += (
                '<p data-ui-link-replacement="{0}">替代引用：{0}</p>'.format(
                    replacement
                )
            )
        body = notice + body
    if review:
        body = body + render_overlay(manifest) + REVIEW_ENTRY + render_panel(
            manifest, view, route
        )
    elif outcome is not None and outcome["outcome"] == "located":
        # A deep link located its target on a host without the review layer.
        # The location mark is harmless annotation; silently presenting it as
        # if review were on would be the quiet enablement the PRD forbids, so
        # the page states the mode explicitly instead. A failed link gets no
        # hint: its notice already says what happened.
        body = REVIEW_HINT + body
    # F7/1-2-3 — the home live poller is a scoped exception to the "normal
    # documents carry no script" convention: it is progressive enhancement for
    # /home only. F10/1-2-4 adds a second scoped script for /home, the run
    # trigger, and only when the host was started with a command facade. F6/1-2-1
    # adds a third scoped script, the composer trigger, under the same
    # command-facade condition. F12/1-2-2 adds a fourth scoped script, the
    # approval-console trigger, under the same approval-facade condition. Other
    # routes stay script-free in normal mode.
    live_tag = LIVE_SCRIPT_TAG if route == "/home" else ""
    run_tag = RUN_SCRIPT_TAG if (route == "/home" and run_capable) else ""
    composer_tag = COMPOSER_SCRIPT_TAG if (route == "/home" and run_capable) else ""
    approval_tag = APPROVAL_SCRIPT_TAG if (route == "/home" and approval_capable) else ""
    return DOCUMENT.format(
        title=title,
        stylesheet=STYLESHEET_ROUTE,
        body=body,
        script=live_tag + run_tag + composer_tag + approval_tag + (REVIEW_SCRIPT_TAG if review else ""),
    )


class WorkbenchHost:
    """A running host. Obtain one through :func:`serve_workbench`."""

    def __init__(self, server: HTTPServer, thread: threading.Thread) -> None:
        # HTTPServer is only the annotation; serving is threaded, see below.
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
    command_source: Optional[Callable[..., Mapping[str, Any]]] = None,
    approval_source: Optional[Callable[..., Mapping[str, Any]]] = None,
) -> WorkbenchHost:
    """Start a host, by default on an ephemeral loopback port.

    ``view_source`` supplies the redacted presentation model for a route. The
    host never reads owner storage itself; until the control-plane facade
    lands, callers pass their own already-redacted model.

    ``bind`` exists so a caller can request a specific port. Refusing a
    non-loopback address is the entry point's job, not this function's.

    ``review`` is a start-up choice on purpose. A request cannot turn the
    review layer on, so a deep link is structurally incapable of enabling it
    rather than merely lacking the parameter.

    ``command_source`` is the *optional* F10/1-2-4 write seam. When supplied
    (by the control plane, never by the read-only CLI ``ui-host``), the host
    exposes a POST ``/api/runs`` endpoint that creates + starts a run through
    this narrow facade. When ``None`` the endpoint answers 404, so the write
    surface can never appear without an explicit, named wiring decision.

    ``approval_source`` is the *optional* F12/1-2-2 write seam. When supplied,
    the host exposes POST ``/api/approvals`` (approve/deny) and POST
    ``/api/effects`` (record receipt) through a narrow facade that exposes only
    the human-decidable verbs of the Approval/Effect seam. When ``None`` both
    endpoints answer 404, so the approval-execution write surface can never
    appear without an explicit, named wiring decision.
    """
    resolve_view = view_source or (lambda route: {})
    cmd = command_source
    approval_src = approval_source

    # ADR 0006: the build identity is computed once, here, at startup. A source
    # that cannot be read fails loudly at this line -- before the socket opens
    # and before any request can be answered with an identity nothing aligns
    # with -- rather than surfacing as a dropped connection mid-request. This
    # deliberately bypasses the module-level cache: a long-lived process that
    # filled the cache earlier must not skip the startup read and serve an
    # identity the tree can no longer back.
    served_build = build_receipt(Path(__file__).resolve().parents[2], ROOT_SOURCES)[
        "build"
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            route, _, query = self.path.partition("?")
            if route == STYLESHEET_ROUTE:
                self._respond(stylesheet().encode("utf-8"), "text/css; charset=utf-8")
                return
            if route == REVIEW_SCRIPT_ROUTE:
                # Served only while review mode is on: in normal mode the
                # behaviour layer does not exist as a resource, so it cannot be
                # fetched and injected into a page that never linked it.
                if not review:
                    self.send_error(404, "unknown view")
                    return
                self._respond(
                    review_script().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if route == LIVE_FACTS_ROUTE:
                # F7/1-2-3 — read-only live facts for /home. Re-projects the
                # same owner-backed view the page renders; no write, no runtime
                # invocation beyond the read-only projection.
                self._respond(self._live_facts_json(), "application/json; charset=utf-8")
                return
            if route == LIVE_SCRIPT_ROUTE:
                # F7/1-2-3 — the poller, served unconditionally: it is
                # progressive enhancement for /home, not a review-mode layer.
                self._respond(
                    live_script().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if route == RUN_SCRIPT_ROUTE:
                # F10/1-2-4 — the run trigger handler. Served unconditionally
                # like the live poller: it is progressive enhancement for /home
                # and does nothing on a host without a run button.
                self._respond(
                    run_trigger_script().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if route == COMPOSER_SCRIPT_ROUTE:
                # F6/1-2-1 — the composer trigger handler. Served unconditionally
                # like the run-rail script: progressive enhancement for /home,
                # and a no-op on a host whose composer form is disabled.
                self._respond(
                    composer_script().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if route == APPROVAL_SCRIPT_ROUTE:
                # F12/1-2-2 — the approval-console trigger handler. Served
                # unconditionally like the run-rail/composer scripts: it is
                # progressive enhancement for /home and does nothing on a host
                # whose approval console is disabled.
                self._respond(
                    approval_script().encode("utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return
            if route not in ROUTES:
                self.send_error(404, "unknown view")
                return
            query_resolver = getattr(resolve_view, "resolve_query", None)
            view = (
                query_resolver(route, query)
                if callable(query_resolver)
                else resolve_view(route)
            )
            # F10/1-2-4 — a host wired with a command facade may let the run
            # button fire. Signal that capability to the renderer by flipping
            # ``can_run`` on /home's run-rail projection; the run script is
            # injected by render_document from the same flag.
            if route == "/home" and cmd is not None:
                view = dict(view)
                rail = dict(view.get("run_rail") or {})
                rail["can_run"] = True
                view["run_rail"] = rail
                # F6/1-2-1 — the command facade also enables the composer send.
                composer = dict(view.get("composer") or {})
                composer["can_send"] = True
                view["composer"] = composer
            if route == "/home" and approval_src is not None:
                # F12/1-2-2 — the approval command facade enables the console's
                # Approve/Deny/Record-receipt controls, independently of the
                # run seam (a control plane may wire approvals without runs).
                console = dict(view.get("approval_console") or {})
                console["can_decide"] = True
                view["approval_console"] = console
            body = render_document(
                route, view, query, review, build=served_build,
                run_capable=(cmd is not None),
                approval_capable=(approval_src is not None),
            ).encode("utf-8")
            self._respond(body, "text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            route, _, _ = self.path.partition("?")
            writable = {
                RUN_API_ROUTE: self._handle_create_run,
                APPROVAL_API_ROUTE: self._handle_approval_decision,
                EFFECT_API_ROUTE: self._handle_effect_receipt,
            }
            if route not in writable:
                self.send_error(404, "unknown view")
                return
            writable[route]()

        def _handle_create_run(self) -> None:
            """F10/1-2-4 — create + start a run through the command facade.

            Reached only when a command facade was wired at startup. A read-only
            host answers 404 here, so the write surface never appears without an
            explicit wiring decision. Input is validated at the boundary; owner
            errors surface as 4xx rather than 500.
            """
            if cmd is None:
                self.send_error(404, "read-only host: no command facade")
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0 or length > 1_000_000:
                self._respond_json({"error": "bad request"}, 400)
                return
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                self._respond_json({"error": "invalid json"}, 400)
                return
            if not isinstance(payload, dict):
                self._respond_json({"error": "invalid payload"}, 400)
                return
            task_type = payload.get("task_type")
            input_value = payload.get("input_value")
            metadata = payload.get("metadata")
            if not isinstance(task_type, str) or not task_type.strip():
                self._respond_json({"error": "task_type required"}, 400)
                return
            if input_value is None:
                self._respond_json({"error": "input_value required"}, 400)
                return
            if metadata is not None and not isinstance(metadata, (dict, Mapping)):
                self._respond_json({"error": "metadata must be an object"}, 400)
                return
            try:
                result = cmd(
                    task_type=task_type,
                    input_value=input_value,
                    metadata=metadata,
                )
            except Exception as exc:  # owner raises CompositionError etc.
                self._respond_json({"error": str(exc)}, 400)
                return
            self._respond_json(result, 201)

        def _read_json_payload(self) -> Any:
            """Read + parse a JSON request body.

            Returns a dict on success, or an int HTTP status (400) to return
            when the body is missing, oversized, or not a JSON object.
            """
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0 or length > 1_000_000:
                return 400
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                return 400
            if not isinstance(payload, dict):
                return 400
            return payload

        def _handle_approval_decision(self) -> None:
            """F12/1-2-2 — approve/deny a pending approval through the facade.

            Reached only when an approval command facade was wired at startup. A
            read-only host answers 404 here, so the write surface never appears
            without an explicit wiring decision. Input is validated at the
            boundary; owner errors surface as 4xx rather than 500.
            """
            if approval_src is None:
                self.send_error(404, "read-only host: no approval facade")
                return
            payload = self._read_json_payload()
            if isinstance(payload, int):
                self._respond_json({"error": "bad request"}, payload)
                return
            action = payload.get("action")
            if action not in ("approve", "deny"):
                self._respond_json({"error": "action must be approve or deny"}, 400)
                return
            approval_id = payload.get("approval_id")
            if not isinstance(approval_id, str) or not approval_id.strip():
                self._respond_json({"error": "approval_id required"}, 400)
                return
            try:
                result = approval_src(
                    action=action,
                    approval_id=approval_id,
                    reason=payload.get("reason"),
                )
            except Exception as exc:  # owner raises ApprovalError/NotFoundError
                self._respond_json({"error": str(exc)}, 400)
                return
            self._respond_json(result, 200)

        def _handle_effect_receipt(self) -> None:
            """F12/1-2-2 — record a claimed effect's receipt through the facade.

            Reached only when an approval command facade was wired. A read-only
            host answers 404 here. The receipt commits the physical effect
            exactly once; owner errors (e.g. effect not claimable) surface as
            4xx rather than 500.
            """
            if approval_src is None:
                self.send_error(404, "read-only host: no approval facade")
                return
            payload = self._read_json_payload()
            if isinstance(payload, int):
                self._respond_json({"error": "bad request"}, payload)
                return
            effect_id = payload.get("effect_id")
            if not isinstance(effect_id, str) or not effect_id.strip():
                self._respond_json({"error": "effect_id required"}, 400)
                return
            external_receipt = payload.get("external_receipt")
            if external_receipt is not None and not isinstance(
                external_receipt, (dict, Mapping)
            ):
                self._respond_json({"error": "external_receipt must be an object"}, 400)
                return
            try:
                result = approval_src(
                    action="complete_effect",
                    effect_id=effect_id,
                    external_receipt=external_receipt,
                )
            except Exception as exc:  # owner raises InvalidTransition etc.
                self._respond_json({"error": str(exc)}, 400)
                return
            self._respond_json(result, 200)

        def _respond(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _respond_json(self, obj: Any, status: int) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _live_facts_json(self) -> bytes:
            """Project /home's live facts through the same view source."""
            resolver = getattr(resolve_view, "resolve_query", None)
            view = resolver("/home", "") if callable(resolver) else resolve_view("/home")
            return json.dumps(
                live_facts_payload(view), ensure_ascii=False
            ).encode("utf-8")

        def log_message(self, *args: Any) -> None:
            """Keep the test output clean; the host is not an evidence source."""

    # Threaded, with daemon threads: a browser preconnects by opening a TCP
    # connection and saying nothing on it until a navigation needs it. A
    # single-threaded server would block in recv on that idle socket and queue
    # every real request behind it -- the page loads forever while the host
    # looks healthy. Daemon threads keep close() a port release rather than a
    # wait for idle sockets to time out.
    server = ThreadingHTTPServer(bind, Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return WorkbenchHost(server, thread)
