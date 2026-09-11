"""Record-view declarations, used by the coverage matrix only.

This module holds the structural contract for the record-view.  The
renderer is a fixture-level helper; the real rendering belongs to a
future host.
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from .ui_runtime import render_attributes


_MODULE = "src/zworkbench/ui_record_view.py"
_RECORD_REFS = (
    ("record-view.record-picker", "记录选择器", "region", None),
    ("record-view.event-list", "事件列表", "list", "record-view.record-picker"),
    ("record-view.event-list.item", "事件项", "list-item", "record-view.event-list"),
    ("record-view.filter", "筛选", "action", "record-view.record-picker"),
    ("record-view.event-detail", "事件详情", "region", "record-view.record-picker"),
    ("record-view.result", "结果", "detail", "record-view.event-detail"),
    ("record-view.artifact-metadata", "Artifact 元数据", "detail", "record-view.event-detail"),
    ("record-view.replay-metadata", "Replay 元数据", "detail", "record-view.event-detail"),
    ("record-view.mode-boundary", "模式边界说明", "detail", "record-view.record-picker"),
)


def _module_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def record_registry() -> UiRefRegistry:
    registry = UiRefRegistry()
    digest = _module_digest()
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
    return record_registry().build_manifest(build=build or _module_digest())


def _attr(manifest: Mapping[str, Any], ref: str) -> str:
    rendered = render_attributes(manifest, ref)
    return " ".join(
        '{0}="{1}"'.format(name, html.escape(value, quote=True))
        for name, value in sorted(rendered.items())
    )


def render_record_view(view: Mapping[str, Any], *, manifest: Mapping[str, Any] = None) -> str:
    """Fixture-level renderer for coverage assertions."""
    m = manifest or record_manifest()
    items: Sequence[Any] = view.get("events") or ()
    event_html = ""
    if items:
        event_html = "".join(
            "<li {0}>{1}</li>".format(
                _attr(m, "record-view.event-list.item"),
                html.escape(str(item.get("title", "unknown"))),
            )
            for item in items
        )
    return (
        "<main {root}>"
        "<section {picker}>{picker_text}</section>"
        "<ul {list}>{events}</ul>"
        "<button {filter}>筛选</button>"
        "<section {detail}>{detail_text}</section>"
        "<section {mode}>{mode_text}</section>"
        "</main>"
    ).format(
        root=_attr(m, "record-view.record-picker"),
        picker=_attr(m, "record-view.record-picker"),
        picker_text=html.escape(str(view.get("picker", "unknown"))),
        list=_attr(m, "record-view.event-list"),
        events=event_html,
        filter=_attr(m, "record-view.filter"),
        detail=_attr(m, "record-view.event-detail"),
        detail_text=html.escape(str(view.get("detail", "unknown"))),
        mode=_attr(m, "record-view.mode-boundary"),
        mode_text=html.escape(str(view.get("mode", ""))),
    )
