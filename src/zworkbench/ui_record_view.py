"""Record-view declarations, used by the coverage matrix only.

This module holds the structural contract for the record-view.  The
renderer is a fixture-level helper; the real rendering belongs to a
future host.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from .ui_declare import attribute_text, module_source_digest


_MODULE = "src/zworkbench/ui_record_view.py"
_RECORD_REFS = (
    ("record-view.root", "记录视图页", "region", None),
    ("record-view.record-picker", "记录选择器", "region", "record-view.root"),
    ("record-view.event-list", "事件列表", "list", "record-view.record-picker"),
    ("record-view.event-list.item", "事件项", "list-item", "record-view.event-list"),
    ("record-view.filter", "筛选", "action", "record-view.record-picker"),
    ("record-view.event-detail", "事件详情", "region", "record-view.record-picker"),
    ("record-view.result", "结果", "detail", "record-view.event-detail"),
    ("record-view.artifact-metadata", "Artifact 元数据", "detail", "record-view.event-detail"),
    ("record-view.replay-metadata", "Replay 元数据", "detail", "record-view.event-detail"),
    ("record-view.mode-boundary", "模式边界说明", "detail", "record-view.record-picker"),
)


def record_registry() -> UiRefRegistry:
    registry = UiRefRegistry()
    digest = module_source_digest(Path(__file__))
    for ref, semantic_zh, kind, parent in _RECORD_REFS:
        registry.declare(
            UiRefDeclaration(
                ref=ref,
                semantic_zh=semantic_zh,
                kind=kind,
                view="record-view",
                source=SourceAnchor(
                    repo_path=_MODULE, symbol="record_registry", content_digest=digest,
                ),
                parent=parent,
            )
        )
    return registry


def record_manifest(*, build: str = None) -> Dict[str, Any]:
    return record_registry().build_manifest(build=build or module_source_digest(Path(__file__)))


#: The units this renderer places behind a native disclosure, collapsed by
#: default. Detail-level metadata is secondary to the event being reviewed, so
#: hiding it keeps the surface readable at 390px.
#:
#: This list is written here rather than imported from :mod:`zworkbench.ui_matrix`
#: on purpose. The matrix is the *expected* classification; if the renderer read
#: it, the two would agree by construction and the test comparing them would
#: prove nothing.
DISCLOSED_REFS = (
    "record-view.result",
    "record-view.artifact-metadata",
    "record-view.replay-metadata",
)


def _render_value(value: Any) -> str:
    """Render redacted view-model values without exposing Python repr syntax."""

    if isinstance(value, Mapping):
        rows = "".join(
            "<div><dt>{0}</dt><dd>{1}</dd></div>".format(
                html.escape(str(key)), _render_value(item)
            )
            for key, item in value.items()
        )
        return "<dl>{0}</dl>".format(rows)
    if isinstance(value, (list, tuple)):
        items = "".join("<li>{0}</li>".format(_render_value(item)) for item in value)
        return "<ul>{0}</ul>".format(items)
    return html.escape(str(value))


def render_record_view(
    view: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] = None,
    expand: Sequence[str] = (),
) -> str:
    """Fixture-level renderer for coverage assertions.

    ``expand`` names references whose enclosing disclosure must be served open.
    The host passes the target of a deep link, so following a link reveals the
    element without a click and without scripting: ``<details>`` is the engine's
    own disclosure, and opening it executes nothing.

    Expansion is scoped to the disclosure that holds the named reference. A
    renderer that opened every disclosure would satisfy "the unit is visible"
    while locating nothing.
    """
    m = manifest or record_manifest()
    requested = set(expand)
    items: Sequence[Any] = view.get("events") or ()
    event_html = ""
    if items:
        event_html = "".join(
            "<li {0}>{1}</li>".format(
                attribute_text(m, "record-view.event-list.item"),
                _render_value(
                    {
                        "type": item.get("type", item.get("title", "unknown")),
                        **(
                            {
                                "event_id": item["event_id"],
                                "created_at": item["created_at"],
                                "source": item["source"],
                            }
                            if "event_id" in item
                            else {}
                        ),
                    }
                ),
            )
            for item in items
        )
    def disclosure(ref, label, value):
        """One read-only disclosure holding one detail-level unit."""
        return (
            "<details{open}><summary>{label}</summary>"
            "<section {attrs}>{value}</section></details>"
        ).format(
            open=" open" if ref in requested else "",
            label=html.escape(label),
            attrs=attribute_text(m, ref),
            value=_render_value(value),
        )

    disclosures = (
        disclosure("record-view.result", "结果", view.get("result", "unknown"))
        + disclosure(
            "record-view.artifact-metadata",
            "Artifact 元数据",
            view.get("artifact_metadata", "unknown"),
        )
        + disclosure(
            "record-view.replay-metadata",
            "Replay 元数据",
            view.get("replay_metadata", "unknown"),
        )
    )

    selected_run = html.escape(str(view.get("picker", "unknown")), quote=True)
    options = "".join(
        '<option value="{run_id}"{selected}>{title} · {status}</option>'.format(
            run_id=html.escape(str(item.get("run_id", "unknown")), quote=True),
            selected=(
                " selected"
                if str(item.get("run_id")) == str(view.get("picker"))
                else ""
            ),
            title=html.escape(str(item.get("title", item.get("run_id", "unknown")))),
            status=html.escape(str(item.get("status", "unknown"))),
        )
        for item in (view.get("run_options") or ())
        if isinstance(item, Mapping)
    )
    picker_content = (
        '<form method="get" action="/record-view" class="record-picker-form">'
        '<label for="record-run-id">记录</label>'
        '<select id="record-run-id" name="run_id">{options}</select>'
        '<button type="submit">打开记录</button></form>'
        .format(options=options)
        if options
        else _render_value(view.get("picker", "unknown"))
    )
    filter_value = view.get("filter")
    filter_query = (
        filter_value.get("query", "")
        if isinstance(filter_value, Mapping)
        else filter_value
    )
    filter_content = (
        '<form method="get" action="/record-view" class="record-filter-form">'
        '<input type="hidden" name="run_id" value="{run_id}">'
        '<label for="record-event-filter">事件筛选</label>'
        '<input id="record-event-filter" name="filter" value="{query}">'
        '<button {filter} type="submit">筛选</button></form>'
    ).format(
        run_id=selected_run,
        query=html.escape(str(filter_query if filter_query != "unknown" else ""), quote=True),
        filter=attribute_text(m, "record-view.filter"),
    )

    return (
        "<main {root}>"
        '<nav class="view-nav" aria-label="工作台视图">'
        '<a href="/home" tabindex="-1">工作台</a>'
        '<a href="/task-detail" tabindex="-1">任务详情</a>'
        '<a href="/record-view" tabindex="-1" aria-current="page">记录视图</a></nav>'
        "<section {picker}>{picker_content}</section>"
        "<ul {list}>{events}</ul>"
        "{filter_content}"
        "<section {detail}>{detail_text}</section>"
        "{disclosures}"
        "<section {mode}>{mode_text}</section>"
        "</main>"
    ).format(
        disclosures=disclosures,
        root=attribute_text(m, "record-view.root"),
        picker=attribute_text(m, "record-view.record-picker"),
        picker_content=picker_content,
        list=attribute_text(m, "record-view.event-list"),
        events=event_html,
        filter_content=filter_content,
        detail=attribute_text(m, "record-view.event-detail"),
        detail_text=html.escape(str(view.get("detail", "unknown"))),
        mode=attribute_text(m, "record-view.mode-boundary"),
        mode_text=html.escape(
            str(view.get("mode", ""))
            + "；live replay 默认不可用，需显式授权和独立安全策略"
        ),
    )
