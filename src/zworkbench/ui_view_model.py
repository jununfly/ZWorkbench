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

#: Credential shapes that may appear inside otherwise ordinary prose.
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
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
    return _SECRET_VALUE.sub(REDACTED, str(value))


def _runs(owner: Any) -> List[Mapping[str, Any]]:
    return list(owner.snapshot()["runs"])


def home_view_model(owner: Any) -> Dict[str, Any]:
    """Project the owner's runs into the home surface's presentation model.

    Only the run identity and status are shown. The recorded input is not: it
    is user prose, and the home surface has no reason to display it.
    """
    runs = _runs(owner)
    latest = runs[-1] if runs else None
    return {
        "workspace": UNKNOWN,
        "records": [{"title": display_text(run["run_id"])} for run in runs],
        "run_facts": {"status": display_text(latest["status"]) if latest else UNKNOWN},
        "intent": UNKNOWN,
        "plan": UNKNOWN,
        "artifacts": UNKNOWN,
        "evidence": UNKNOWN,
        "preflight_result": UNKNOWN,
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
        return {key: UNKNOWN for key in (
            "intent", "denial", "identity", "timeline", "result",
            "error", "effect", "approval", "reconcile", "replay_mode",
        )} | {"admission": {"status": UNKNOWN}}

    results = run.get("results") or ()
    effects = run.get("effects") or ()
    return {
        "intent": display_text(run.get("task_type")),
        "admission": {"status": display_text(run.get("status"))},
        "denial": UNKNOWN,
        "identity": display_text(run.get("run_id")),
        "timeline": display_text(run.get("updated_at")),
        "result": display_text(results[-1].get("kind")) if results else UNKNOWN,
        "error": UNKNOWN,
        "effect": display_text(effects[-1].get("status")) if effects else UNKNOWN,
        "approval": UNKNOWN,
        "reconcile": UNKNOWN,
        "replay_mode": "recorded_view",
    }


def record_view_model(owner: Any, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Project recorded events into the record surface's presentation model.

    This is a recorded view. The events are read as stored; nothing here
    resumes a session or contacts a provider.
    """
    events = owner.events(run_id)
    return {
        "picker": display_text(run_id) if run_id else UNKNOWN,
        "events": [{"title": display_text(event["type"])} for event in events],
        "filter": UNKNOWN,
        "detail": display_text(events[-1]["type"]) if events else UNKNOWN,
        "artifact_metadata": UNKNOWN,
        "replay_metadata": UNKNOWN,
        "result": UNKNOWN,
        "mode": "recorded_view",
    }


#: Route -> the projection that answers it. The host asks for a route and
#: receives a presentation model; it never learns that an owner exists.
_ROUTES = {
    "/home": lambda owner: home_view_model(owner),
    "/record-view": lambda owner: record_view_model(owner),
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
            runs = _runs(owner)
            return task_detail_view_model(owner, runs[-1]["run_id"] if runs else "")
        return {}

    return resolve
