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
from .ui_review import HOST_UNKNOWNS


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
    out of scope.
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
        "unverified": HOST_UNKNOWNS,
        "accepted": False,
        "conclusion": (
            "structural declarations only; interaction surfaces remain unknown "
            "and this report is not an acceptance decision"
        ),
    }
