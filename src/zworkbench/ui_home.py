"""The home-surface vertical slice: one static region, one dynamic list and one
business button, declared once and rendered from a redacted view model.

The view layer receives an already-redacted presentation model, built by
:mod:`zworkbench.ui_view_model`.  It never reads the composition owner, never
infers a run status and never executes a business action: the preflight button
is rendered, not invoked.
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from .ui_runtime import render_attributes


_MODULE = "src/zworkbench/ui_home.py"

HOME_REFS = (
    ("home.root", "工作台首页", "region", None),
    ("home.workspace-context", "工作区与模式上下文", "region", "home.root"),
    ("home.run-facts", "运行事实", "region", "home.root"),
    ("home.record-list", "工作记录列表", "list", "home.root"),
    ("home.record-list.item", "工作记录项", "list-item", "home.record-list"),
    ("home.current-intent", "当前意图与已记录文本", "region", "home.root"),
    ("home.plan-next-step", "计划与下一步", "region", "home.root"),
    ("home.artifacts", "产物区", "region", "home.root"),
    ("home.evidence", "证据区", "region", "home.root"),
    ("home.preflight-run.action", "预检并运行", "action", "home.root"),
    ("home.preflight-result", "预检结果", "detail", "home.preflight-run.action"),
)


def _module_digest() -> str:
    """Digest this module's own source, so the manifest points at real code."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def home_registry() -> UiRefRegistry:
    """Declare every semantic unit the home slice renders."""
    registry = UiRefRegistry()
    digest = _module_digest()
    for ref, semantic_zh, kind, parent in HOME_REFS:
        registry.declare(
            UiRefDeclaration(
                ref=ref,
                semantic_zh=semantic_zh,
                kind=kind,
                view="home",
                source=SourceAnchor(
                    repo_path=_MODULE,
                    symbol="render_home",
                    content_digest=digest,
                ),
                parent=parent,
            )
        )
    return registry


def home_manifest(*, build: str = None) -> Dict[str, Any]:
    """Generate the manifest for the home slice."""
    return home_registry().build_manifest(build=build or _module_digest())


def _attributes(manifest: Mapping[str, Any], ref: str) -> str:
    rendered = render_attributes(manifest, ref)
    return " ".join(
        '{0}="{1}"'.format(name, html.escape(value, quote=True))
        for name, value in sorted(rendered.items())
    )


def render_home(view: Mapping[str, Any], *, manifest: Mapping[str, Any] = None) -> str:
    """Render the home slice from a redacted view model."""
    resolved = manifest or home_manifest()
    records: Sequence[Mapping[str, Any]] = view.get("records") or ()

    if records:
        items = "".join(
            "<li {0}>{1}</li>".format(
                _attributes(resolved, "home.record-list.item"),
                html.escape(str(record.get("title", "unknown"))),
            )
            for record in records
        )
    else:
        items = ""

    def section(ref, value):
        return "<section {0}>{1}</section>".format(
            _attributes(resolved, ref), html.escape(str(value))
        )

    return (
        "<main {root}>"
        "{workspace}"
        "{facts}"
        "<ul {list}>{items}</ul>"
        "{intent}"
        "{plan}"
        "{artifacts}"
        "{evidence}"
        "<button {action} type=\"button\">预检并运行</button>"
        "{preflight_result}"
        "</main>"
    ).format(
        root=_attributes(resolved, "home.root"),
        workspace=section("home.workspace-context", view.get("workspace", "unknown")),
        facts=section(
            "home.run-facts", view.get("run_facts", {}).get("status", "unknown")
        ),
        list=_attributes(resolved, "home.record-list"),
        items=items,
        intent=section("home.current-intent", view.get("intent", "unknown")),
        plan=section("home.plan-next-step", view.get("plan", "unknown")),
        artifacts=section("home.artifacts", view.get("artifacts", "unknown")),
        evidence=section("home.evidence", view.get("evidence", "unknown")),
        action=_attributes(resolved, "home.preflight-run.action"),
        preflight_result=section(
            "home.preflight-result", view.get("preflight_result", "unknown")
        ),
    )
