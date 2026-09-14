"""Shared declaration helpers for the view modules.

Each view declares its semantic units in its own module -- that ownership is
the point of the registry. What does not need to exist three times is the
machinery every view uses identically: digesting the declaring module's own
source for its ``SourceAnchor``, and rendering one reference's DOM attributes
as escaped attribute text.

``DISCLOSED_REFS``-style per-view decisions stay in the view modules on
purpose; only the byte-for-byte duplicated plumbing lives here.
"""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Mapping, Any

from .ui_runtime import render_attributes


def module_source_digest(module_path: Path) -> str:
    """Digest one declaring module's own source for its source anchor."""
    return hashlib.sha256(Path(module_path).read_bytes()).hexdigest()


def attribute_text(manifest: Mapping[str, Any], ref: str) -> str:
    """Render one declared reference's DOM attributes as escaped text."""
    rendered = render_attributes(manifest, ref)
    return " ".join(
        '{0}="{1}"'.format(name, html.escape(value, quote=True))
        for name, value in sorted(rendered.items())
    )
