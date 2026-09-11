"""UI reference declarations and the manifest generated from them.

The registry is the single source of UI reference metadata: code declares a
semantic element once, and the build derives the manifest from those
declarations.  There is no hand-maintained mapping table.

This module owns interface reference metadata only.  It holds no run, attempt,
event, effect, approval or replay state, and it never reads or writes the
composition owner.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


UI_REF_SCHEMA = "ui-ref-manifest/v1"

MAX_REF_LENGTH = 128
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class UiRefError(Exception):
    """Base class for a UI reference boundary error."""


class UiRefValidationError(UiRefError):
    """A declaration or manifest violates the reference contract."""


@dataclass(frozen=True)
class SourceAnchor:
    """Where a declaration lives in the repository."""

    repo_path: str
    symbol: str
    content_digest: str

    def __post_init__(self) -> None:
        if not self.repo_path or self.repo_path.startswith("/") or ":\\" in self.repo_path:
            raise UiRefValidationError(
                "source anchor repo_path must be repository-relative, got {0!r}".format(
                    self.repo_path
                )
            )
        if not self.symbol:
            raise UiRefValidationError("source anchor symbol is required")
        if not _SHA256_PATTERN.match(self.content_digest):
            raise UiRefValidationError(
                "source anchor content_digest must be a lowercase sha256 hex digest"
            )

    def to_dict(self) -> Dict[str, str]:
        return {
            "repo_path": self.repo_path,
            "symbol": self.symbol,
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class UiRefDeclaration:
    """One declared semantic element."""

    ref: str
    semantic_zh: str
    kind: str
    view: str
    source: SourceAnchor
    parent: Optional[str] = None
    accessible_name: Optional[str] = None
    alias_of: Tuple[str, ...] = ()
    retired: bool = False
    replaced_by: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.ref) > MAX_REF_LENGTH or not _REF_PATTERN.match(self.ref):
            raise UiRefValidationError("invalid ui reference name {0!r}".format(self.ref))
        if not self.semantic_zh.strip():
            raise UiRefValidationError(
                "declaration {0!r} requires a semantic name".format(self.ref)
            )
        for alias in self.alias_of:
            if len(alias) > MAX_REF_LENGTH or not _REF_PATTERN.match(alias):
                raise UiRefValidationError(
                    "invalid alias name {0!r} on {1!r}".format(alias, self.ref)
                )
        if self.replaced_by is not None and not self.retired:
            raise UiRefValidationError(
                "declaration {0!r} names a replacement without being retired".format(
                    self.ref
                )
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the declaration.

        ``accessible_name`` is deliberately absent: it is presentation copy, and
        including it would make a wording change move the mapping version.
        """
        return {
            "ref": self.ref,
            "semantic_zh": self.semantic_zh,
            "kind": self.kind,
            "view": self.view,
            "parent": self.parent,
            "source": self.source.to_dict(),
            "alias_of": list(self.alias_of),
            "retired": self.retired,
            "replaced_by": self.replaced_by,
        }


class UiRefRegistry:
    """Collects declarations and derives the manifest from them."""

    def __init__(self) -> None:
        self._declarations: Dict[str, UiRefDeclaration] = {}

    def declare(self, declaration: UiRefDeclaration) -> str:
        """Register one declaration and return its reference.

        A duplicate reference is rejected and leaves the original declaration
        untouched: registry uniqueness is not the same rule as repeated dynamic
        instances of one declaration.
        """
        existing = self._declarations.get(declaration.ref)
        if existing is not None:
            raise UiRefValidationError(
                "duplicate declaration for ref {0!r}".format(declaration.ref)
            )
        self._declarations[declaration.ref] = declaration
        return declaration.ref

    def declaration(self, ref: str) -> UiRefDeclaration:
        """Return one registered declaration."""
        return self._declarations[ref]

    def validate(self) -> Tuple[str, ...]:
        """Return every cross-declaration problem, in reference order."""
        problems = []
        for ref in sorted(self._declarations):
            parent = self._declarations[ref].parent
            if parent is None:
                continue
            if parent == ref:
                problems.append("declaration {0!r} is its own parent".format(ref))
                continue
            if parent not in self._declarations:
                problems.append(
                    "declaration {0!r} names undeclared parent {1!r}".format(ref, parent)
                )
                continue
            seen = {ref}
            cursor = parent
            while cursor is not None:
                if cursor in seen:
                    problems.append("declaration {0!r} sits in a parent cycle".format(ref))
                    break
                seen.add(cursor)
                cursor = self._declarations[cursor].parent if cursor in self._declarations else None

        problems.extend(self._alias_problems())
        problems.extend(self._replacement_problems())
        return tuple(problems)

    def _alias_problems(self) -> list:
        """An alias is a retired name pointing at one live identity.

        Two declarations claiming the same old name, or an alias shadowing a
        live reference, would make an old token ambiguous rather than migrated.
        """
        problems = []
        claimed: Dict[str, str] = {}
        for ref in sorted(self._declarations):
            for alias in self._declarations[ref].alias_of:
                if alias == ref:
                    problems.append("declaration {0!r} aliases itself".format(ref))
                    continue
                if alias in self._declarations:
                    problems.append(
                        "alias {0!r} on {1!r} collides with a live declaration".format(
                            alias, ref
                        )
                    )
                    continue
                if alias in claimed:
                    problems.append(
                        "alias {0!r} is claimed by both {1!r} and {2!r}".format(
                            alias, claimed[alias], ref
                        )
                    )
                    continue
                claimed[alias] = ref
        return problems

    def _replacement_problems(self) -> list:
        """A replacement must name a real, reachable, non-circular target."""
        problems = []
        for ref in sorted(self._declarations):
            target = self._declarations[ref].replaced_by
            if target is None:
                continue
            if target == ref:
                problems.append("declaration {0!r} replaces itself".format(ref))
                continue
            if target not in self._declarations:
                problems.append(
                    "declaration {0!r} names undeclared replacement {1!r}".format(ref, target)
                )
                continue
            seen = {ref}
            cursor = target
            while cursor is not None:
                if cursor in seen:
                    problems.append(
                        "declaration {0!r} sits in a replacement cycle".format(ref)
                    )
                    break
                seen.add(cursor)
                cursor = self._declarations[cursor].replaced_by if cursor in self._declarations else None
        return problems

    def build_manifest(
        self, *, build: str, previous_ui_map: Optional[str] = None
    ) -> Dict[str, Any]:
        """Derive the deterministic manifest from the current declarations.

        ``ui_map`` digests reference *semantics* only: identity, semantic name,
        kind, view, parent and lifecycle metadata.  Three things are recorded
        alongside it but excluded from the digest, because each would otherwise
        invalidate every previously copied token for a change that moved no
        identity:

        * the build receipt, which follows any source edit;
        * the source anchor, whose digest follows a comment-only edit;
        * the previous mapping version, which is lineage rather than semantics
          and would form a self-referential chain.
        """
        if not _SHA256_PATTERN.match(build):
            raise UiRefValidationError(
                "build receipt must be a lowercase sha256 hex digest"
            )
        if previous_ui_map is not None and not _SHA256_PATTERN.match(previous_ui_map):
            raise UiRefValidationError(
                "previous_ui_map must be a lowercase sha256 hex digest"
            )
        problems = self.validate()
        if problems:
            raise UiRefValidationError("; ".join(problems))
        refs = [
            self._declarations[ref].to_dict()
            for ref in sorted(self._declarations)
        ]
        semantics = {
            "schema": UI_REF_SCHEMA,
            "refs": [
                {key: value for key, value in entry.items() if key != "source"}
                for entry in refs
            ],
        }
        canonical = json.dumps(
            semantics, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        ui_map = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if previous_ui_map == ui_map:
            raise UiRefValidationError(
                "a manifest cannot name itself as its previous mapping version"
            )
        return {
            "schema": UI_REF_SCHEMA,
            "refs": refs,
            "ui_map": ui_map,
            "build": build,
            "previous_ui_map": previous_ui_map,
        }


def _entry_of(manifest: Dict[str, Any], ref: str) -> Optional[Dict[str, Any]]:
    for entry in manifest["refs"]:
        if entry["ref"] == ref:
            return entry
    return None


def _found(ref: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "outcome": "found",
        "ref": ref,
        "semantic_zh": entry["semantic_zh"],
        "view": entry["view"],
        "source": dict(entry["source"]),
    }


def _semantics_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The identity-bearing fields, excluding source and lifecycle bookkeeping."""
    return {key: entry[key] for key in ("ref", "semantic_zh", "kind", "view", "parent")}


def resolve(
    manifest: Dict[str, Any],
    ref: str,
    *,
    ui_map: str,
    previous_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve one reference against a pinned manifest.

    The caller must name the ``ui_map`` the reference came from.  When that is
    the current version the answer comes from this manifest directly.

    When it is the immediately previous version, the caller must also supply
    that manifest, so the answer rests on the old declarations rather than on
    the current ones standing in for them.  Without it the outcome is
    ``incompatible``: a locally addressable artifact is missing evidence, not an
    invitation to guess.  Anything older than one version is outside the
    compatibility window.

    Outcomes never fall back to a selector or CSS guess.  ``migrated`` means the
    same identity was renamed; ``retired`` means the semantics changed and a
    replacement exists, and it is never reported as the same identity.

    This is the structural/code-provenance result only.  Resolving a live DOM
    instance is a separate contract with its own outcomes.
    """
    current_ui_map = manifest.get("ui_map")

    if ui_map == current_ui_map:
        entry = _entry_of(manifest, ref)
        if entry is None:
            return {"outcome": "not-found", "ref": ref}
        if entry["retired"]:
            result = {
                "outcome": "retired",
                "retired_ref": ref,
                "identity": "different-semantics",
            }
            if entry["replaced_by"] is not None:
                result["replacement"] = entry["replaced_by"]
            return result
        return _found(ref, entry)

    if ui_map != manifest.get("previous_ui_map"):
        return {
            "outcome": "incompatible",
            "ref": ref,
            "requested_ui_map": ui_map,
            "reason": "outside-compatibility-window",
        }

    if previous_manifest is None:
        return {
            "outcome": "incompatible",
            "ref": ref,
            "requested_ui_map": ui_map,
            "reason": "previous-manifest-required",
        }
    if previous_manifest.get("ui_map") != ui_map:
        return {
            "outcome": "incompatible",
            "ref": ref,
            "requested_ui_map": ui_map,
            "reason": "previous-manifest-mismatch",
        }

    previous_entry = _entry_of(previous_manifest, ref)
    if previous_entry is None:
        return {"outcome": "not-found", "ref": ref}

    for entry in manifest["refs"]:
        if ref in (entry["alias_of"] or ()):
            return {
                "outcome": "migrated",
                "ref": entry["ref"],
                "previous_ref": ref,
                "identity": "same-semantics",
                "semantic_zh": entry["semantic_zh"],
                "view": entry["view"],
                "source": dict(entry["source"]),
            }

    current_entry = _entry_of(manifest, ref)
    if current_entry is None:
        return {"outcome": "not-found", "ref": ref}
    if current_entry["retired"]:
        result = {
            "outcome": "retired",
            "retired_ref": ref,
            "identity": "different-semantics",
        }
        if current_entry["replaced_by"] is not None:
            result["replacement"] = current_entry["replaced_by"]
        return result
    if _semantics_of(current_entry) != _semantics_of(previous_entry):
        return {
            "outcome": "incompatible",
            "ref": ref,
            "requested_ui_map": ui_map,
            "reason": "semantics-changed",
        }
    return _found(ref, current_entry)
