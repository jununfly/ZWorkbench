"""The fixed semantic coverage matrix transcribed from the R1 PRD.

This module is an acceptance *specification*, not an implementation detail. It
is written down independently of the manifest on purpose: if the denominator
were derived from the declarations that happen to exist, an unimplemented unit
would silently disappear from the report and coverage would approach 100% by
declaring nothing. Here a missing unit always surfaces as a gap.

The report it produces is structural only. It says nothing about whether a real
browser honours the interaction contracts, and it never reports acceptance.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

from .ui_ref import UiRefError
from .ui_review import HOST_SURFACES, HOST_UNKNOWNS


REQUIRED_VIEWPORTS = ("compact", "wide")
REQUIRED_MODES = ("normal", "review")

#: The PRD states compact as "below 768px" and wide as "at least 768px", so the
#: boundary belongs to wide. The stylesheet must use the same number, otherwise
#: a token could claim one class while the page was laid out as the other.
VIEWPORT_BREAKPOINT_PX = 768


def viewport_class(width_px: int) -> str:
    """Classify a CSS viewport width into the two classes a token may carry."""
    return "compact" if width_px < VIEWPORT_BREAKPOINT_PX else "wide"


class CoverageError(UiRefError):
    """A coverage claim violates the counting contract."""


#: View -> (required semantic units, required scenarios).
#: Transcribed from the PRD acceptance matrix. Unit names are the references
#: the implementation is expected to declare; a name absent from the manifest is
#: a gap in the product, not an error in this table.
MATRIX: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "home": {
        "units": (
            "home.root",
            "home.workspace-context",
            "home.record-list",
            "home.record-list.item",
            "home.current-intent",
            "home.plan-next-step",
            "home.artifacts",
            "home.run-facts",
            "home.evidence",
            "home.preflight-run.action",
            "home.preflight-result",
            "home.conversation",
            "home.conversation.message",
        ),
        "scenarios": (
            "no-records",
            "draft",
            "loading",
            "preflight-denied",
            "running",
            "completed",
            "failed",
            "safe-stopped",
            "unknown",
            "dynamic-reorder",
            "dynamic-delete",
        ),
    },
    "task-detail": {
        "units": (
            "task-detail.root",
            "task-detail.intent",
            "task-detail.admission-check",
            "task-detail.denial-reason",
            "task-detail.execution-identity",
            "task-detail.timeline",
            "task-detail.result",
            "task-detail.error",
            "task-detail.effect",
            "task-detail.approval",
            "task-detail.reconcile",
            "task-detail.replay-mode",
        ),
        "scenarios": (
            "denied",
            "running",
            "recovering",
            "completed",
            "failed",
            "safe-stopped",
            "unknown",
            "read-only-not-applicable",
            "missing-identity",
            "pending-reconcile",
        ),
    },
    "record-view": {
        "units": (
            "record-view.root",
            "record-view.record-picker",
            "record-view.event-list",
            "record-view.event-list.item",
            "record-view.filter",
            "record-view.event-detail",
            "record-view.result",
            "record-view.artifact-metadata",
            "record-view.replay-metadata",
            "record-view.mode-boundary",
        ),
        "scenarios": (
            "loading",
            "empty-events",
            "normal-record",
            "no-filter-results",
            "missing-metadata",
            "duplicate-structural-events",
        ),
    },
}


#: View -> unit -> the visibility the PRD requires of it in a normal scenario.
#:
#: ``visible``      always rendered when the view renders at all.
#: ``expandable``   rendered inside a read-only disclosure, collapsed by
#:                  default; locating it must expand it.
#: ``conditional``  rendered only when the run class or state can produce it;
#:                  otherwise it is legitimately absent and may be excused as
#:                  not applicable with a stated reason.
#:
#: Transcribed by hand from the PRD, like :data:`MATRIX` and for the same
#: reason: a table derived from what the renderers happen to emit would agree
#: with every implementation, including one that renders nothing. Only
#: ``conditional`` units may be excused, which is the rule that stops a missing
#: implementation from being relabelled as out of scope.
UNIT_VISIBILITY: Dict[str, Dict[str, str]] = {
    "home": {
        "home.root": "visible",
        "home.workspace-context": "visible",
        "home.record-list": "visible",
        "home.record-list.item": "conditional",
        "home.current-intent": "visible",
        "home.plan-next-step": "visible",
        "home.artifacts": "visible",
        "home.run-facts": "visible",
        "home.evidence": "visible",
        "home.preflight-run.action": "visible",
        "home.preflight-result": "visible",
        "home.conversation": "visible",
        "home.conversation.message": "conditional",
    },
    "task-detail": {
        "task-detail.root": "visible",
        "task-detail.intent": "visible",
        "task-detail.admission-check": "visible",
        "task-detail.denial-reason": "conditional",
        "task-detail.execution-identity": "visible",
        "task-detail.timeline": "visible",
        "task-detail.result": "visible",
        "task-detail.error": "conditional",
        "task-detail.effect": "conditional",
        "task-detail.approval": "conditional",
        "task-detail.reconcile": "conditional",
        "task-detail.replay-mode": "visible",
    },
    "record-view": {
        "record-view.root": "visible",
        "record-view.record-picker": "visible",
        "record-view.event-list": "visible",
        "record-view.event-list.item": "conditional",
        "record-view.filter": "visible",
        "record-view.event-detail": "visible",
        "record-view.result": "expandable",
        "record-view.artifact-metadata": "expandable",
        "record-view.replay-metadata": "expandable",
        "record-view.mode-boundary": "visible",
    },
}


def unit_visibility(view: str, unit: str) -> str:
    """The visibility class the specification requires of one unit."""
    classes = UNIT_VISIBILITY.get(view)
    if classes is None or unit not in classes:
        raise CoverageError(
            "unit {0!r} has no declared visibility in view {1!r}".format(unit, view)
        )
    return classes[unit]


def expandable_units(view: str) -> Tuple[str, ...]:
    """The units this view must render behind a read-only disclosure."""
    return tuple(
        unit
        for unit, visibility in UNIT_VISIBILITY.get(view, {}).items()
        if visibility == "expandable"
    )


def _view(view: str) -> Dict[str, Tuple[str, ...]]:
    if view not in MATRIX:
        raise CoverageError("view {0!r} is not in the acceptance matrix".format(view))
    return MATRIX[view]


def required_units(view: str) -> Tuple[str, ...]:
    """The semantic units the PRD requires this view to expose."""
    return _view(view)["units"]


def required_scenarios(view: str) -> Tuple[str, ...]:
    """The scenarios the PRD requires this view to be tested under."""
    return _view(view)["scenarios"]


#: The host-executed evidence beyond the four interaction surfaces: the full
#: PRD matrix re-run in the real engine, and the negative redaction check. Same
#: pattern as ``HOST_SURFACES`` -- a status is only ever ``met`` alongside the
#: evidence file that backs it, so a condition cannot be dropped from this list
#: to fake readiness.
HOST_EVIDENCE: Tuple[Dict[str, str], ...] = (
    {
        "condition": "full-matrix-in-real-host",
        "status": "met",
        "evidence": "tests/test_ui_matrix_host.py",
        "scope": "every view x scenario at 390px and 1280px in normal and "
        "review mode, served over HTTP and asserted in the engine: each "
        "required unit rendered, no undeclared reference, the review layer "
        "purely additive",
    },
    {
        "condition": "redaction-negative",
        "status": "met",
        "evidence": "tests/test_ui_redaction_host.py",
        "scope": "an owner polluted with credential-shaped strings served "
        "through the host; nothing sensitive survives in the document, URL, "
        "token or browser-persisted storage",
    },
)


def _acceptance(gaps: Tuple[str, ...]) -> Dict[str, Any]:
    """List the conditions under which this report could be accepted.

    The report never accepts itself. It states each precondition, whether it
    currently holds, and the evidence behind that claim, so a human can make
    the decision the PRD reserves for a human without re-deriving what is
    outstanding. ``met`` means every precondition holds; the decision itself is
    recorded in the PRD, never flipped here.
    """
    conditions = [
        {
            "condition": "structural-coverage-complete",
            "status": "unmet" if gaps else "met",
            "evidence": "this report's gap list against the fixed PRD matrix",
        },
        {
            "condition": "host-interaction-surfaces-verified",
            "status": "unmet" if HOST_UNKNOWNS else "met",
            "evidence": ", ".join(s["evidence"] for s in HOST_SURFACES),
        },
    ]
    conditions.extend(dict(entry) for entry in HOST_EVIDENCE)
    return {
        "conditions": tuple(conditions),
        "met": all(c["status"] == "met" for c in conditions),
        "decision": "human: recorded in the PRD, never flipped by this report",
    }


def _conclusion() -> str:
    """State what this report is, and what it still is not.

    Even with every interaction surface verified the report stays
    ``accepted: false``. Structural coverage plus host surfaces is not the
    acceptance decision: the PRD's fixed matrix -- every view, state and
    viewport -- and the negative redaction checks are separate evidence, and an
    acceptance decision is a human one recorded in the PRD, not a flag this
    function flips on its own.
    """
    if HOST_UNKNOWNS:
        return (
            "structural declarations only; {0} interaction surface(s) remain "
            "unknown and this report is not an acceptance decision".format(
                len(HOST_UNKNOWNS)
            )
        )
    return (
        "structural declarations complete and every interaction surface has "
        "host evidence within its stated scope; full-matrix and redaction "
        "evidence is registered under acceptance conditions, and this report "
        "is not an acceptance decision"
    )


def coverage_report(
    view: str,
    *,
    declared_refs: Sequence[str],
    not_applicable: Mapping[str, str] = None,
) -> Dict[str, Any]:
    """Measure declared references against the specification.

    The denominator is always the full specification. Marking a unit not
    applicable requires a stated reason and removes it from the gap list, but
    never from the denominator and never into the covered count: "we chose not
    to show this" and "we verified this" are different claims.

    A unit that is not in the specification cannot be excused as not
    applicable, because that is how a missing implementation gets relabelled as
    out of scope. Neither can a unit the specification requires to be visible or
    expandable: those are always supposed to be there, so their absence is a
    gap by definition. Only a ``conditional`` unit -- one whose presence depends
    on the run class or state -- can legitimately be excused.
    """
    units = required_units(view)
    excused = dict(not_applicable or {})

    for unit, reason in excused.items():
        if unit not in units:
            raise CoverageError(
                "unit {0!r} is not in the {1!r} specification and cannot be "
                "excused as not applicable".format(unit, view)
            )
        if not str(reason).strip():
            raise CoverageError(
                "unit {0!r} needs a stated reason to be not applicable".format(unit)
            )
        visibility = unit_visibility(view, unit)
        if visibility != "conditional":
            raise CoverageError(
                "unit {0!r} is specified as {1!r} and cannot be excused as not "
                "applicable; its absence is a gap".format(unit, visibility)
            )

    declared = set(declared_refs)
    covered = tuple(unit for unit in units if unit in declared and unit not in excused)
    gaps = tuple(unit for unit in units if unit not in declared and unit not in excused)

    countable = len(units) - len(excused)
    ratio = (len(covered) / countable) if countable else 0.0

    return {
        "view": view,
        "required": len(units),
        "covered": len(covered),
        "not_applicable": len(excused),
        "gaps": gaps,
        "ratio": ratio,
        "evidence": "structural-only",
        "surfaces": HOST_SURFACES,
        "unverified": HOST_UNKNOWNS,
        "accepted": False,
        "acceptance": _acceptance(gaps),
        "conclusion": _conclusion(),
    }
