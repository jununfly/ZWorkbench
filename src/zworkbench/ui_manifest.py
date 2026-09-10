"""Build receipt and local artifact handling for the UI reference manifest.

The receipt pins the source snapshot the manifest was generated from, including
uncommitted working-tree edits.  A Git commit may accompany it as a secondary
hint but never replaces content identity.

Queries are local and read-only: they read a stored artifact, never download a
historical version, and never start a business run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable

from .ui_ref import UiRefValidationError


RECEIPT_SCHEMA = "ui-ref-build-receipt/v1"


def build_receipt(root: Path, sources: Iterable[str]) -> Dict[str, Any]:
    """Digest the declared source files as they exist in the working tree."""
    entries = []
    for relative in sorted(sources):
        if relative.startswith("/"):
            raise UiRefValidationError(
                "source path must be repository-relative, got {0!r}".format(relative)
            )
        content = (root / relative).read_bytes()
        entries.append(
            {
                "repo_path": relative,
                "content_digest": hashlib.sha256(content).hexdigest(),
            }
        )
    canonical = json.dumps(
        {"schema": RECEIPT_SCHEMA, "sources": entries},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return {
        "schema": RECEIPT_SCHEMA,
        "sources": entries,
        "build": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _artifact_path(store: Path, ui_map: str, build: str) -> Path:
    """Address an artifact by both halves of its identity."""
    return store / "{0}.{1}.json".format(ui_map, build)


def write_manifest(store: Path, manifest: Dict[str, Any]) -> Path:
    """Store one manifest artifact under its own ui_map/build identity."""
    store.mkdir(parents=True, exist_ok=True)
    destination = _artifact_path(store, manifest["ui_map"], manifest["build"])
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return destination


def load_manifest(store: Path, *, ui_map: str, build: str) -> Dict[str, Any]:
    """Read one stored manifest by exact identity.

    An identity that is not stored yields ``manifest-missing``.  The current
    artifact never stands in for a different version, because the caller's
    ui_map and build both address the file.
    """
    source = _artifact_path(store, ui_map, build)
    if not source.is_file():
        return {"outcome": "manifest-missing", "ui_map": ui_map, "build": build}
    return {
        "outcome": "found",
        "manifest": json.loads(source.read_text(encoding="utf-8")),
    }


def locate_source(manifest: Dict[str, Any], ref: str, *, root: Path) -> Dict[str, Any]:
    """Locate the code declaration behind one reference.

    The recorded content digest is verified before a hit is reported.  When the
    file changed or disappeared the outcome is ``source-mismatch``: the
    historical provenance is still returned as a hint, but no claim is made
    about a precise location in the current source.  Line numbers are
    deliberately absent, since they drift.
    """
    for entry in manifest["refs"]:
        if entry["ref"] != ref:
            continue
        anchor = entry["source"]
        candidate = root / anchor["repo_path"]
        provenance = {
            "ref": ref,
            "repo_path": anchor["repo_path"],
            "symbol": anchor["symbol"],
            "declared_digest": anchor["content_digest"],
        }
        try:
            content = candidate.read_bytes()
        except OSError:
            return dict(provenance, outcome="source-mismatch", reason="source-unreadable")
        if hashlib.sha256(content).hexdigest() != anchor["content_digest"]:
            return dict(provenance, outcome="source-mismatch", reason="content-changed")
        return dict(provenance, outcome="found")
    return {"outcome": "not-found", "ref": ref}
