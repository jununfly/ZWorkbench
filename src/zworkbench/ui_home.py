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
    ("home.run-rail", "运行轨道栏", "region", "home.root"),
    ("home.scenario-state", "场景状态", "region", "home.root"),
    ("home.safe-stop", "安全停止", "region", "home.root"),
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
    ("home.ui-reference-collab", "UI 引用协同状态", "region", "home.root"),
    ("home.variant-switcher", "三变体调试切换器", "region", "home.root"),
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


#: F10 run-rail lifecycle track. The happy path is created -> running ->
#: completed; terminal branches (failed / safe-stopped / denied) mark the
#: running node in red and append a terminal label. Any other status (including
#: unknown) leaves every node pending and no terminal label.
_RAIL_STAGES = (
    ("created", "已创建"),
    ("running", "进行中"),
    ("completed", "已完成"),
)
_RAIL_TERMINAL = {
    "failed": "失败",
    "safe-stopped": "safe-stopped",
    "denied": "已拒绝",
}


def _rail_stage_classes(status: str) -> "tuple":
    """Return (active_index, terminal_label_or_None) for the run-rail track."""

    if status == "created":
        return 0, None
    if status in ("running", "recovering"):
        return 1, None
    if status == "completed":
        return 2, None
    if status in _RAIL_TERMINAL:
        return 1, _RAIL_TERMINAL[status]
    return -1, None


#: F11 scenario state machine — render shell only. The four canonical scenario
#: states describe the overall workbench scenario. Real derivation of "approval"
#: (safe-stop / approval judgment) stays behind the 1-2 product gate (F13); here
#: the model is pure presentation: it validates a token and returns descriptors.
#: ``tone`` drives both the node dot and the banner accent so a glance shows the
#: live state. "empty" is the start; "stopped" is a recoverable terminal.
_SCENARIO_STATES = (
    ("empty", "空场景", "empty", "还没有任何工作记录或计划；完成一次本地只读运行后会出现内容。"),
    ("planning", "规划中", "planning", "已载入计划或当前意图，正在评审 / 推进计划步骤。"),
    ("approval", "待审批", "approval", "存在待人类审批的 Approval / Effect；真实审批交互留 product gate。"),
    ("stopped", "已停止", "stopped", "场景被 safe-stopped；需 reconcile 后才能继续。"),
)
_SCENARIO_KEYS = frozenset(state[0] for state in _SCENARIO_STATES)
_SCENARIO_LABELS = {state[0]: state[1] for state in _SCENARIO_STATES}
_SCENARIO_TONES = {state[0]: state[2] for state in _SCENARIO_STATES}
_SCENARIO_BLURBS = {state[0]: state[3] for state in _SCENARIO_STATES}

#: Transition edges of the scenario state machine (pure data; the render shell
#: does not enforce them). They document the intended flow for the eventual
#: product-gate wiring, not behaviour exercised by this shell.
_SCENARIO_TRANSITIONS = {
    "empty": ("planning",),
    "planning": ("approval", "stopped"),
    "approval": ("planning", "stopped"),
    "stopped": ("planning",),
}


def _scenario_state_token(state: Any) -> str:
    """Normalise and validate a scenario-state token.

    Returns the canonical token, or ``"unknown"`` for a missing or unrecognised
    value so the shell never presents a fabricated state.
    """

    candidate = str(state or "unknown").strip().lower().replace("_", "-")
    return candidate if candidate in _SCENARIO_KEYS else "unknown"


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


def _render_run_rail(value: Any) -> str:
    """F10 — run-rail inspector shell (render-only; executable Run deferred).

    The rail shows the run's lifecycle position (created -> running -> completed,
    terminal states flagged in red), a disabled "executable Run" button whose
    real trigger stays behind the 1-2-3 product gate, the owner-backed record
    list and a chronological evidence timeline. Every value comes from the
    owner-backed projection; a missing value reads ``unknown``.
    """
    rail = _mapping(value)
    state = rail.get("status", "unknown")
    source = rail.get("source") or "source unknown"
    source_badge = "owner-backed" if source == "CompositionOwner" else "source unknown"
    active_index, terminal_label = _rail_stage_classes(_status(state))
    stage_spans = []
    for idx, (key, label) in enumerate(_RAIL_STAGES):
        if active_index < 0:
            cls = "rail-pending"
        elif idx < active_index:
            cls = "rail-done"
        elif idx == active_index:
            cls = "rail-current"
        else:
            cls = "rail-pending"
        stage_spans.append(
            '<span class="rail-node {cls}"><i aria-hidden="true"></i>{label}</span>'.format(
                cls=cls, label=_text(label)
            )
        )
    rail_track = '<div class="rail-track">{0}</div>'.format("".join(stage_spans))
    terminal = (
        '<span class="rail-terminal">{0}</span>'.format(_text(terminal_label))
        if terminal_label
        else ""
    )
    run_button = (
        '<button type="button" class="rail-run-button" aria-disabled="true" '
        'aria-label="可执行 Run（留 product gate）">'
        '<span class="rail-run-glyph" aria-hidden="true">&#9654;</span>可执行 Run'
        '<span>留 product gate</span></button>'
    )
    owner_records = _items(rail.get("owner_records"))
    if owner_records:
        rec_rows = "".join(
            '<li><code>{rid}</code><span>{rstatus}</span><time>{time}</time></li>'.format(
                rid=_text(_mapping(r).get("run_id") or "unknown"),
                rstatus=_text(_mapping(r).get("status") or "unknown"),
                time=_text(_mapping(r).get("updated_at") or ""),
            )
            for r in owner_records
        )
        records_block = (
            '<div class="rail-records"><p class="eyebrow">OWNER RECORDS</p>'
            '<ul class="rail-record-list">{0}</ul></div>'.format(rec_rows)
        )
    else:
        records_block = '<p class="rail-records rail-empty">暂无 Owner 记录</p>'
    timeline = _items(rail.get("evidence_timeline"))
    if timeline:
        t_rows = []
        for node in timeline:
            n = _mapping(node)
            t_rows.append(
                '<li><time>{time}</time>'
                '<a class="rail-timeline-link" href="{href}">{type}</a>'
                '<code>{eid}</code></li>'.format(
                    time=_text(n.get("created_at") or ""),
                    href=_text(n.get("href") or "#"),
                    type=_text(n.get("type") or "evidence"),
                    eid=_text(n.get("event_id") or "unknown"),
                )
            )
        timeline_block = (
            '<div class="rail-timeline"><p class="eyebrow">EVIDENCE TIMELINE</p>'
            '<ol class="rail-timeline-list">{0}</ol></div>'.format("".join(t_rows))
        )
    else:
        timeline_block = '<p class="rail-timeline rail-empty">暂无证据时间线</p>'
    return (
        '<div class="inspector-heading"><div><p class="eyebrow">RUN RAIL</p>'
        '<h2>运行轨道栏</h2></div><span class="source-badge">{source_badge}</span></div>'
        '{rail_track}{terminal}'
        '{run_button}'
        '{records_block}'
        '{timeline_block}'
        '<p class="source-note">判断来源：{source}</p>'.format(
            source_badge=_text(source_badge),
            rail_track=rail_track,
            terminal=terminal,
            run_button=run_button,
            records_block=records_block,
            timeline_block=timeline_block,
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


def _render_scenario_state(value: Any) -> str:
    """F11 — scenario state machine UI (render-only; wiring deferred).

    Renders a four-state stepper (empty -> planning -> approval -> stopped) with
    the active state highlighted, a blurb describing the active state and a
    source badge.  A missing or invalid state reads as ``unknown`` and no node
    is marked active.  No control in this shell triggers a run, approval or
    stop: those belong to the 1-2 product gate (F13).
    """

    scenario = _mapping(value)
    raw_state = scenario.get("state", "unknown")
    source = scenario.get("source") or "source unknown"
    state = _scenario_state_token(raw_state)
    source_badge = "owner-backed" if source == "CompositionOwner" else "source unknown"

    nodes = []
    for key, label_zh, tone, _blurb in _SCENARIO_STATES:
        if state == "unknown":
            cls = "ss-node ss-unknown"
        elif key == state:
            cls = "ss-node ss-active ss-{0}".format(tone)
        else:
            cls = "ss-node ss-{0}".format(tone)
        nodes.append(
            '<li class="{cls}"><span class="ss-dot" aria-hidden="true"></span>'
            '<span class="ss-label">{label}</span></li>'.format(
                cls=cls, label=_text(label_zh)
            )
        )
    stepper = '<ol class="ss-track" aria-label="场景状态">{0}</ol>'.format("".join(nodes))

    tone = _SCENARIO_TONES.get(state, "unknown")
    blurb = _SCENARIO_BLURBS.get(state, "状态未知（真实判定留 product gate）。")
    return (
        '<div class="scenario-state ss-{tone}">'
        '<div class="section-heading"><div><p class="eyebrow">SCENARIO STATE · 场景状态机</p>'
        '<h2>场景状态</h2></div>'
        '<span class="section-source">{source_badge}</span></div>'
        '{stepper}'
        '<p class="ss-blurb">{blurb}</p>'
        '</div>'
    ).format(
        tone=_text(tone),
        source_badge=_text(source_badge),
        stepper=stepper,
        blurb=_text(blurb),
    )


def _render_safe_stop(value: Any) -> str:
    """F13 — safe-stop / reconcile banner (render-only; wiring deferred).

    Renders a prominent alert banner when the scenario is in the ``stopped``
    state, carrying a disabled "请求 reconcile" CTA.  The banner is derived from
    the owner-backed ``scenario_state`` projection (active only when stopped);
    the actual reconcile trigger and the identity-unresolved / boundary
    detection that motivates it are product-gate logic (F13 越界判定), not
    exercised here.  When inactive it renders an empty section so the declared
    ref stays audit-clean without a visible banner.
    """

    safe = _mapping(value)
    active = bool(safe.get("active"))
    source = safe.get("source") or "source unknown"
    if not active:
        return '<div {ref} class="safe-stop safe-stop-inactive" aria-hidden="true"></div>'.format(
            ref=attribute_text(home_manifest(), "home.safe-stop")
        )

    tone = _text(safe.get("tone") or "stopped")
    message = safe.get("message_zh") or "场景已安全停止（safe-stop）。恢复需 reconcile。"
    reconcile_label = safe.get("reconcile_label_zh") or "请求 reconcile"
    disabled = bool(safe.get("reconcile_disabled", True))
    source_badge = "owner-backed" if source == "CompositionOwner" else "source unknown"
    return (
        '<div {ref} class="safe-stop ss-stopped" role="alert">'
        '<div class="section-heading"><div><p class="eyebrow">SAFE STOP · 安全停止 / reconcile</p>'
        '<h2>安全停止</h2></div>'
        '<span class="section-source">{source_badge}</span></div>'
        '<p class="safe-stop-message">{message}</p>'
        '<div class="safe-stop-actions">'
        '<button type="button" class="reconcile-button" aria-disabled="true" disabled>{label}</button>'
        '<span class="safe-stop-hint">真实 reconcile 触发属 product gate（F13 越界判定），本轮仅渲染请求入口。</span>'
        '</div></div>'
    ).format(
        ref=attribute_text(home_manifest(), "home.safe-stop"),
        source_badge=_text(source_badge),
        message=_text(message),
        label=_text(reconcile_label),
    )


def _collab_status_token(value: Any) -> str:
    """Map a ui-reference status to the scope-* token used for styling/labels."""

    candidate = str(value or "unknown").strip().lower().replace("_", "-").replace(" ", "-")
    allowed = {
        "implemented", "target", "unknown", "hold", "blocked", "migrated",
        "retired", "incompatible", "source-mismatch", "manifest-missing",
        "ambiguous", "unavailable", "expired",
    }
    return candidate if candidate in allowed else "unknown"


def _render_collab_list(items: Any) -> str:
    """Render an uncovered_items / next_evidence list, or nothing when empty."""

    items = items if isinstance(items, (list, tuple)) else ()
    if not items:
        return ""
    return "<ul class=\"urc-evidence\">{0}</ul>".format(
        "".join("<li>{0}</li>".format(_text(item)) for item in items)
    )


def _render_ui_reference_collab(value: Any) -> str:
    """F15 r2 — r2-ui-reference-skills 协同可视化（read-only projection）.

    Renders, per ui-reference skill, its ``profile_status`` and ``runtime_status``
    as two status pills plus the reason and the uncovered / next-evidence the
    collaboration still needs. ``unknown`` is shown in plain sight (rose), never
    hidden: that is the whole point of the panel -- it tells a human and an agent
    what evidence is still missing. No control here triggers a skill run or reads
    a runtime; the live invocation seam is the product gate (1-2).
    """

    collab = _mapping(value)
    skills = collab.get("skills") or ()
    if not skills:
        return (
            '<div {ref} class="ui-ref-collab ui-ref-collab-empty" aria-hidden="true"></div>'
        ).format(ref=attribute_text(home_manifest(), "home.ui-reference-collab"))

    rows = []
    for skill in skills:
        skill = _mapping(skill)
        profile = _mapping(skill.get("profile_status"))
        runtime = _mapping(skill.get("runtime_status"))
        p_status = _collab_status_token(profile.get("status"))
        r_status = _collab_status_token(runtime.get("status"))
        row = (
            '<li class="urc-row">'
            '<div class="urc-skill"><span class="urc-skill-name">{name}</span>'
            '<span class="urc-skill-id">{sid}</span></div>'
            '<div class="urc-statuses">'
            '<div class="urc-status urc-profile scope-{pcls}">'
            '<span class="urc-status-key">profile_status</span>'
            '<span class="urc-pill">{pstatus}</span>'
            '<span class="urc-reason">{preason}</span>'
            '{puncovered}{pnext}</div>'
            '<div class="urc-status urc-runtime scope-{rcls}">'
            '<span class="urc-status-key">runtime_status</span>'
            '<span class="urc-pill">{rstatus}</span>'
            '<span class="urc-reason">{rreason}</span>'
            '{runcovered}{rnext}</div>'
            '</div></li>'
        ).format(
            name=_text(skill.get("skill_zh")),
            sid=_text(skill.get("skill")),
            pcls=p_status, rcls=r_status,
            pstatus=_text(profile.get("status")),
            rstatus=_text(runtime.get("status")),
            preason=_text(profile.get("reason")),
            rreason=_text(runtime.get("reason")),
            puncovered=_render_collab_list(profile.get("uncovered_items")),
            runcovered=_render_collab_list(runtime.get("uncovered_items")),
            pnext=_render_collab_list(profile.get("next_evidence")),
            rnext=_render_collab_list(runtime.get("next_evidence")),
        )
        rows.append(row)
    return (
        '<section {ref} class="ui-ref-collab">'
        '<div class="section-heading"><div><p class="eyebrow">UI REFERENCE · 协同可视化</p>'
        '<h2>UI 引用协同状态</h2></div>'
        '<span class="section-source">{source}</span></div>'
        '<p class="urc-caption">协议设计 / 运行时实现两 skill 的 profile_status 与 runtime_status；'
        'unknown 须显式给出待补证据。</p>'
        '<ul class="urc-list">{rows}</ul>'
        '<p class="urc-boundary">只读投影 · 实时调用留 product gate（1-2）</p>'
        '</section>'
    ).format(
        ref=attribute_text(home_manifest(), "home.ui-reference-collab"),
        source=_text(collab.get("source") or "source unknown"),
        rows="".join(rows),
    )


def _render_variant_switcher(value: Any) -> str:
    """Render the F19 three-variant debug switcher.

    Round 1 ships the shell only: three ``?variant=A|B|C`` links (no script --
    normal mode never loads one) with the active variant highlighted, plus a
    read-only projection of the current selection. The actual per-variant content
    branch is a product-gate (1-2) concern and is not performed here. An
    out-of-range or absent value is shown honestly (default, invalid) and never
    crashes or injects, because every echoed string passes through :func:`_text`.
    """
    variant = _mapping(value)
    selected = _text(variant.get("selected"))
    valid = bool(variant.get("valid"))
    options = variant.get("options") or ()
    links = "".join(
        '<a class="vs-option{active}" href="?variant={vid}" data-variant="{vid}">{vid}</a>'.format(
            vid=_text(opt.get("id")),
            active=" vs-option-active" if opt.get("active") else "",
        )
        for opt in options
    )
    invalid_note = (
        ""
        if valid
        else '<span class="vs-invalid">（越界/无效，已回退默认）</span>'
    )
    return (
        '<section {ref} class="variant-switcher">'
        '<div class="section-heading"><div><p class="eyebrow">DEBUG · 三变体切换器</p>'
        '<h2>UI 变体调试切换器</h2></div>'
        '<span class="section-source">{source}</span></div>'
        '<p class="vs-caption">通过 ?variant=A|B|C 在客户端切换渲染变体'
        '（纯 UI 壳，本轮仅切换器 + 只读投影，实际分支留 1-2）。</p>'
        '<div class="vs-options">{links}</div>'
        '<p class="vs-state">当前变体：<span class="vs-current">{selected}</span>{invalid}</p>'
        '</section>'
    ).format(
        ref=attribute_text(home_manifest(), "home.variant-switcher"),
        source=_text(variant.get("source") or "source unknown"),
        links=links,
        selected=selected,
        invalid=invalid_note,
    )


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
        '<section {scenario_state_ref} class="scenario-state-wrap">{scenario_state}</section>'
        '{safe_stop}'
        '{ui_reference_collab}'
        '{variant_switcher}'
        '<div class="home-layout">'
        '<section {facts_ref} class="home-inspector">{facts}'
        '<div {run_rail_ref} class="run-rail">{run_rail}</div></section>'
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
        run_rail_ref=attribute_text(resolved, "home.run-rail"),
        scenario_state_ref=attribute_text(resolved, "home.scenario-state"),
        ui_reference_collab_ref=attribute_text(resolved, "home.ui-reference-collab"),
        scenario_state=_render_scenario_state(view.get("scenario_state", {})),
        safe_stop=_render_safe_stop(view.get("safe_stop", {})),
        ui_reference_collab=_render_ui_reference_collab(view.get("ui_reference_collab", {})),
        variant_switcher=_render_variant_switcher(view.get("variant", {})),
        run_rail=_render_run_rail(view.get("run_rail", {})),
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
