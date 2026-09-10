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

    def __post_init__(self) -> None:
        if len(self.ref) > MAX_REF_LENGTH or not _REF_PATTERN.match(self.ref):
            raise UiRefValidationError("invalid ui reference name {0!r}".format(self.ref))
        if not self.semantic_zh.strip():
            raise UiRefValidationError(
                "declaration {0!r} requires a semantic name".format(self.ref)
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "semantic_zh": self.semantic_zh,
            "kind": self.kind,
            "view": self.view,
            "parent": self.parent,
            "source": self.source.to_dict(),
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
        return tuple(problems)

    def build_manifest(self, *, build: str) -> Dict[str, Any]:
        """Derive the deterministic manifest from the current declarations.

        ``ui_map`` digests the reference semantics only.  The build receipt is
        recorded alongside it but deliberately excluded from the digest, so a
        source change that leaves every declaration intact does not invalidate
        previously copied feedback tokens.
        """
        if not _SHA256_PATTERN.match(build):
            raise UiRefValidationError(
                "build receipt must be a lowercase sha256 hex digest"
            )
        problems = self.validate()
        if problems:
            raise UiRefValidationError("; ".join(problems))
        refs = [
            self._declarations[ref].to_dict()
            for ref in sorted(self._declarations)
        ]
        semantics = {"schema": UI_REF_SCHEMA, "refs": refs}
        canonical = json.dumps(
            semantics, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        ui_map = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {"schema": UI_REF_SCHEMA, "refs": refs, "ui_map": ui_map, "build": build}


def resolve(manifest: Dict[str, Any], ref: str, *, ui_map: str) -> Dict[str, Any]:
    """Resolve one reference against a pinned manifest.

    The caller must name the ``ui_map`` it expects.  A mismatch is reported as
    ``incompatible`` and carries no declaration data: the current manifest never
    silently stands in for the one the reference came from.

    This is the structural/code-provenance result only.  Resolving a live DOM
    instance is a separate contract with its own outcomes.
    """
    if manifest.get("ui_map") != ui_map:
        return {"outcome": "incompatible", "ref": ref, "requested_ui_map": ui_map}
    for entry in manifest["refs"]:
        if entry["ref"] == ref:
            return {
                "outcome": "found",
                "ref": ref,
                "semantic_zh": entry["semantic_zh"],
                "view": entry["view"],
                "source": dict(entry["source"]),
            }
    return {"outcome": "not-found", "ref": ref}
