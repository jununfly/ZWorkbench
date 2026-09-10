"""Runtime rendering of declared UI references and review-session instances.

Rendering reads the generated manifest, so a node that was never declared
cannot acquire a plausible-looking reference.  Instance identity is a
review-session concern: handles are random, memory-only, and never derived from
run identity, titles or list positions.

This module owns interface reference metadata and short-lived presentation
state only.  It holds no run, attempt, event, effect, approval or replay state.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from .ui_ref import UiRefError

HANDLE_BYTES = 16


class UnregisteredReference(UiRefError):
    """A reference that the manifest does not declare cannot be rendered."""


def render_attributes(manifest: Dict[str, Any], ref: str) -> Dict[str, str]:
    """Return the DOM attributes for one declared semantic element."""
    for entry in manifest["refs"]:
        if entry["ref"] == ref:
            return {"data-ui-ref": ref}
    raise UnregisteredReference(
        "reference {0!r} is not declared in this manifest".format(ref)
    )


class ReviewSession:
    """Tracks the semantic instances currently mounted in one review session.

    A handle identifies an instance inside this session only.  It is random,
    never derived from run identity, titles, positions or their hashes, and it
    is not a credential or a durable entity.
    """

    def __init__(self, manifest: Dict[str, Any]) -> None:
        self._manifest = manifest
        self._declared = {entry["ref"]: entry for entry in manifest["refs"]}
        self._mounted: Dict[str, Dict[str, str]] = {}
        self._unmounted: Dict[str, Dict[str, str]] = {}
        self._order: list = []
        self._locked: Optional[str] = None

    def mount(self, ref: str, *, entity_key: str) -> str:
        """Register one mounted instance and return its session handle."""
        if ref not in self._declared:
            raise UnregisteredReference(
                "reference {0!r} is not declared in this manifest".format(ref)
            )
        handle = secrets.token_hex(HANDLE_BYTES)
        self._mounted[handle] = {"ref": ref, "entity_key": entity_key}
        self._order.append(handle)
        return handle

    def close(self) -> None:
        """End the review session: every handle is void and never reused."""
        self._mounted.clear()
        self._unmounted.clear()
        self._order = []
        self._locked = None

    def unmount(self, handle: str) -> None:
        """Record that one instance left the DOM, for example via virtualisation.

        The handle stays interpretable so that a later lookup can say
        ``unavailable`` instead of silently resolving to a different row.
        """
        mounted = self._mounted.pop(handle, None)
        if mounted is not None:
            self._unmounted[handle] = mounted
            self._order = [item for item in self._order if item != handle]

    def remount(self, ref: str, *, entity_key: str) -> str:
        """Re-attach an entity that was unmounted, reusing its handle."""
        for handle, entry in list(self._unmounted.items()):
            if entry["ref"] == ref and entry["entity_key"] == entity_key:
                self._mounted[handle] = self._unmounted.pop(handle)
                self._order.append(handle)
                return handle
        return self.mount(ref, entity_key=entity_key)

    def reorder(self, handles: Any) -> None:
        """Apply a new display order; instance associations are unaffected."""
        reordered = [handle for handle in handles if handle in self._mounted]
        remaining = [handle for handle in self._order if handle not in reordered]
        self._order = reordered + remaining

    def mounted_handles(self) -> tuple:
        """Currently mounted handles in display order.

        Exposed so a panel can be built without reaching into session
        internals; unmounted instances are excluded.
        """
        return tuple(handle for handle in self._order if handle in self._mounted)

    def ref_of(self, handle: str) -> str:
        """The structural reference one handle points at."""
        entry = self._mounted.get(handle) or self._unmounted[handle]
        return entry["ref"]

    def unlock(self) -> None:
        """Drop the annotation target, leaving instance associations intact."""
        self._locked = None

    def entity_key_of(self, handle: str) -> str:
        """Return the UI entity key a handle tracks, for in-memory use only."""
        entry = self._mounted.get(handle) or self._unmounted[handle]
        return entry["entity_key"]

    def lock(self, handle: str) -> None:
        """Retain one instance as the annotation target."""
        self._locked = handle

    def locked_target(self) -> Optional[Dict[str, Any]]:
        """Resolve the locked instance, or ``None`` when nothing is locked."""
        if self._locked is None:
            return None
        return self.resolve_instance(self._locked)

    def resolve_structural(self, ref: str) -> Dict[str, Any]:
        """Resolve a structural reference against the mounted instances.

        Several mounted instances of one declaration are ``ambiguous``: the
        caller must choose an instance locally.  Defaulting to the first row
        would silently annotate the wrong record.
        """
        if ref not in self._declared:
            raise UnregisteredReference(
                "reference {0!r} is not declared in this manifest".format(ref)
            )
        matches = [
            handle
            for handle in self._order
            if handle in self._mounted and self._mounted[handle]["ref"] == ref
        ]
        if not matches:
            return {"outcome": "unavailable", "ref": ref}
        if len(matches) > 1:
            return {"outcome": "ambiguous", "ref": ref, "instance_count": len(matches)}
        return {"outcome": "found", "ref": ref, "instance": matches[0]}

    def resolve_instance(self, handle: str) -> Dict[str, Any]:
        """Resolve one instance handle within this session."""
        mounted = self._mounted.get(handle)
        if mounted is not None:
            declaration = self._declared[mounted["ref"]]
            return {
                "outcome": "found",
                "ref": mounted["ref"],
                "semantic_zh": declaration["semantic_zh"],
                "instance": handle,
            }
        unmounted = self._unmounted.get(handle)
        if unmounted is not None:
            return {"outcome": "unavailable", "ref": unmounted["ref"]}
        return {"outcome": "expired"}


def audit_rendered_html(manifest: Dict[str, Any], html_text: str) -> Dict[str, Any]:
    """Compare the references in rendered HTML against the manifest.

    ``missing`` is computed from the declarations, not from what the DOM
    happens to contain, so an unimplemented element cannot shrink the
    denominator of a coverage check.
    """
    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.counts: Dict[str, int] = {}

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            for name, value in attrs:
                if name == "data-ui-ref" and value:
                    self.counts[value] = self.counts.get(value, 0) + 1

    collector = _Collector()
    collector.feed(html_text)
    declared = {entry["ref"] for entry in manifest["refs"]}
    rendered = collector.counts
    return {
        "ui_map": manifest["ui_map"],
        "instances": dict(rendered),
        "undeclared": tuple(sorted(set(rendered) - declared)),
        "missing": tuple(sorted(declared - set(rendered))),
    }
