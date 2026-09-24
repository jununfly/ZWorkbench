"""The control-plane facade: durable owner state to redacted view models.

The views must not read owner storage. This module is the only path between
the two, and it goes one way: it calls the owner's read-only surface and
returns plain JSON-compatible data. Nothing it returns can be used to reach
back into the owner, and it invokes no method that changes state.

Selection is a whitelist. Every field a view can display is named here, and
anything not named is absent -- including columns added to the owner later. A
blacklist would have the opposite default: a new field is shown until someone
remembers to exclude it, which for a presentation layer means leaking by
default.

The owner rejects credential *field names* on write, but a secret pasted into
free text still lands in durable state. Redaction here is therefore a second,
value-level pass over the text this module is about to hand to a view.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import parse_qs

#: Credential shapes that may appear inside otherwise ordinary prose.
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
_LOCAL_PATH = re.compile(r"/(?:Users|home|private|tmp|var)/[^\s<>\"']+")
REDACTED = "<redacted>"

UNKNOWN = "unknown"

#: Canonical debug variant vocabulary for the F19 three-variant switcher.
#: Round 1 ships the switcher shell + read-only projection only; the actual
#: per-variant content branch is a product-gate (1-2) concern. Anything not in
#: this catalogue (including an absent value) resolves to ``HOME_VARIANT_DEFAULT``
#: and is reported as ``valid: False`` so the shell never crashes or injects.
HOME_VARIANT_CATALOG = ("A", "B", "C")
HOME_VARIANT_DEFAULT = "default"

#: Canonical status vocabulary shared by the r2-ui-reference-skills status
#: reports (profile_status.py / runtime_status.py). Copied verbatim from the
#: skill contracts so the projection can validate and pass through a status
#: without importing the skill packages (the r2 PRD forbids implicit cross-skill
#: imports). Treat this as a mirror of the contract, not a source of truth.
UI_REFERENCE_STATUS_CATALOG = (
    "implemented",
    "target",
    "unknown",
    "HOLD",
    "blocked",
    "migrated",
    "retired",
    "incompatible",
    "source-mismatch",
    "manifest-missing",
    "ambiguous",
    "unavailable",
    "expired",
)


def _ui_reference_status(
    status: Any,
    reason: str,
    uncovered: Iterable[str] = (),
    next_evidence: Iterable[str] = (),
) -> Dict[str, Any]:
    """Project one r2-ui-reference-skills status report into the view model.

    Mirrors the shape emitted by ``profile_status.py`` / ``runtime_status.py``
    (``status``, ``reason``, ``uncovered_items``, ``next_evidence``,
    ``status_catalog``) while applying the same redaction and unknown-first
    discipline the rest of the facade uses. A status outside the catalog is
    collapsed to ``unknown`` rather than echoed.
    """

    token = str(status or UNKNOWN).strip()
    if token not in UI_REFERENCE_STATUS_CATALOG:
        token = UNKNOWN
    return {
        "status": token,
        "reason": display_text(reason),
        "uncovered_items": [display_text(item) for item in uncovered],
        "next_evidence": [display_text(item) for item in next_evidence],
        "status_catalog": list(UI_REFERENCE_STATUS_CATALOG),
    }


#: Read-only, build-time snapshot of the r2-ui-reference-skills collaboration
#: surface. Round 1 does not invoke the skill subprocesses, so this declared
#: catalog is the projection source. Live invocation of ``profile_status.py`` /
#: ``runtime_status.py`` belongs to the 1-2 product gate.
UI_REFERENCE_SKILL_COLLAB_CATALOG = (
    {
        "skill": "ui-reference-protocol",
        "skill_zh": "UI 引用协议设计",
        "profile_status": (
            "implemented",
            "protocol-design-skill-implemented",
            (),
            (),
        ),
        "runtime_status": (
            "unknown",
            "design-skill-no-runtime-evidence",
            ("runtime-evidence",),
            ("协议设计 skill 只产出/校验 profile；运行时证据由 runtime skill 负责",),
        ),
    },
    {
        "skill": "ui-reference-runtime",
        "skill_zh": "UI 引用运行时实现",
        "profile_status": (
            "implemented",
            "runtime-skill-profile-aligned",
            (),
            (),
        ),
        "runtime_status": (
            "unknown",
            "zworkbench-specific-profile-evidence-deferred",
            ("zworkbench-specific-profile-acceptance",),
            ("ZWorkbench 专属 profile 联调验证（按 r2 PRD 为 deferred/unknown，留 product gate 1-2）",),
        ),
    },
)


def ui_reference_collab_view_model() -> Dict[str, Any]:
    """Project the r2-ui-reference-skills collaboration surface (F15 r2).

    A read-only panel that visualises each ui-reference skill's
    ``profile_status`` and ``runtime_status`` so a human and agent can see at a
    glance whether the UI-reference capability is aligned to spec. No owner
    field, no method call, no runtime dependency -- derived solely from the
    declared catalog, exactly like the F14 ``session_references`` surface.
    """

    skills = []
    for entry in UI_REFERENCE_SKILL_COLLAB_CATALOG:
        skills.append(
            {
                "skill": display_text(entry["skill"]),
                "skill_zh": display_text(entry["skill_zh"]),
                "profile_status": _ui_reference_status(*entry["profile_status"]),
                "runtime_status": _ui_reference_status(*entry["runtime_status"]),
                "source": "r2-ui-reference-skills (declared snapshot)",
            }
        )
    return {
        "skills": skills,
        "source": "r2-ui-reference-skills (declared snapshot)",
    }


def display_text(value: Any) -> str:
    """Render one owner value as display text, with credentials removed.

    Public because it is a defence in its own right and is tested directly.
    Field selection keeps most owner data out of a view, but the values that
    *are* shown -- a run identifier, an event type -- are caller-supplied text.
    """
    if value is None:
        return UNKNOWN
    redacted = _SECRET_VALUE.sub(REDACTED, str(value))
    return _LOCAL_PATH.sub("<local path>", redacted)


def display_intent_summary(value: Any) -> str:
    """Show that input exists without copying user prose into the browser."""

    return "已记录输入" if display_text(value) != UNKNOWN else UNKNOWN


def display_status(value: Any) -> str:
    """Use the user-facing status spelling while preserving unknown values."""

    return display_text(value).replace("safe_stopped", "safe-stopped")


#: Run classes that cannot produce an effect, an approval or a reconcile by
#: definition, and the units that therefore do not apply to them.
#:
#: This is a narrower claim than "this run has none yet". A read-only run makes
#: no external change, so rendering ``unknown`` for approval would say "we
#: cannot tell whether one was granted" when the truth is that none can exist.
#: The distinction matters: ``unknown`` is a reason to investigate.
_EFFECT_FREE_TASK_TYPES = ("local_read_only_run",)

_EFFECT_FAMILY = ("task-detail.effect", "task-detail.approval", "task-detail.reconcile")


def _not_applicable_units(task_type: Any) -> Dict[str, str]:
    """Units that do not apply to this run class, each with its reason.

    An empty mapping is the default. A run class this function does not
    recognise is never excused: an unrecognised class might well produce
    effects, and silently excusing it would hide a real gap.
    """
    if str(task_type) not in _EFFECT_FREE_TASK_TYPES:
        return {}
    reason = "只读运行按定义不产生副作用，无 effect/approval/reconcile"
    return {unit: reason for unit in _EFFECT_FAMILY}


def _project_execution_identity(
    run: Mapping[str, Any], results: List[Mapping[str, Any]]
) -> Dict[str, str]:
    """Project the correlation fields needed to interpret a task result.

    Worker results carry the identity chain in their result value, while a
    child run carries the same facts in metadata.  The view accepts either
    owner-backed location but never treats a partial chain as complete.
    """

    metadata = run.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    identity_sources = [metadata]
    provider_sources = []
    if isinstance(metadata.get("identity"), Mapping):
        identity_sources.insert(0, metadata["identity"])
    if isinstance(metadata.get("provider_identity"), Mapping):
        provider_sources.append(metadata["provider_identity"])
    for result in reversed(results):
        if not isinstance(result, Mapping) or not isinstance(result.get("value"), Mapping):
            continue
        value = result["value"]
        if isinstance(value.get("identity"), Mapping):
            identity_sources.insert(0, value["identity"])
        if isinstance(value.get("provider_identity"), Mapping):
            provider_sources.insert(0, value["provider_identity"])

    def first_text(sources: List[Mapping[str, Any]], field: str) -> str:
        for source in sources:
            value = source.get(field)
            if value not in (None, ""):
                return display_text(value)
        return UNKNOWN

    identity = {
        "run_id": display_text(run.get("run_id")),
        **{
            field: first_text(identity_sources, field)
            for field in (
                "parent_run_id",
                "child_run_id",
                "attempt_id",
                "dsh_session_id",
                "dsh_turn_id",
                "worker_run_id",
                "codex_thread_id",
                "codex_turn_id",
                "event_id",
                "artifact_id",
            )
        },
        **{
            field: first_text(provider_sources, field)
            for field in ("provider", "model", "endpoint", "transport")
        },
    }
    if run.get("task_type") in _EFFECT_FREE_TASK_TYPES:
        identity["status"] = "known" if identity["run_id"] != UNKNOWN else UNKNOWN
    else:
        required = (
            "parent_run_id",
            "child_run_id",
            "attempt_id",
            "provider",
            "model",
            "endpoint",
            "transport",
        )
        identity["status"] = "known" if all(identity[field] != UNKNOWN for field in required) else UNKNOWN
    return identity


def _project_session_references(identity: Mapping[str, str]) -> Dict[str, str]:
    """DSH-aligned read-only session-reference surface (dsh-web ``/session-references`` style).

    dsh-web exposes a session's reference identity -- its session/turn id and the
    parent/child linkage that ties it into the run tree -- as a named, read-only
    surface. ZWorkbench reuses that *idea* (ADR 0007), not its runtime: this
    surface is derived solely from the identity the facade already projected, so
    it adds no owner field, no method call, and no runtime dependency. Values are
    redacted and unknown-annotated upstream; a session reference is "known" only
    when both the DSH session and turn id resolved.
    """

    session_id = identity.get("dsh_session_id", UNKNOWN)
    turn_id = identity.get("dsh_turn_id", UNKNOWN)
    return {
        "dsh_session_id": session_id,
        "dsh_turn_id": turn_id,
        "parent_run_id": identity.get("parent_run_id", UNKNOWN),
        "child_run_id": identity.get("child_run_id", UNKNOWN),
        "provider": identity.get("provider", UNKNOWN),
        "model": identity.get("model", UNKNOWN),
        "status": "known" if session_id != UNKNOWN and turn_id != UNKNOWN else UNKNOWN,
        "source": "CompositionOwner",
    }


def _runs(owner: Any) -> List[Mapping[str, Any]]:
    return list(owner.snapshot()["runs"])


def _project_artifacts(snapshot: Mapping[str, Any], run_id: Any) -> Any:
    """Project only the stable artifact metadata the home surface needs."""

    artifacts = []
    for result in snapshot.get("results", ()):
        if not isinstance(result, Mapping) or result.get("run_id") != run_id:
            continue
        if result.get("kind") != "artifact" or not isinstance(result.get("value"), Mapping):
            continue
        value = result["value"]
        item = {
            "title": display_text(value.get("title") or value.get("name") or result.get("source_id", UNKNOWN)),
            "source": "CompositionOwner",
        }
        for field in ("path", "digest"):
            if field in value:
                item[field] = display_text(value[field])
        if isinstance(value.get("bytes"), int) and value["bytes"] >= 0:
            item["bytes"] = value["bytes"]
        artifacts.append(item)
    return artifacts or UNKNOWN


def _project_evidence(snapshot: Mapping[str, Any], run_id: Any) -> Any:
    """Expose evidence identities without carrying event payloads outward."""

    evidence = []
    for event in snapshot.get("events", ()):
        if not isinstance(event, Mapping) or event.get("run_id") != run_id:
            continue
        evidence.append(
            {
                "title": display_text(event.get("type", UNKNOWN)),
                "description": "Owner event",
                "identity": display_text(event.get("event_id", UNKNOWN)),
                "source": "CompositionOwner",
            }
        )
    for replay in snapshot.get("replays", ()):
        if not isinstance(replay, Mapping) or replay.get("run_id") != run_id:
            continue
        evidence.append(
            {
                "title": display_text(replay.get("mode", UNKNOWN)),
                "description": "event digest: " + display_text(replay.get("source_event_digest", UNKNOWN)),
                "identity": display_text(replay.get("replay_id", UNKNOWN)),
                "source": "CompositionOwner",
            }
        )
    return evidence or UNKNOWN


def _project_evidence_timeline(snapshot: Mapping[str, Any], run_id: Any) -> Any:
    """Chronological evidence timeline for the current run, read-only.

    Each node links to the recorded view's read-only route; no node resumes a
    session or reaches back into the owner. An absent run yields ``UNKNOWN``.
    """

    if not run_id:
        return UNKNOWN
    nodes = []
    for event in snapshot.get("events", ()):
        if not isinstance(event, Mapping) or event.get("run_id") != run_id:
            continue
        nodes.append(
            {
                "type": display_text(event.get("type", UNKNOWN)),
                "event_id": display_text(event.get("event_id", UNKNOWN)),
                "created_at": display_text(event.get("created_at", UNKNOWN)),
                "href": "/record-view?run_id=" + display_text(run_id),
                "source": "CompositionOwner",
            }
        )
    if not nodes:
        return UNKNOWN
    nodes.sort(key=lambda n: n["created_at"])
    return nodes


def _project_owner_records(snapshot: Mapping[str, Any]) -> Any:
    """Owner-backed record list for the run rail, read-only projection only."""

    records = [
        {
            "run_id": display_text(run.get("run_id")),
            "status": display_status(run.get("status", UNKNOWN)),
            "updated_at": display_text(run.get("updated_at", UNKNOWN)),
            "source": "CompositionOwner",
        }
        for run in snapshot.get("runs", ())
        if isinstance(run, Mapping)
    ]
    return records or UNKNOWN


def _project_preflight(value: Any) -> Dict[str, Any]:
    """Keep the admission explanation readable and limited to stable fields."""

    if not isinstance(value, Mapping):
        return {
            "status": UNKNOWN,
            "mode": UNKNOWN,
            "config_digest": UNKNOWN,
            "allowed": UNKNOWN,
            "checks": {},
            "violations": [],
            "source": "preflight not recorded",
        }
    checks = value.get("checks")
    checks = checks if isinstance(checks, Mapping) else {}
    checks = {
        display_text(key): item
        for key, item in checks.items()
        if isinstance(item, bool)
    }
    violations = value.get("violations")
    violations = [
        {
            "code": display_text(item.get("code", UNKNOWN)),
            "message": display_text(item.get("message", UNKNOWN)),
        }
        for item in (violations if isinstance(violations, list) else ())
        if isinstance(item, Mapping)
    ]
    allowed = value.get("allowed", UNKNOWN)
    if not isinstance(allowed, bool):
        allowed = UNKNOWN
    return {
        "status": display_text(value.get("status", UNKNOWN)),
        "mode": display_text(value.get("mode", UNKNOWN)),
        "config_digest": display_text(value.get("config_digest", UNKNOWN)),
        "allowed": allowed,
        "checks": checks,
        "violations": violations,
        "source": "Owner / recorded preflight",
    }


def _project_conversation(snapshot: Mapping[str, Any]) -> Any:
    """Project the owner's runs into a read-only conversation stream.

    Each message mirrors one recorded run: a role, its run identity, the status
    and time, the recorded intent, and -- when the run carried a plan -- a
    plan-card whose step states come straight from the owner-backed projection.
    No message is synthesised: an owner with no runs yields ``UNKNOWN`` and the
    view degrades to an explicit empty state.
    """
    messages = []
    for run in snapshot.get("runs") or ():
        if not isinstance(run, Mapping):
            continue
        run_id = run.get("run_id")
        metadata = run.get("metadata") or {}
        metadata = metadata if isinstance(metadata, Mapping) else {}
        input_value = run.get("input") or {}
        input_value = input_value if isinstance(input_value, Mapping) else {}
        plan = metadata.get("plan")
        if isinstance(plan, list):
            plan_proj: Any = {
                "steps": [
                    {
                        "title": display_text(step.get("title", UNKNOWN)),
                        "status": display_text(step.get("status", UNKNOWN)),
                        **(
                            {"description": display_text(step["description"])}
                            if isinstance(step, Mapping) and "description" in step
                            else {}
                        ),
                    }
                    for step in plan
                    if isinstance(step, Mapping)
                ]
            }
        else:
            plan_proj = UNKNOWN
        messages.append(
            {
                "role": "agent",
                "avatar_label": "A",
                "run_id": display_text(run_id),
                "status": display_status(run.get("status", UNKNOWN)),
                "updated_at": display_text(run.get("updated_at", UNKNOWN)),
                "title": display_text(run.get("task_type") or run_id),
                "intent": display_intent_summary(input_value.get("prompt", UNKNOWN)),
                "plan": plan_proj,
                "source": "CompositionOwner",
            }
        )
    return messages or UNKNOWN


def _project_variant(raw: Any) -> Dict[str, Any]:
    """Project the F19 debug variant selection into a safe, read-only shape.

    The value comes from a client-supplied ``?variant=`` query param and is
    therefore untrusted. Only the whitelisted members of ``HOME_VARIANT_CATALOG``
    are accepted; an absent or out-of-range value falls back to
    ``HOME_VARIANT_DEFAULT`` and is flagged ``valid: False``. The raw (untrusted)
    input is never echoed into a value the template interpolates without going
    through :func:`display_text`, so a stray ``?variant=<script>`` cannot inject.
    """
    raw_str = "" if raw is None else str(raw).strip()
    normalized = raw_str.upper()
    if normalized in HOME_VARIANT_CATALOG:
        return {
            "selected": normalized,
            "selected_raw": "",
            "valid": True,
            "options": [{"id": v, "active": v == normalized} for v in HOME_VARIANT_CATALOG],
            "source": "query param ?variant",
        }
    return {
        "selected": HOME_VARIANT_DEFAULT,
        "selected_raw": display_text(raw_str) if raw_str else "",
        "valid": False,
        "options": [{"id": v, "active": False} for v in HOME_VARIANT_CATALOG],
        "source": "query param ?variant" if raw_str else "source unknown",
    }


def _project_canvas_layout(snapshot: Mapping[str, Any], latest: Optional[Mapping[str, Any]], run_id: Any) -> Dict[str, Any]:
    """F8 (1-3-1) — B 命令画布只读投影（canvas-layout）。

    Pure read-only projection of existing owner state: the command path is the
    chain of claimed/recorded effects (operation -> resource -> status), the
    decision notes are the approvals (pending/decided with action/resource/
    reason), the artifact panel is the recorded results, and the run-rail is the
    latest run. No new owner API, no write.
    """

    effects = [e for e in snapshot.get("effects", ()) if isinstance(e, Mapping)]
    approvals = [a for a in snapshot.get("approvals", ()) if isinstance(a, Mapping)]
    results = [r for r in snapshot.get("results", ()) if isinstance(r, Mapping)]

    command_path = [
        {
            "effect_id": display_text(e.get("effect_id")),
            "operation_id": display_text(e.get("operation_id")),
            "resource": display_text(e.get("resource")),
            "kind": display_text(e.get("kind")),
            "status": display_status(e.get("status")),
            "run_id": display_text(e.get("run_id")),
            "source": "CompositionOwner",
        }
        for e in effects
    ]
    decisions = [
        {
            "approval_id": display_text(a.get("approval_id")),
            "operation_id": display_text(a.get("operation_id")),
            "action": display_text(a.get("action")),
            "resource": display_text(a.get("resource")),
            "reason": display_text(a.get("reason")),
            "status": display_status(a.get("status")),
            "source": "CompositionOwner",
        }
        for a in approvals
    ]
    artifacts = [
        {
            "result_id": display_text(r.get("result_id")),
            "kind": display_text(r.get("kind")),
            "value": display_text(r.get("value")),
            "run_id": display_text(r.get("run_id")),
            "source_id": display_text(r.get("source_id")),
            "source": "CompositionOwner",
        }
        for r in results
    ]
    run_rail = {
        "run_id": display_text(run_id) if run_id is not None else UNKNOWN,
        "status": display_status(latest["status"]) if latest else UNKNOWN,
        "source": "CompositionOwner" if latest else "source unknown",
    }
    return {
        "kind": "canvas",
        "command_path": command_path or UNKNOWN,
        "decisions": decisions or UNKNOWN,
        "artifacts": artifacts or UNKNOWN,
        "run_rail": run_rail,
        "source": "CompositionOwner" if (effects or approvals or results) else "source unknown",
    }


def _project_journal_layout(snapshot: Mapping[str, Any], latest: Optional[Mapping[str, Any]], run_id: Any) -> Dict[str, Any]:
    """F9 (1-3-2) — C 项目日记只读投影（journal-layout）。

    Pure read-only projection: the index is the runs list, the reading pane is the
    latest run's recorded input/plan/metadata, and the evidence table is the
    events/replays/results joined by run. No new owner API, no write.
    """

    runs = [r for r in snapshot.get("runs", ()) if isinstance(r, Mapping)]
    events = [e for e in snapshot.get("events", ()) if isinstance(e, Mapping)]
    replays = [rp for rp in snapshot.get("replays", ()) if isinstance(rp, Mapping)]
    results = [r for r in snapshot.get("results", ()) if isinstance(r, Mapping)]

    index = [
        {
            "run_id": display_text(r.get("run_id")),
            "status": display_status(r.get("status")),
            "updated_at": display_text(r.get("updated_at")),
            "source": "CompositionOwner",
        }
        for r in runs
    ]
    input_value = latest.get("input") if isinstance(latest, Mapping) and isinstance(latest.get("input"), Mapping) else {}
    metadata = latest.get("metadata") if isinstance(latest, Mapping) and isinstance(latest.get("metadata"), Mapping) else {}
    plan = metadata.get("plan", UNKNOWN)
    if isinstance(plan, list):
        plan = {
            "steps": [
                {
                    "title": display_text(s.get("title", UNKNOWN)),
                    "status": display_text(s.get("status", UNKNOWN)),
                }
                for s in plan
            ]
        } if plan else UNKNOWN
    reading = {
        "run_id": display_text(run_id) if run_id is not None else UNKNOWN,
        "prompt": display_text(input_value.get("prompt", UNKNOWN)),
        "plan": plan,
        "workspace": display_text(metadata.get("workspace", UNKNOWN)),
        "workspace_mode": display_text(metadata.get("workspace_mode", UNKNOWN)),
        "source": "CompositionOwner" if latest else "source unknown",
    }
    evidence_table = (
        [
            {
                "kind": "event",
                "id": display_text(e.get("event_id")),
                "type": display_text(e.get("type")),
                "run_id": display_text(e.get("run_id")),
                "source": "CompositionOwner",
            }
            for e in events
        ]
        + [
            {
                "kind": "replay",
                "id": display_text(rp.get("replay_id")),
                "type": display_text(rp.get("mode")),
                "run_id": display_text(rp.get("run_id")),
                "source": "CompositionOwner",
            }
            for rp in replays
        ]
        + [
            {
                "kind": "result",
                "id": display_text(r.get("result_id")),
                "type": display_text(r.get("kind")),
                "run_id": display_text(r.get("run_id")),
                "source": "CompositionOwner",
            }
            for r in results
        ]
    )
    return {
        "kind": "journal",
        "index": index or UNKNOWN,
        "reading": reading,
        "evidence_table": evidence_table or UNKNOWN,
        "source": "CompositionOwner" if (runs or events or replays or results) else "source unknown",
    }


def home_view_model(owner: Any, *, variant: Any = None) -> Dict[str, Any]:
    """Project the owner's runs into the home surface's presentation model.

    Only the run identity and status are shown. The recorded input is not: it
    is user prose, and the home surface has no reason to display it.
    """
    snapshot = owner.snapshot()
    runs = list(snapshot.get("runs") or ())
    latest = runs[-1] if runs else None
    metadata = latest.get("metadata") if latest else None
    metadata = metadata if isinstance(metadata, Mapping) else {}
    input_value = latest.get("input") if latest else None
    input_value = input_value if isinstance(input_value, Mapping) else {}
    workspace_name = display_text(metadata.get("workspace", UNKNOWN))
    workspace_mode = display_text(metadata.get("workspace_mode", UNKNOWN))
    workspace_known = bool(workspace_name.strip()) and bool(workspace_mode.strip()) and all(
        value != UNKNOWN for value in (workspace_name, workspace_mode)
    )
    plan = metadata.get("plan", UNKNOWN)
    if isinstance(plan, list):
        plan = {
            "steps": [
                {
                    "title": display_text(step.get("title", UNKNOWN)),
                    "status": display_text(step.get("status", UNKNOWN)),
                    **(
                        {"description": display_text(step["description"])}
                        if "description" in step
                        else {}
                    ),
                }
                for step in plan
                if isinstance(step, Mapping)
            ]
        }
    elif plan != UNKNOWN:
        plan = UNKNOWN
    replay = None
    if latest:
        replay_rows = [
            item
            for item in snapshot.get("replays", ())
            if isinstance(item, Mapping) and item.get("run_id") == latest.get("run_id")
        ]
        replay = replay_rows[-1] if replay_rows else None
    provider_identity = replay.get("provider_identity") if isinstance(replay, Mapping) else None
    provider_identity = provider_identity if isinstance(provider_identity, Mapping) else {}

    # F7 inspector facts — read-only projection only. Real-time values that
    # would require a live runtime query (or dynamic projection) are deliberately
    # left to the 1-2-3 product gate; here an absent field reads ``unknown``.
    run_id = latest.get("run_id") if latest else None
    approval_rows = [
        item for item in snapshot.get("approvals", ())
        if isinstance(item, Mapping) and (run_id is None or item.get("run_id") == run_id)
    ]
    latest_approval = approval_rows[-1] if approval_rows else None
    approval_status = (
        display_status(latest_approval.get("status")) if latest_approval else UNKNOWN
    )
    effect_rows = [
        item for item in snapshot.get("effects", ())
        if isinstance(item, Mapping) and (run_id is None or item.get("run_id") == run_id)
    ]
    latest_effect = effect_rows[-1] if effect_rows else None
    effect_status = (
        display_status(latest_effect.get("status")) if latest_effect else UNKNOWN
    )
    worker = " · ".join(
        piece for piece in (provider_identity.get("provider"), provider_identity.get("model"))
        if piece not in (None, "", UNKNOWN)
    )
    worker = worker if worker else UNKNOWN
    evidence_links = []
    if latest and run_id:
        for event in snapshot.get("events", ()):
            if isinstance(event, Mapping) and event.get("run_id") == run_id:
                evidence_links.append({
                    "title": display_text(event.get("type", UNKNOWN)),
                    "identity": display_text(event.get("event_id", UNKNOWN)),
                    "event_id": display_text(event.get("event_id", UNKNOWN)),
                    "source": "CompositionOwner",
                    "href": "/record-view?run_id=" + display_text(run_id),
                })
        for replay_row in snapshot.get("replays", ()):
            if isinstance(replay_row, Mapping) and replay_row.get("run_id") == run_id:
                evidence_links.append({
                    "title": display_text(replay_row.get("mode", UNKNOWN)),
                    "identity": display_text(replay_row.get("replay_id", UNKNOWN)),
                    "event_id": display_text(replay_row.get("replay_id", UNKNOWN)),
                    "source": "CompositionOwner",
                    "href": "/record-view?run_id=" + display_text(run_id),
                })
    evidence_links = evidence_links or UNKNOWN
    evidence_timeline = _project_evidence_timeline(snapshot, run_id) if run_id else UNKNOWN
    owner_records = _project_owner_records(snapshot) if runs else UNKNOWN

    # F10 run-rail — render shell. ``can_run`` defaults to False here; the host
    # injects ``can_run = True`` for /home only when a command facade was wired
    # at startup (F10/1-2-4). A read-only host (CLI ui-host) keeps it False, so
    # the button degrades to a disabled placeholder rather than a broken trigger.
    run_rail = {
        "status": display_status(latest["status"]) if latest else UNKNOWN,
        "run_id": display_text(run_id) if run_id is not None else UNKNOWN,
        "can_run": False,
        "workspace": workspace_name,
        "parent_child": display_text(metadata.get("parent_child", UNKNOWN)),
        "worker": worker,
        "owner_records": owner_records,
        "evidence_timeline": evidence_timeline,
        "source": "CompositionOwner" if latest else "source unknown",
    }

    # F11 scenario-state — render shell only. The "approval" derivation
    # (safe-stop / approval judgment) stays behind the 1-2 product gate (F13);
    # here we read only existing read-only signals: no recorded run -> empty, a
    # safe-stopped latest run -> stopped, otherwise -> planning. An absent field
    # reads ``unknown`` and the real state machine wiring is not exercised.
    scenario_latest_status = display_status(latest["status"]) if latest else UNKNOWN
    scenario_state_token = (
        "stopped" if scenario_latest_status == "safe-stopped"
        else "planning" if (latest or runs)
        else "empty"
    )
    scenario_source = "CompositionOwner" if (latest or runs) else "source unknown"
    scenario_state = {
        "state": scenario_state_token,
        "source": scenario_source,
    }

    # F13 (1-2-5) — safe-stop / reconcile banner projection.
    # The banner activates when the scenario is stopped OR when the owner reports
    # an unresolved identity reference (identity unresolved). The reconcile CTA is
    # enabled only when a concrete identity violation was detected; the structured
    # findings name the exact broken reference so a human can act on it.
    identity_violations = []
    if run_id is not None:
        try:
            identity_violations = list(owner.detect_identity_violations(run_id))
        except Exception:
            identity_violations = []
    has_identity_violation = bool(identity_violations)

    safe_stop_active = scenario_state_token == "stopped" or has_identity_violation
    safe_stop = {
        "active": safe_stop_active,
        "tone": "stopped" if safe_stop_active else "neutral",
        "reason": "identity_unresolved" if has_identity_violation else None,
        "message_zh": (
            "检测到身份越界：{n} 处身份引用无法解析（identity unresolved）。恢复需 reconcile。".format(n=len(identity_violations))
            if has_identity_violation
            else ("场景已安全停止（safe-stop）。恢复需 reconcile；真实越界 / 身份未解析（identity unresolved）判定属 product gate（F13），本轮仅渲染请求入口。"
                  if safe_stop_active
                  else "场景未检测到身份越界。")
        ),
        "reconcile_label_zh": "请求 reconcile",
        "reconcile_disabled": not has_identity_violation,
        "violations": identity_violations,
        "source": "CompositionOwner" if (safe_stop_active or has_identity_violation) else "source unknown",
    }

    # 1-3 — variant content branch (F8 canvas / F9 journal). Read-only projection
    # of existing owner state; only the whitelisted B/C variants produce a layout,
    # everything else (A / default) stays None so render_home keeps the A-session
    # main content. The F19 switcher already drives this via ?variant=.
    variant_proj = _project_variant(variant)
    selected = variant_proj.get("selected")
    if selected == "B":
        variant_layout = _project_canvas_layout(snapshot, latest, run_id)
    elif selected == "C":
        variant_layout = _project_journal_layout(snapshot, latest, run_id)
    else:
        variant_layout = None

    return {
        "workspace": {
            "name": workspace_name,
            "mode": workspace_mode,
            "status": "implemented" if workspace_known else UNKNOWN,
            "source": "CompositionOwner" if workspace_known else "source unknown",
        },
        "records": [
            {
                "title": display_text(run["run_id"]),
                "run_id": display_text(run["run_id"]),
                "status": display_status(run.get("status", UNKNOWN)),
                "updated_at": display_text(run.get("updated_at", UNKNOWN)),
                "source": "CompositionOwner",
            }
            for run in runs
        ],
        "run_facts": {
            "status": display_status(latest["status"]) if latest else UNKNOWN,
            "run_id": display_text(run_id) if run_id is not None else UNKNOWN,
            "parent_child": display_text(metadata.get("parent_child", UNKNOWN)),
            "mode": workspace_mode,
            "workspace": display_text(metadata.get("workspace", UNKNOWN)),
            "worker": worker,
            "approval": approval_status,
            "effect": effect_status,
            "provider": display_text(provider_identity.get("provider", UNKNOWN)),
            "model": display_text(provider_identity.get("model", UNKNOWN)),
            "event_digest": display_text(replay.get("source_event_digest", UNKNOWN)) if replay else UNKNOWN,
            "environment_digest": display_text(replay.get("environment_digest", UNKNOWN)) if replay else UNKNOWN,
            "evidence": display_text(replay.get("mode", UNKNOWN)) if replay else UNKNOWN,
            "evidence_links": evidence_links,
            "source": "CompositionOwner" if latest else "source unknown",
        },
        "run_rail": run_rail,
        # F6/1-2-1 — input composer projection (render shell + send capability
        # flag). ``can_send`` defaults to False here; the host injects
        # ``can_send = True`` for /home only when a command facade was wired at
        # startup (same condition as F10 ``can_run``). A read-only host keeps it
        # False, so the composer degrades to a disabled input rather than a
        # broken trigger. The composer is a UI control, not owner-backed data,
        # so its source is the view model, not CompositionOwner.
        "composer": {
            "can_send": False,
            "source": "view model",
        },
        # F12/1-2-2 — approval-execution console projection (read-only listing).
        # The human-actable verbs (approve/deny/record receipt) are write actions
        # handled by the narrow approval command facade; the console lists only
        # what a human can act on, with no owner-backed write here.
        # ``can_decide`` defaults to False; the host flips it for /home only when
        # an approval command facade was wired at startup (parallel to F10
        # ``can_run`` / F6 ``can_send``). A read-only host keeps it False, so the
        # console degrades to disabled controls rather than broken triggers.
        "approval_console": {
            "can_decide": False,
            "pending_approvals": [
                {
                    "approval_id": display_text(item.get("approval_id")),
                    "operation_id": display_text(item.get("operation_id")),
                    "action": display_text(item.get("action")),
                    "resource": display_text(item.get("resource")),
                    "reason": display_text(item.get("reason")),
                    "created_at": display_text(item.get("created_at")),
                }
                for item in snapshot.get("approvals", ())
                if isinstance(item, Mapping) and item.get("status") == "pending"
            ],
            "claimed_effects": [
                {
                    "effect_id": display_text(item.get("effect_id")),
                    "operation_id": display_text(item.get("operation_id")),
                    "action": display_text(item.get("action")),
                    "resource": display_text(item.get("resource")),
                    "status": display_status(item.get("status")),
                    "attempt": item.get("attempt", UNKNOWN),
                }
                for item in snapshot.get("effects", ())
                if isinstance(item, Mapping) and item.get("status") == "claimed"
            ],
            "source": "CompositionOwner"
            if (
                any(
                    item.get("status") == "pending"
                    for item in snapshot.get("approvals", ())
                    if isinstance(item, Mapping)
                )
                or any(
                    item.get("status") == "claimed"
                    for item in snapshot.get("effects", ())
                    if isinstance(item, Mapping)
                )
            )
            else "source unknown",
        },
        "scenario_state": scenario_state,
        "safe_stop": safe_stop,
        "intent": {
            "title": display_text(latest.get("task_type", UNKNOWN)) if latest else UNKNOWN,
            "summary": display_intent_summary(input_value.get("prompt", UNKNOWN)),
            "status": display_status(latest.get("status", UNKNOWN)) if latest else UNKNOWN,
            "source": "Owner / recorded input" if latest else "source unknown",
        },
        "plan": plan,
        "artifacts": _project_artifacts(snapshot, latest.get("run_id")) if latest else UNKNOWN,
        "evidence": _project_evidence(snapshot, latest.get("run_id")) if latest else UNKNOWN,
        "preflight_result": _project_preflight(metadata.get("preflight")),
        "conversation": _project_conversation(snapshot),
        # F15 r2 — r2-ui-reference-skills 协同可视化（read-only projection）.
        # Declared snapshot only; live profile_status.py / runtime_status.py
        # invocation belongs to the 1-2 product gate.
        "ui_reference_collab": ui_reference_collab_view_model(),
        # F19 — three-variant debug switcher (read-only projection of ?variant=).
        "variant": _project_variant(variant),
        # 1-3 — variant content branch (F8 canvas / F9 journal). ``None`` for the
        # A-session / default variant so render_home keeps the A-session content.
        "variant_layout": variant_layout,
    }


def task_detail_view_model(owner: Any, run_id: str) -> Dict[str, Any]:
    """Project one run into the task-detail surface's presentation model.

    A run the owner does not hold yields a model of ``unknown`` values rather
    than an error: an absent run is a state the surface can display.
    """
    try:
        run = owner.get_run(run_id)
    except Exception:
        run = None

    if run is None:
        absent = {key: UNKNOWN for key in (
            "intent", "denial", "identity", "timeline", "result",
            "error", "effect", "approval", "reconcile", "replay_mode",
        )}
        absent["admission"] = {"status": UNKNOWN}
        # An absent run has no class, so nothing can be excused: unknown is the
        # honest answer for every unit.
        absent["not_applicable"] = {}
        return absent

    metadata = run.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    input_value = run.get("input")
    input_value = input_value if isinstance(input_value, Mapping) else {}
    preflight = _project_preflight(metadata.get("preflight"))
    denied = preflight["status"] == "deny" or preflight["allowed"] is False
    denial = (
        {
            "violations": preflight["violations"],
            "source": preflight["source"],
        }
        if denied
        else UNKNOWN
    )
    results = run.get("results") or ()
    effects = run.get("effects") or ()
    owner_snapshot = owner.snapshot()
    approval_rows = [
        item
        for item in owner_snapshot.get("approvals", ())
        if isinstance(item, Mapping) and item.get("run_id") == run_id
    ]
    latest_approval = approval_rows[-1] if approval_rows else None
    approval = (
        {
            "status": display_status(latest_approval.get("status")),
            "operation_id": display_text(latest_approval.get("operation_id")),
            "action": display_text(latest_approval.get("action")),
            "resource": display_text(latest_approval.get("resource")),
            "idempotency_key": display_text(latest_approval.get("idempotency_key")),
            "reason": display_text(latest_approval.get("reason")),
            "decision_reason": display_text(latest_approval.get("decision_reason")),
            "source": "CompositionOwner",
        }
        if latest_approval
        else UNKNOWN
    )
    replay_rows = [
        item
        for item in owner_snapshot.get("replays", ())
        if isinstance(item, Mapping) and item.get("run_id") == run_id
    ]
    latest_replay = replay_rows[-1] if replay_rows else None
    replay_provider = latest_replay.get("provider_identity") if latest_replay else None
    replay_provider = replay_provider if isinstance(replay_provider, Mapping) else {}
    replay = (
        {
            "replay_id": display_text(latest_replay.get("replay_id")),
            "mode": display_text(latest_replay.get("mode")),
            "source_event_digest": display_text(latest_replay.get("source_event_digest")),
            "environment_digest": display_text(latest_replay.get("environment_digest")),
            "provider": display_text(replay_provider.get("provider")),
            "model": display_text(replay_provider.get("model")),
            "source": "CompositionOwner",
        }
        if latest_replay
        else UNKNOWN
    )
    identity = _project_execution_identity(run, list(results))
    latest_effect = effects[-1] if effects and isinstance(effects[-1], Mapping) else None
    latest_result = results[-1] if results and isinstance(results[-1], Mapping) else None
    latest_result_kind = display_text(latest_result.get("kind")) if latest_result else UNKNOWN
    error_value = latest_result.get("value") if latest_result else None
    if latest_result_kind == "error":
        if isinstance(error_value, Mapping):
            error = {
                "code": display_text(error_value.get("code")),
                "message": display_text(error_value.get("message")),
                "source": "CompositionOwner",
            }
        else:
            error = {
                "code": UNKNOWN,
                "message": display_text(error_value),
                "source": "CompositionOwner",
            }
    else:
        error = UNKNOWN
    effect_status = display_status(latest_effect.get("status")) if latest_effect else UNKNOWN
    unresolved_effect = effect_status in {"claimed", "uncertain", "retryable", "unknown"}
    interpretable_result = (
        identity["status"] == "known"
        and not unresolved_effect
        and latest_result_kind != "error"
    )
    effect = (
        {
            "status": effect_status,
            "operation_id": display_text(latest_effect.get("operation_id")),
            "action": display_text(latest_effect.get("action")),
            "resource": display_text(latest_effect.get("resource")),
            "idempotency_key": display_text(latest_effect.get("idempotency_key")),
            "attempt": latest_effect.get("attempt", UNKNOWN),
            "source": "CompositionOwner",
        }
        if latest_effect
        else UNKNOWN
    )
    if latest_effect and unresolved_effect:
        reconcile_status = "unknown" if effect_status == "unknown" else "pending"
        reconcile = {
            "status": reconcile_status,
            "effect_id": display_text(latest_effect.get("effect_id")),
            "source": "Owner / effect state",
        }
    else:
        reconcile = UNKNOWN
    timeline_events = [
        {
            "type": display_text(event.get("type")),
            "event_id": display_text(event.get("event_id")),
            "created_at": display_text(event.get("created_at")),
            "source": "CompositionOwner",
        }
        for event in owner.events(run_id)
        if isinstance(event, Mapping)
    ]
    timeline = {
        "updated_at": display_text(run.get("updated_at")),
        "events": timeline_events,
        "source": "CompositionOwner",
    }
    return {
        "intent": {
            "task_type": display_text(run.get("task_type")),
            "summary": display_intent_summary(input_value.get("prompt")),
            "source": "Owner / recorded input",
        },
        "admission": {
            "status": "denied" if denied else display_status(run.get("status")),
            "source": preflight["source"] if denied else "Owner / run status",
        },
        "denial": denial,
        "identity": identity,
        "session_references": _project_session_references(identity),
        "timeline": timeline,
        "result": latest_result_kind if latest_result and interpretable_result else UNKNOWN,
        "error": error,
        "effect": effect,
        "approval": approval,
        "reconcile": reconcile,
        "replay_mode": "recorded_view",
        "replay": replay,
        "not_applicable": _not_applicable_units(run.get("task_type")),
    }


def record_view_model(
    owner: Any, run_id: Optional[str] = None, *, filter_text: Optional[str] = None
) -> Dict[str, Any]:
    """Project recorded events into the record surface's presentation model.

    This is a recorded view. The events are read as stored; nothing here
    resumes a session or contacts a provider.
    """
    all_events = owner.events(run_id)
    query = display_text(filter_text) if filter_text else ""
    events = [
        event
        for event in all_events
        if not query or query.casefold() in display_text(event.get("type")).casefold()
    ]
    snapshot = owner.snapshot()
    event_rows = [
        {
            "title": display_text(event.get("type")),
            "type": display_text(event.get("type")),
            "event_id": display_text(event.get("event_id")),
            "created_at": display_text(event.get("created_at")),
            "source": "CompositionOwner",
        }
        for event in events
        if isinstance(event, Mapping)
    ]
    result_rows = [
        item
        for item in snapshot.get("results", ())
        if isinstance(item, Mapping)
        and (run_id is None or item.get("run_id") == run_id)
        and item.get("kind") != "artifact"
    ]
    latest_result = result_rows[-1] if result_rows else None
    result_value = latest_result.get("value") if latest_result else None
    result = (
        {
            "result_id": display_text(latest_result.get("result_id")),
            "kind": display_text(latest_result.get("kind")),
            "status": display_text(result_value.get("status"))
            if isinstance(result_value, Mapping)
            else UNKNOWN,
            "source": "CompositionOwner",
        }
        if latest_result
        else UNKNOWN
    )
    artifact_metadata = _project_artifacts(snapshot, run_id) if run_id else UNKNOWN
    replay_rows = [
        item
        for item in snapshot.get("replays", ())
        if isinstance(item, Mapping)
        and (run_id is None or item.get("run_id") == run_id)
    ]
    latest_replay = replay_rows[-1] if replay_rows else None
    replay_provider = latest_replay.get("provider_identity") if latest_replay else None
    replay_provider = replay_provider if isinstance(replay_provider, Mapping) else {}
    replay_metadata = (
        {
            "replay_id": display_text(latest_replay.get("replay_id")),
            "mode": display_text(latest_replay.get("mode")),
            "source_event_digest": display_text(latest_replay.get("source_event_digest")),
            "environment_digest": display_text(latest_replay.get("environment_digest")),
            "provider": display_text(replay_provider.get("provider")),
            "model": display_text(replay_provider.get("model")),
            "source": "CompositionOwner",
        }
        if latest_replay
        else UNKNOWN
    )
    state = (
        "empty-events"
        if not all_events
        else "no-filter-results"
        if query and not event_rows
        else "ready"
    )
    run_options = [
        {
            "run_id": display_text(item.get("run_id")),
            "title": display_text(item.get("run_id")),
            "status": display_status(item.get("status")),
            "updated_at": display_text(item.get("updated_at")),
            "source": "CompositionOwner",
        }
        for item in snapshot.get("runs", ())
        if isinstance(item, Mapping)
    ]
    return {
        "picker": display_text(run_id) if run_id else UNKNOWN,
        "run_options": run_options,
        "state": state,
        "events": event_rows,
        "filter": {
            "query": query or UNKNOWN,
            "matched": len(event_rows),
            "total": len(all_events),
            "source": "CompositionOwner",
        },
        "detail": event_rows[-1]["type"] if event_rows else UNKNOWN,
        "artifact_metadata": artifact_metadata,
        "replay_metadata": replay_metadata,
        "result": result,
        "mode": "recorded_view",
    }


#: Route -> the projection that answers it. The host asks for a route and
#: receives a presentation model; it never learns that an owner exists.
def _latest_run_id(owner: Any) -> Optional[str]:
    runs = _runs(owner)
    return runs[-1].get("run_id") if runs else None


_ROUTES = {
    "/home": lambda owner: home_view_model(owner),
    "/record-view": lambda owner: record_view_model(owner, _latest_run_id(owner)),
}


def owner_view_source(owner: Any):
    """Adapt an owner into the view source the host expects.

    The host is handed a function of one route, not the owner, so serving a
    page cannot widen into owner access however the host later changes.
    """

    def resolve(route: str) -> Dict[str, Any]:
        if route in _ROUTES:
            return _ROUTES[route](owner)
        if route == "/task-detail":
            return task_detail_view_model(owner, _latest_run_id(owner) or "")
        return {}

    def resolve_query(route: str, query: str) -> Dict[str, Any]:
        """Resolve read-only route selection without giving the browser state."""

        params = parse_qs(query or "", keep_blank_values=True)
        if route == "/record-view":
            selected = params.get("run_id", [None])[0] or _latest_run_id(owner)
            filter_text = params.get("filter", [None])[0]
            return record_view_model(owner, selected, filter_text=filter_text)
        if route == "/task-detail":
            selected = params.get("run_id", [None])[0] or _latest_run_id(owner)
            return task_detail_view_model(owner, selected or "")
        if route == "/home":
            # F19 — pure client-side branch driven by the ?variant= query param.
            # No owner write, no runtime: the host projects the selection and the
            # page renders three query-param links. Out-of-range values are
            # rejected by home_view_model's projection, not here.
            variant = params.get("variant", [None])[0]
            return home_view_model(owner, variant=variant)
        return resolve(route)

    resolve.resolve_query = resolve_query  # type: ignore[attr-defined]

    return resolve
