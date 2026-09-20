"""The server-rendered workbench home surface.

The view layer receives an already-redacted presentation model, built by
:mod:`zworkbench.ui_view_model`.  It never reads the composition owner, never
infers a run status and never executes a business action.  The renderer owns
the information architecture; :mod:`zworkbench.ui_style` owns its visual
system.  Keeping those concerns separate lets the UI reference protocol stay
stable while the surface gets refined.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from .ui_declare import attribute_text, module_source_digest


_MODULE = "src/zworkbench/ui_home.py"

HOME_REFS = (
    ("home.root", "工作台首页", "region", None),
    ("home.workspace-context", "工作区与模式上下文", "region", "home.root"),
    ("home.run-facts", "运行事实", "region", "home.root"),
    ("home.record-list", "工作记录列表", "list", "home.root"),
    ("home.record-list.item", "工作记录项", "list-item", "home.record-list"),
    ("home.side-panel", "侧栏工作记录导航", "region", "home.root"),
    ("home.side-panel.new", "新建工作记录", "action", "home.side-panel"),
    ("home.side-panel.recent", "近期工作", "list", "home.side-panel"),
    ("home.side-panel.workspace", "工作区", "list", "home.side-panel"),
    ("home.current-intent", "当前意图与已记录文本", "region", "home.root"),
    ("home.plan-next-step", "计划与下一步", "region", "home.root"),
    ("home.artifacts", "产物区", "region", "home.root"),
    ("home.evidence", "证据区", "region", "home.root"),
    ("home.preflight-run.action", "预检并运行", "action", "home.root"),
    ("home.preflight-result", "预检结果", "detail", "home.preflight-run.action"),
    ("home.conversation", "会话消息流", "region", "home.root"),
    ("home.conversation.message", "会话消息", "list-item", "home.conversation"),
)


def home_registry() -> UiRefRegistry:
    """Declare every semantic unit the home slice renders."""
    registry = UiRefRegistry()
    digest = module_source_digest(Path(__file__))
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
    return home_registry().build_manifest(build=build or module_source_digest(Path(__file__)))


def _text(value: Any, fallback: str = "unknown") -> str:
    """Escape one view-model value without making presentation decisions."""
    if value is None or value == "":
        value = fallback
    return html.escape(str(value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _status(value: Any) -> str:
    """Return the status token used for styling and the visible label."""
    candidate = str(value or "unknown").strip().lower().replace("_", "-")
    allowed = {
        "created", "running", "recovering", "completed", "failed",
        "safe-stopped", "denied", "unknown", "ready", "not-applicable",
    }
    return candidate if candidate in allowed else "unknown"


def _scope(value: Any) -> str:
    candidate = str(value or "unknown").strip().lower().replace("_", "-")
    return candidate if candidate in {"implemented", "target", "unknown"} else "unknown"


def _status_chip(value: Any, *, source: Any = "source unknown") -> str:
    token = _status(value)
    labels = {
        "created": "已创建",
        "running": "进行中",
        "recovering": "恢复中",
        "completed": "已完成",
        "failed": "失败",
        "safe-stopped": "safe-stopped",
        "denied": "已拒绝",
        "unknown": "unknown",
        "ready": "可预检",
        "not-applicable": "不适用",
    }
    return (
        '<span class="status-chip status-{token}" data-status="{token}">'
        '<span class="status-dot" aria-hidden="true"></span>'
        '<b>{label}</b><code>{token}</code>'
        '<small>来源：{source}</small></span>'
    ).format(token=token, label=labels[token], source=_text(source))


def _value_title(value: Any, fallback: str) -> str:
    if isinstance(value, Mapping):
        return str(value.get("title") or value.get("label") or fallback)
    return fallback


def _value_summary(value: Any, fallback: str = "unknown") -> str:
    if isinstance(value, Mapping):
        return str(value.get("summary") or value.get("description") or value.get("text") or fallback)
    return str(value if value is not None else fallback)


def _items(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        value = value.get("items") or value.get("steps") or value.get("entries") or ()
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    try:
        return tuple(value)
    except TypeError:
        return (value,)


_PLAN_STEP_STATE_MAP = {
    "done": "done",
    "completed": "done",
    "current": "current",
    "running": "current",
    "in-progress": "current",
    "pending": "pending",
    "not-started": "pending",
    "todo": "pending",
    "unknown": "pending",
}

_PLAN_STEP_LABEL = {
    "done": "已完成",
    "current": "进行中",
    "pending": "待办",
}

_PLAN_STEP_MARKER = {
    "done": "✓",
    "current": "▸",
    "pending": "·",
}


def _plan_step_state(value: Any) -> str:
    """Map a plan-step status to a CSS state token (done/current/pending).

    Isolated from ``_status`` so plan-card semantics never leak into the
    run-status chip vocabulary.
    """
    candidate = str(value or "unknown").strip().lower().replace("_", "-")
    return _PLAN_STEP_STATE_MAP.get(candidate, "pending")


def _render_plan(value: Any) -> str:
    if isinstance(value, Mapping) and (value.get("steps") or value.get("items")):
        rows = []
        for index, item in enumerate(_items(value), 1):
            item_map = _mapping(item)
            state = _plan_step_state(item_map.get("state", item_map.get("status", "unknown")))
            title = item_map.get("title") or item_map.get("label") or item_map.get("text") or "unknown"
            detail = item_map.get("detail") or item_map.get("description")
            marker = _PLAN_STEP_MARKER.get(state, str(index))
            rows.append(
                '<li class="plan-row plan-{state}">'
                '<span class="plan-step" aria-hidden="true">{marker}</span>'
                '<span><strong>{title}</strong>{detail}</span>'
                '<code>{label}</code></li>'.format(
                    state=state,
                    marker=marker,
                    title=_text(title),
                    detail=("<small>{0}</small>".format(_text(detail)) if detail else ""),
                    label=_text(_PLAN_STEP_LABEL.get(state, state)),
                )
            )
        return '<ol class="plan-list">{0}</ol>'.format("".join(rows))
    return '<p class="section-copy">{0}</p>'.format(_text(_value_summary(value)))


def _render_items(value: Any, *, kind: str) -> str:
    entries = []
    for item in _items(value):
        item_map = _mapping(item)
        title = item_map.get("title") or item_map.get("name") or item_map.get("label") or item
        detail = item_map.get("summary") or item_map.get("description") or item_map.get("source")
        entries.append(
            '<li class="{kind}-row"><span class="row-mark" aria-hidden="true"></span>'
            '<span><strong>{title}</strong>{detail}</span></li>'.format(
                kind=kind,
                title=_text(title),
                detail=("<small>{0}</small>".format(_text(detail)) if detail else ""),
            )
        )
    if entries:
        return '<ul class="{0}-list">{1}</ul>'.format(kind, "".join(entries))
    return '<p class="section-copy section-empty">暂无已记录内容</p>'


def _render_record(record: Mapping[str, Any]) -> str:
    title = record.get("title") or record.get("name") or record.get("run_id") or "unknown"
    status = record.get("status") or record.get("state")
    identity = record.get("run_id") or record.get("key")
    activity = record.get("updated_at") or record.get("last_activity") or record.get("time")
    meta = ""
    if status or identity or activity:
        meta = (
            '<span class="record-meta"><code>{identity}</code><span>{status}</span></span>'
            '<span class="record-activity">{activity}</span>'
        ).format(
            identity=_text(identity),
            status=_text(status),
            activity=_text(activity),
        )
    return (
        '<li data-ui-ref="{ref}" class="record-item">'
        '<span class="record-title">{title}</span>{meta}</li>'
    ).format(
        ref="home.record-list.item",
        title=_text(title),
        meta=meta,
    )


def _render_side_panel(view: Mapping[str, Any]) -> str:
    """F3 — A-session side-panel navigation shell.

    Pure navigation shell: a new-record action (read-only, aria-disabled this
    round) plus recent-works and workspaces groups sourced from the
    owner-backed view model. Empty groups degrade to an explicit empty state.
    """
    new_action = (
        '<button type="button" class="side-action" aria-disabled="true" '
        'aria-label="新建工作记录（只读）">'
        '<span>新建工作记录</span>'
        '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>'
        '</button>'
    )
    recent = _items(view.get("recent"))
    if recent:
        recent_items = "".join(
            '<li class="side-item">{title}<small>{meta}</small></li>'.format(
                title=_text(_mapping(r).get("title") or _mapping(r).get("name") or r),
                meta=_text(_mapping(r).get("updated_at") or _mapping(r).get("status") or ""),
            )
            for r in recent
        )
        recent_block = '<ul class="side-list">{0}</ul>'.format(recent_items)
    else:
        recent_block = '<p class="side-empty">暂无近期工作</p>'
    workspaces = _items(view.get("workspaces"))
    if workspaces:
        ws_items = "".join(
            '<li class="side-item">{title}<small>{meta}</small></li>'.format(
                title=_text(_mapping(w).get("name") or w),
                meta=_text(_mapping(w).get("mode") or _mapping(w).get("status") or ""),
            )
            for w in workspaces
        )
        ws_block = '<ul class="side-list">{0}</ul>'.format(ws_items)
    else:
        ws_block = '<p class="side-empty">暂无工作区</p>'
    return (
        '{new_action}'
        '<p class="nav-label">近期工作</p>{recent_block}'
        '<p class="nav-label">工作区</p>{ws_block}'
    ).format(new_action=new_action, recent_block=recent_block, ws_block=ws_block)


def _render_run_facts(value: Any) -> str:
    """F7 — run-facts inspector shell (render-only; live values deferred).

    The inspector exposes the F7 field set -- mode, workspace, worker,
    approval, effect and evidence links -- as a static shell driven by the
    owner-backed projection. Fields the projection cannot yet supply read
    ``unknown``; the live values that would require a runtime query stay behind
    the 1-2-3 gate.
    """
    facts = _mapping(value)
    state = facts.get("status", "unknown")
    source = facts.get("source") or "source unknown"
    source_badge = "owner-backed" if source == "CompositionOwner" else "source unknown"
    rows = (
        ("run_id", facts.get("run_id", facts.get("run", "unknown"))),
        ("parent / child", facts.get("parent_child", "unknown")),
        ("mode", facts.get("mode", "unknown")),
        ("workspace", facts.get("workspace", "unknown")),
        ("worker", facts.get("worker", facts.get("provider", "unknown"))),
        ("approval", facts.get("approval", "unknown")),
        ("effect", facts.get("effect", "unknown")),
    )
    details = "".join(
        '<div class="fact-row"><dt>{label}</dt><dd>{value}</dd></div>'.format(
            label=_text(label), value=_text(value)
        )
        for label, value in rows
    )
    evidence_links = _items(facts.get("evidence_links"))
    if evidence_links:
        links = []
        for link in evidence_links:
            item = _mapping(link)
            links.append(
                '<li class="evidence-link-row">'
                '<a class="evidence-link" href="{href}" data-evidence-id="{eid}">{title}</a>'
                '<small>{identity}</small></li>'.format(
                    href=_text(item.get("href") or "#"),
                    eid=_text(item.get("event_id") or item.get("identity") or "unknown"),
                    title=_text(item.get("title") or "evidence"),
                    identity=_text(item.get("identity") or item.get("event_id") or "unknown"),
                )
            )
        evidence_block = (
            '<div class="evidence-links"><p class="eyebrow">EVIDENCE LINKS</p>'
            '<ul class="evidence-link-list">{0}</ul></div>'.format("".join(links))
        )
    else:
        evidence_block = '<p class="evidence-links evidence-empty">暂无证据链接</p>'
    return (
        '<div class="inspector-heading"><div><p class="eyebrow">RUNTIME FACTS</p>'
        '<h2>运行事实</h2></div><span class="source-badge">{source_badge}</span></div>'
        '<div class="state-card">{status}</div>'
        '<dl class="fact-list">{details}</dl>'
        '{evidence_block}'
        '<p class="source-note">判断来源：{source}</p>'.format(
            source_badge=_text(source_badge),
            status=_status_chip(state, source=source),
            details=details,
            evidence_block=evidence_block,
            source=_text(source),
        )
    )


def _render_conversation(view: Mapping[str, Any]) -> str:
    """F4 — A-session conversation message stream, read-only.

    Each message mirrors one owner-backed work record: a role avatar, a meta
    row (run identity, status, time) and the recorded intent, with an embedded
    plan-card whose step states come from ``ui_view_model``. The stream never
    invents events and never reaches back into the owner; an absent projection
    degrades to an explicit empty state.
    """
    messages = view.get("conversation")
    if not isinstance(messages, (list, tuple)) or not messages:
        return '<p class="conversation-empty">暂无会话消息</p>'
    role_labels = {"agent": "智能体", "human": "我", "system": "系统"}
    rows = []
    for message in messages:
        m = _mapping(message)
        role = _text(m.get("role") or "agent")
        avatar = _text((m.get("avatar_label") or role[:1].upper() or "A"))
        run_id = m.get("run_id") or "unknown"
        updated = m.get("updated_at") or "unknown"
        title = m.get("title") or run_id
        intent = m.get("intent") or "unknown"
        plan = m.get("plan")
        plan_html = (
            _render_plan(plan)
            if isinstance(plan, Mapping) and (plan.get("steps") or plan.get("items"))
            else ""
        )
        article = (
            '<article class="msg msg-{role}" data-ui-ref="home.conversation.message">'
            '<span class="msg-avatar" aria-hidden="true">{avatar}</span>'
            '<div class="msg-body">'
            '<div class="msg-meta">'
            '<span class="msg-role">{role_label}</span>'
            '<code class="msg-run">{run_id}</code>'
            '{status}'
            '<time class="msg-time">{time}</time>'
            '</div>'
            '<div class="msg-content"><p class="msg-title">{title}</p>'
            '<p class="msg-intent">{intent}</p></div>'
            '{plan}'
            '</div></article>'
        ).format(
            role=_text(role),
            avatar=avatar,
            role_label=_text(role_labels.get(role, role)),
            run_id=_text(run_id),
            status=_status_chip(
                m.get("status") or "unknown",
                source=m.get("source", "CompositionOwner"),
            ),
            time=_text(updated),
            title=_text(title),
            intent=_text(intent),
            plan=plan_html,
        )
        rows.append(article)
    return '<ol class="conversation-list">{0}</ol>'.format("".join(rows))


def render_home(view: Mapping[str, Any], *, manifest: Mapping[str, Any] = None) -> str:
    """Render the home surface from a redacted view model.

    The DOM order intentionally follows the review-mode focus contract:
    workspace context, run facts, record list, then the central work surface.
    CSS grid places the run facts on the right without changing that semantic
    order.
    """
    resolved = manifest or home_manifest()
    records: Sequence[Mapping[str, Any]] = view.get("records") or ()

    if records:
        items = "".join(_render_record(record) for record in records)
    else:
        items = '<li class="records-empty"><span class="empty-mark" aria-hidden="true"></span>' \
            '<strong>还没有工作记录</strong><span>完成一次本地只读运行后，Owner-backed 记录会出现在这里。</span></li>'

    raw_workspace = view.get("workspace")
    workspace = _mapping(raw_workspace)
    workspace_name = workspace.get("name") or (raw_workspace if raw_workspace not in (None, "") and not workspace else "unknown")
    workspace_mode = workspace.get("mode") or "unknown"
    workspace_status = workspace.get("status") or view.get("workspace_status") or "unknown"
    status_token = _status(workspace_status)
    _STATUS_COLOR_TOKENS = {
        "created", "running", "recovering", "completed",
        "failed", "safe-stopped", "denied", "ready", "not-applicable",
    }
    status_class = "status-" + status_token if status_token in _STATUS_COLOR_TOKENS else "scope-target"
    intent = view.get("intent", "unknown")
    intent_title = _value_title(intent, "当前工作")
    intent_summary = _value_summary(intent)
    preflight = _mapping(view.get("preflight_result"))
    preflight_status = preflight.get("status", view.get("preflight_result", "unknown"))

    return (
        '<main {root} class="workbench-page">'
        '<header {workspace_ref} class="workspace-bar">'
        '<div class="brand-lockup"><span class="brand-mark" aria-hidden="true">'
        '<svg viewBox="0 0 24 24"><path d="M5 4h14v13H8l-3 3V4Z"/><path d="m9 9 3 3 3-3"/></svg>'
        '</span><span class="brand-name">ZWorkbench</span><span class="breadcrumb">/ workbench</span></div>'
        '<div class="workspace-meta"><span class="meta-pill"><span class="status-dot" aria-hidden="true"></span>{workspace}</span>'
        '<span class="scope-tag scope-{scope}">{mode}</span>'
        '<span class="scope-tag {status_class}">{status}</span>'
        '<button type="button" class="icon-button" aria-disabled="true" aria-label="工作台信息（只读）">'
        '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/></svg>'
        '</button></div>'
        '</header>'
        '<nav class="view-nav" aria-label="工作台视图">'
        '<a href="/home" tabindex="-1" aria-current="page">工作台</a>'
        '<a href="/task-detail" tabindex="-1">任务详情</a>'
        '<a href="/record-view" tabindex="-1">记录视图</a></nav>'
        '<div class="home-layout">'
        '<section {facts_ref} class="home-inspector">{facts}</section>'
        '<div class="home-sidebar">'
        '<aside class="side-panel" {side_panel_ref}>{side_panel}</aside>'
        '<nav {list_ref} class="home-records" aria-label="工作记录">'
        '<div class="records-heading"><div><p class="eyebrow">WORK RECORDS</p><h2>工作记录</h2></div>'
        '<span class="record-count">{record_count:02d}</span></div>'
        '<p class="records-caption">从 Owner 恢复的上下文中</p><ul class="record-list">{items}</ul>'
        '<p class="records-boundary">只读索引 · 不在浏览器保存 Run 状态</p></nav>'
        '</div>'
        '<section class="home-content">'
        '<section {conv_ref} class="home-section conversation-section">'
        '<div class="section-heading"><div><p class="eyebrow">CONVERSATION</p>'
        '<h2>会话消息流</h2></div><span class="section-source">view model</span></div>'
        '{conversation}</section>'
        '<section {intent_ref} class="home-section intent-section">'
        '<div class="section-heading"><p class="eyebrow">CURRENT WORK</p>{intent_status}</div>'
        '<h1>{intent_title}</h1><p class="intent-summary">{intent_summary}</p>'
        '<div class="intent-context"><span>mode</span><code>{mode}</code><span>workspace</span><code>{workspace}</code></div>'
        '</section>'
        '<section {plan_ref} class="home-section plan-section plan-card">'
        '<div class="section-heading"><div><p class="eyebrow">PLAN CARD · 计划卡</p><h2>计划与下一步</h2></div>'
        '<span class="section-source">view model</span></div>{plan}'
        '<ul class="plan-legend" aria-label="步骤态图例">'
        '<li><span class="legend-dot legend-done">✓</span>已完成</li>'
        '<li><span class="legend-dot legend-current">▸</span>进行中</li>'
        '<li><span class="legend-dot legend-pending">·</span>待办</li>'
        '</ul></section>'
        '<div class="home-secondary-grid">'
        '<section {artifacts_ref} class="home-section compact-section"><div class="section-heading"><div><p class="eyebrow">ARTIFACTS</p><h2>产物</h2></div></div>{artifacts}</section>'
        '<section {evidence_ref} class="home-section compact-section"><div class="section-heading"><div><p class="eyebrow">EVIDENCE</p><h2>证据</h2></div></div>{evidence}</section>'
        '</div>'
        '<section class="home-action-block"><div><p class="eyebrow">BOUNDARY</p><strong>下一步仍需显式预检</strong><p>当前页面只展示已记录事实；不会从页面启动 Run、写入工作区或切换 Provider。</p></div>'
        '<button {action_ref} class="preflight-button" type="button" aria-disabled="true">预检并运行<span>只读入口</span></button></section>'
        '<section {preflight_ref} class="preflight-result"><div class="section-heading"><div><p class="eyebrow">PREFLIGHT</p><h2>预检结果</h2></div></div>{preflight}</section>'
        '</section></div></main>'
    ).format(
        root=attribute_text(resolved, "home.root"),
        workspace_ref=attribute_text(resolved, "home.workspace-context"),
        facts_ref=attribute_text(resolved, "home.run-facts"),
        list_ref=attribute_text(resolved, "home.record-list"),
        side_panel_ref=attribute_text(resolved, "home.side-panel"),
        side_panel=_render_side_panel(view),
        conv_ref=attribute_text(resolved, "home.conversation"),
        conversation=_render_conversation(view),
        intent_ref=attribute_text(resolved, "home.current-intent"),
        plan_ref=attribute_text(resolved, "home.plan-next-step"),
        artifacts_ref=attribute_text(resolved, "home.artifacts"),
        evidence_ref=attribute_text(resolved, "home.evidence"),
        action_ref=attribute_text(resolved, "home.preflight-run.action"),
        preflight_ref=attribute_text(resolved, "home.preflight-result"),
        workspace=_text(workspace_name),
        mode=_text(workspace_mode),
        scope=_scope(workspace_status),
        status=_text(workspace_status),
        status_class=status_class,
        facts=_render_run_facts(view.get("run_facts", {})),
        items=items,
        record_count=len(records),
        intent_status=_status_chip(_mapping(intent).get("status", view.get("state", "unknown")), source=_mapping(intent).get("source", "Owner / recorded input")),
        intent_title=_text(intent_title),
        intent_summary=_text(intent_summary),
        plan=_render_plan(view.get("plan", "unknown")),
        artifacts=_render_items(view.get("artifacts", "unknown"), kind="artifact"),
        evidence=_render_items(view.get("evidence", "unknown"), kind="evidence"),
        preflight=_status_chip(preflight_status, source=preflight.get("source", "preflight not recorded")),
    )
