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
                html.escape(str(item.get("title", "unknown"))),
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
            value=html.escape(str(value)),
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

    return (
        "<main {root}>"
        "<section {picker}>{picker_text}</section>"
        "<ul {list}>{events}</ul>"
        "<button {filter}>筛选</button>"
        "<section {detail}>{detail_text}</section>"
        "{disclosures}"
        "<section {mode}>{mode_text}</section>"
        "</main>"
    ).format(
        disclosures=disclosures,
        root=attribute_text(m, "record-view.root"),
        picker=attribute_text(m, "record-view.record-picker"),
        picker_text=html.escape(str(view.get("picker", "unknown"))),
        list=attribute_text(m, "record-view.event-list"),
        events=event_html,
        filter=attribute_text(m, "record-view.filter"),
        detail=attribute_text(m, "record-view.event-detail"),
        detail_text=html.escape(str(view.get("detail", "unknown"))),
        mode=attribute_text(m, "record-view.mode-boundary"),
        mode_text=html.escape(str(view.get("mode", ""))),
    )
