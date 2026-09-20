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


def home_view_model(owner: Any) -> Dict[str, Any]:
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
            "run_id": display_text(latest["run_id"]) if latest else UNKNOWN,
            "parent_child": display_text(metadata.get("parent_child", UNKNOWN)),
            "workspace": display_text(metadata.get("workspace", UNKNOWN)),
            "provider": display_text(provider_identity.get("provider", UNKNOWN)),
            "model": display_text(provider_identity.get("model", UNKNOWN)),
            "event_digest": display_text(replay.get("source_event_digest", UNKNOWN)) if replay else UNKNOWN,
            "environment_digest": display_text(replay.get("environment_digest", UNKNOWN)) if replay else UNKNOWN,
            "evidence": display_text(replay.get("mode", UNKNOWN)) if replay else UNKNOWN,
            "source": "CompositionOwner" if latest else "source unknown",
        },
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
        return resolve(route)

    resolve.resolve_query = resolve_query  # type: ignore[attr-defined]

    return resolve
