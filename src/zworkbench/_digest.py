"""Shared deterministic digest helpers (canonical JSON + SHA-256).

Single source of truth for the ``sha256:``-prefixed digests used across the
composition owner and the external-process adapters.  Canonical JSON is UTF-8,
key-sorted, and compact (no whitespace) so equal values hash identically
regardless of insertion order.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SHA256_PREFIX = "sha256:"


def canonical_json(value: Any) -> str:
    """Return a stable, key-sorted, compact JSON encoding of ``value``."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    """Return a ``sha256:``-prefixed digest of the canonical JSON of ``value``."""

    encoded = canonical_json(value).encode("utf-8")
    return f"{SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"


def file_digest(path: Path) -> str:
    """Return a ``sha256:``-prefixed digest of the file at ``path``."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{SHA256_PREFIX}{digest.hexdigest()}"
