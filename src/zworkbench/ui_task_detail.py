"""Task-detail view declarations, used by the coverage matrix only.

This module holds the structural contract for the task-detail view.  The
renderer is a fixture-level helper; the real rendering belongs to a future
host.
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any, Dict, Mapping

from .ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from .ui_runtime import render_attributes


_MODULE = "src/zworkbench/ui_task_detail.py"
_TASK_DETAIL_REFS = (
    ("task-detail.intent", "意图", "region", None),
    ("task-detail.admission-check", "准入检查", "region", "task-detail.intent"),
    ("task-detail.denial-reason", "拒绝原因", "detail", "task-detail.admission-check"),
    ("task-detail.execution-identity", "执行身份", "detail", "task-detail.intent"),
    ("task-detail.timeline", "时间线", "region", "task-detail.intent"),
    ("task-detail.result", "执行结果", "detail", "task-detail.timeline"),
    ("task-detail.error", "错误信息", "detail", "task-detail.timeline"),
    ("task-detail.effect", "Effect 展示", "detail", "task-detail.intent"),
    ("task-detail.approval", "Approval 展示", "detail", "task-detail.intent"),
    ("task-detail.reconcile", "Reconcile 展示", "detail", "task-detail.intent"),
    ("task-detail.replay-mode", "Replay 模式说明", "detail", "task-detail.intent"),
)


def _module_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def task_detail_registry() -> UiRefRegistry:
    registry = UiRefRegistry()
    digest = _module_digest()
    for ref, semantic_zh, kind, parent in _TASK_DETAIL_REFS:
        registry.declare(
            UiRefDeclaration(
                ref=ref,
                semantic_zh=semantic_zh,
                kind=kind,
                view="task-detail",
                source=SourceAnchor(
                    repo_path=_MODULE, symbol="task_detail_registry", content_digest=digest,
                ),
                parent=parent,
            )
        )
    return registry


def task_detail_manifest(*, build: str = None) -> Dict[str, Any]:
    return task_detail_registry().build_manifest(build=build or _module_digest())


def _attr(manifest: Mapping[str, Any], ref: str) -> str:
    rendered = render_attributes(manifest, ref)
    return " ".join(
        '{0}="{1}"'.format(name, html.escape(value, quote=True))
        for name, value in sorted(rendered.items())
    )


def render_task_detail(view: Mapping[str, Any], *, manifest: Mapping[str, Any] = None) -> str:
    """Fixture-level renderer for coverage assertions.

    ``view["not_applicable"]`` maps a reference to the reason it does not apply
    to this run. It comes from the view model, which knows the run class; the
    renderer does not decide what applies.
    """
    m = manifest or task_detail_manifest()
    excused = dict(view.get("not_applicable") or {})

    def section(ref, value):
        """Render one unit, or state why it does not apply to this run.

        An excused unit must not carry its reference: a coverage report that
        counted it as both rendered and not applicable would contradict itself.
        The reason is shown rather than dropped, because "not applicable" and
        "unknown" are different claims and a reviewer needs to see which one
        this is.
        """
        if ref in excused:
            return '<section data-ui-not-applicable="{0}">{1}</section>'.format(
                html.escape(ref, quote=True), html.escape(str(excused[ref]))
            )
        return "<section {0}>{1}</section>".format(
            _attr(m, ref), html.escape(str(value))
        )

    return (
        "<main {root}>"
        "{intent}{admission}{denial}{identity}{timeline}"
        "{result}{error}{effect}{approval}{reconcile}{replay}"
        "</main>"
    ).format(
        root=_attr(m, "task-detail.intent"),
        intent=section("task-detail.intent", view.get("intent", "unknown")),
        admission=section(
            "task-detail.admission-check",
            view.get("admission", {}).get("status", "unknown"),
        ),
        denial=section("task-detail.denial-reason", view.get("denial", "unknown")),
        identity=section(
            "task-detail.execution-identity", view.get("identity", "unknown")
        ),
        timeline=section("task-detail.timeline", view.get("timeline", "unknown")),
        result=section("task-detail.result", view.get("result", "unknown")),
        error=section("task-detail.error", view.get("error", "unknown")),
        effect=section("task-detail.effect", view.get("effect", "unknown")),
        approval=section("task-detail.approval", view.get("approval", "unknown")),
        reconcile=section("task-detail.reconcile", view.get("reconcile", "unknown")),
        replay=section("task-detail.replay-mode", view.get("replay_mode", "unknown")),
    )
