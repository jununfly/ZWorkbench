"""The local review annotation mode: panel state, gestures and exit.

This module owns the *decisions* the review mode makes.  It deliberately holds
no run, effect or approval state, performs no network or telemetry call, and
never dispatches a business action of its own: business activation is delivered
by the host and merely observed here.

Scope of evidence.  Every contract below is verified as a state machine.  The
host-dependent half of each interaction — whether a browser really honours
``pointer-events: none``, what native focus order a real DOM yields, how a real
clipboard API rejects a write, and whether focus visibly lands where we ask —
is *not* verified here. Each such surface is tracked in ``HOST_SURFACES``
together with the host evidence that settled it, or as ``unknown`` when none
has. A green test in this module is never that evidence.
"""

from __future__ import annotations

import secrets
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from .ui_ref import UiRefError
from .ui_runtime import ReviewSession
from .ui_token import build_token


PANEL_ACTIONS = ("select", "lock", "copy", "clear", "close")

REVIEW_ENTRY_REF = "review.entry"

#: The four interaction surfaces the PRD requires that a state machine cannot
#: settle. Each one is lifted out of ``unknown`` only by naming the evidence
#: that settled it, and only for the scope that evidence actually covers.
#:
#: ``verified_by`` is ``host-engine`` when a real rendering engine produced the
#: observation and ``pending-host`` when nothing has. It is never ``automated``:
#: a green test in this module exercises the state machine, and calling that
#: automated verification of a host surface is the precise confusion this table
#: exists to prevent.
#:
#: ``scope`` is load-bearing on ``clipboard-failure-visible``. A headless engine
#: produces no spontaneous user denial, so the rejection is injected (ADR 0004).
#: That supports "when a rejection occurs it is visible and nothing retries" and
#: nothing about how a real permission dialog behaves.
HOST_SURFACES: Tuple[Dict[str, str], ...] = (
    {
        "surface": "keyboard-focus-order",
        "status": "verified",
        "verified_by": "host-engine",
        "evidence": "tests/test_ui_focus_order.py",
        "scope": "real Tab and Shift+Tab dispatched to a rendered document; "
        "the ring is every declared element in document order -- the page "
        "layer makes static units focusable because a keyboard reviewer has "
        "no hover -- then the review entry and the panel actions in declared "
        "order, traversable in both directions",
    },
    {
        "surface": "pointer-events-passthrough",
        "status": "verified",
        "verified_by": "host-engine",
        "evidence": "tests/test_ui_pointer_passthrough.py",
        "scope": "a real click dispatched at a covered business element is "
        "delivered to that element exactly once, and a click on a panel "
        "control stays in the panel",
    },
    {
        "surface": "clipboard-failure-visible",
        "status": "verified",
        "verified_by": "host-engine",
        "evidence": "tests/test_ui_clipboard.py",
        "scope": "injected rejection only: when a write is refused the failure "
        "is announced, the selection survives, the host error text is not "
        "echoed and nothing retries; a real user denial is not covered",
    },
    {
        "surface": "focus-restore-on-close",
        "status": "verified",
        "verified_by": "host-engine",
        "evidence": "tests/test_ui_focus_restore.py",
        "scope": "focus lands on the prior element when it is still rendered "
        "and on the review entry otherwise, never inside the closed panel and "
        "never on the body; a keyboard-driven close leaves a visible ring",
    },
)

#: The surfaces still waiting on host evidence. Derived rather than maintained,
#: so a surface cannot be dropped from the unknown list without gaining the
#: evidence field that moved it.
HOST_UNKNOWNS: Tuple[Dict[str, str], ...] = tuple(
    surface for surface in HOST_SURFACES if surface["status"] == "unknown"
)


_BUSINESS_GESTURES = frozenset({"click", "Enter", " "})
_PREVIEW_GESTURES = frozenset({"hover", "focus"})


class ReviewModeError(UiRefError):
    """An operation was requested that the current review state forbids."""


class ReviewMode:
    """Default-off review mode over one manifest.

    Enabling is explicit and local.  Disabling releases every registered
    resource and voids every session handle, so repeated start/stop cycles
    cannot accumulate overlays, listeners or stale instance associations.
    """

    def __init__(self, manifest: Dict[str, Any]) -> None:
        self._manifest = manifest
        self._enabled = False
        self._resources: Tuple[Dict[str, str], ...] = ()
        self._session: Optional[ReviewSession] = None
        self._panel_focused = False
        self._focused_ref: Optional[str] = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Review mode is off until a local caller turns it on."""
        return self._enabled

    def enable(self, *, focused_ref: str = None) -> None:
        """Turn review mode on, recording what held focus beforehand.

        Enabling twice is idempotent: resources are registered once, so a
        double enable cannot leak a second overlay or listener set.
        """
        if self._enabled:
            return
        self._enabled = True
        self._focused_ref = focused_ref
        self._session = ReviewSession(self._manifest)
        self._resources = (
            {"kind": "overlay", "name": "review-highlight"},
            {"kind": "listener", "name": "pointer-preview"},
            {"kind": "listener", "name": "panel-keys"},
        )

    def disable(self) -> None:
        """Turn review mode off and release everything it registered."""
        if self._session is not None:
            self._session.close()
        self._session = None
        self._resources = ()
        self._enabled = False
        self._panel_focused = False
        self._focused_ref = None

    def unload(self) -> None:
        """Release review resources when the host document is unloaded."""
        self.disable()

    def resources(self) -> Tuple[Dict[str, str], ...]:
        """Report currently held host resources, for residue checks."""
        return self._resources

    def review_entry_ref(self) -> str:
        """The control that opens review mode, used as the focus fallback."""
        return REVIEW_ENTRY_REF

    def _require_enabled(self) -> ReviewSession:
        if not self._enabled or self._session is None:
            raise ReviewModeError("review mode is off")
        return self._session

    # -- instances ----------------------------------------------------------

    def mount(self, ref: str, *, entity_key: str) -> str:
        """Track one mounted semantic instance."""
        return self._require_enabled().mount(ref, entity_key=entity_key)

    def session_handles(self) -> Tuple[str, ...]:
        """Every handle this session still tracks; empty once disabled."""
        if self._session is None:
            return ()
        return self._session.mounted_handles()

    def resolve_instance(self, handle: str) -> Dict[str, Any]:
        """Resolve a handle; a handle from a previous session is expired."""
        if self._session is None:
            return {"outcome": "expired"}
        return self._session.resolve_instance(handle)

    # -- pointer and keyboard ----------------------------------------------

    def overlay_descriptor(self) -> Dict[str, str]:
        """Describe the highlight layer.

        The layer is transparent to input by contract.  Whether a real engine
        honours it is a host unknown, not something this descriptor proves.
        """
        return {"kind": "overlay", "pointer-events": "none", "role": "presentation"}

    def preview(self, handle: str, *, gesture: str) -> Dict[str, Any]:
        """Hover and focus preview a target; they never select it."""
        session = self._require_enabled()
        if gesture not in _PREVIEW_GESTURES:
            raise ReviewModeError("gesture {0!r} is not a preview gesture".format(gesture))
        resolved = session.resolve_instance(handle)
        return {"outcome": "preview", "target": resolved}

    def activate(
        self, handle: str, action: Callable[[], Any], *, gesture: str
    ) -> Dict[str, Any]:
        """Let a business activation through, unchanged and exactly once.

        Review mode observes the gesture and calls the host action once.  It
        does not duplicate, delay, swallow or re-dispatch it.
        """
        self._require_enabled()
        if gesture not in _BUSINESS_GESTURES:
            raise ReviewModeError("gesture {0!r} is not a business activation".format(gesture))
        action()
        return {"business": "delivered", "review": "not-consumed"}

    def handle_key(self, key: str, *, business_dialog_open: bool = False) -> Dict[str, Any]:
        """Route one key press.

        Escape is consumed only when the panel holds focus and no business
        dialog is open, so review mode cannot steal a dismissal from the
        business UI.
        """
        self._require_enabled()
        if key == "Escape" and self._panel_focused and not business_dialog_open:
            self.clear()
            return {"review": "consumed", "business": "not-delivered"}
        return {"review": "not-consumed", "business": "delivered"}

    # -- panel --------------------------------------------------------------

    def panel_entries(self) -> Tuple[Dict[str, Any], ...]:
        """List mounted targets for the panel.

        An entry carries the structural reference, its Chinese semantic name,
        the session handle and, for repeated structural items only, a transient
        mark that helps a human tell two identical rows apart.  The mark is
        regenerated on every read so it cannot become an identity, and the
        business entity key is never included.
        """
        session = self._require_enabled()
        handles = session.mounted_handles()
        counts: Dict[str, int] = {}
        for handle in handles:
            ref = session.ref_of(handle)
            counts[ref] = counts.get(ref, 0) + 1

        entries = []
        for handle in handles:
            resolved = session.resolve_instance(handle)
            ref = resolved["ref"]
            entries.append(
                {
                    "ref": ref,
                    "semantic_zh": resolved["semantic_zh"],
                    "instance": handle,
                    "mark": secrets.token_hex(2) if counts[ref] > 1 else None,
                }
            )
        return tuple(entries)

    def keyboard_plan(self) -> Dict[str, str]:
        """Every panel action must be reachable without a pointer."""
        self._require_enabled()
        return {
            # Pointing at any declared element is ArrowUp/ArrowDown (or Tab):
            # the page layer moves focus across all of them. Locking the
            # pointed-at entry is this button, reached by key.
            "select": "ArrowUp/ArrowDown to point, Enter to lock",
            "lock": "Enter",
            "copy": "Ctrl+C",
            "clear": "Escape",
            "close": "Shift+Tab to close button, then Enter",
        }

    def focus_panel(self) -> None:
        """Move focus into the review panel."""
        self._require_enabled()
        self._panel_focused = True

    def focused_entry(self) -> Optional[Dict[str, Any]]:
        """The panel entry that currently has focus, if the panel is focused."""
        session = self._require_enabled()
        if not self._panel_focused:
            return None
        entries = self.panel_entries()
        return entries[0] if entries else None

    def lock(self, handle: str) -> None:
        """Retain one instance as the annotation target.

        Locking is a review-side selection.  It never dispatches a click, key
        press or any other activation to the business element.
        """
        self._require_enabled().lock(handle)

    def clear(self) -> None:
        """Drop the current selection."""
        session = self._require_enabled()
        session.unlock()

    def locked_target(self) -> Optional[Dict[str, Any]]:
        """The currently locked instance, or ``None``."""
        if self._session is None:
            return None
        return self._session.locked_target()

    def close_panel(self, *, mounted_refs: Sequence[str]) -> Dict[str, Any]:
        """Close the panel and report where focus should go.

        The pre-review target is restored when it is still mounted; otherwise
        focus returns to the review entry rather than being left nowhere.
        Closing the panel is not the same as leaving review mode.
        """
        self._require_enabled()
        self._panel_focused = False
        if self._focused_ref is not None and self._focused_ref in tuple(mounted_refs):
            return {"outcome": "restored", "focus": self._focused_ref}
        return {"outcome": "fallback", "focus": REVIEW_ENTRY_REF}

    # -- copy ---------------------------------------------------------------

    def copy(
        self,
        writer: Callable[[str], Any],
        *,
        user_gesture: bool,
        viewport: str = "wide",
        state: str = "unknown",
    ) -> Dict[str, Any]:
        """Copy the locked target's review token.

        A copy happens only on a user gesture.  A host rejection is reported as
        a visible failure, the selection is kept so the human can retry
        deliberately, and the write is never retried automatically.  The host
        error text is not echoed back.
        """
        session = self._require_enabled()
        if not user_gesture:
            return {"outcome": "refused", "reason": "copy requires a user gesture"}

        target = session.locked_target()
        if target is None or target["outcome"] != "found":
            return {"outcome": "no-target"}

        token = build_token(
            self._manifest,
            target["ref"],
            viewport=viewport,
            state=state,
            instance=target["instance"],
        )
        try:
            writer(token)
        except Exception:
            return {
                "outcome": "copy-failed",
                "visible": True,
                "retry": "user-initiated-only",
            }
        return {"outcome": "copied", "visible": True}
