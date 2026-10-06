"""The build entry point that turns view declarations into stored artifacts.

Before this existed the manifest was only ever written by tests, so the claim
that it is derived from the build had no mechanism behind it. Here one
invocation digests the declaring sources into a single receipt, generates every
view manifest against that receipt, and stores each under its own identity.

One receipt covers all views on purpose. A receipt answers "which source
snapshot produced this?", and the answer is a property of the tree, not of one
module: a change in a shared helper must move the identity of every view it can
affect, even when that view's own file is untouched.

The build only reads sources and writes artifacts. It starts no run, reaches no
owner storage and reports no acceptance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from .ui_home import home_manifest
from .ui_manifest import build_receipt, write_manifest
from .ui_record_view import record_manifest
from .ui_task_detail import task_detail_manifest


#: The sources whose content defines a build identity: the declaring modules
#: plus the shared machinery their declarations depend on.
ROOT_SOURCES: Tuple[str, ...] = (
    "src/zworkbench/ui_home.py",
    "src/zworkbench/ui_task_detail.py",
    "src/zworkbench/ui_record_view.py",
    "src/zworkbench/ui_ref.py",
    "src/zworkbench/ui_runtime.py",
    "src/zworkbench/ui_declare.py",
)

#: View name -> the factory that generates its manifest for a given build.
VIEW_MANIFESTS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "home": home_manifest,
    "task-detail": task_detail_manifest,
    "record-view": record_manifest,
}


def served_source_root_and_sources() -> Tuple[Path, Tuple[str, ...]]:
    """Resolve the package directory and effective source paths.

    The build receipt is computed from the declaring modules.  Those modules
    live at two different places depending on how the package is consumed:

    * **source checkout** -- ``<repo>/src/zworkbench/*.py``; ``ROOT_SOURCES``
      already carries the ``src/zworkbench/`` prefix, and the receipt root is
      the repository root two levels above the package.
    * **installed wheel** -- ``<site-packages>/zworkbench/*.py``; the prefix is
      dropped and the receipt root becomes the package directory itself.

    The discriminator is the package's parent directory name, not the presence
    of ``ui_declare.py`` (which exists in both layouts): a checkout keeps the
    package under a ``src/`` directory, while an installed wheel does not.
    Returning both halves keeps ``build_receipt`` layout-agnostic so the UI
    host serves identically from a checkout or from ``pip install``.
    """
    pkg = Path(__file__).resolve().parent  # .../zworkbench
    if pkg.parent.name == "src":
        # Source checkout: repo root is two levels above src/zworkbench.
        return pkg.parent.parent, ROOT_SOURCES
    # Installed wheel (or any flat layout): modules sit directly under pkg.
    prefix = "src/zworkbench/"
    sources = tuple(
        s[len(prefix) :] if s.startswith(prefix) else s for s in ROOT_SOURCES
    )
    return pkg, sources


def build_ui_artifacts(root: Path, store: Path) -> Dict[str, Any]:
    """Generate and store one manifest per view against a shared receipt.

    The source paths are layout-relative: when ``root`` is a source checkout
    (``<repo>/src/zworkbench`` exists) the ``ROOT_SOURCES`` prefix is kept; when
    ``root`` is an installed wheel (modules sit directly under the package) the
    prefix is dropped.  This keeps ``ui-build`` working from either layout.
    """
    root = Path(root)
    prefix = "src/zworkbench/"
    if (root / "ui_declare.py").exists():
        sources: Tuple[str, ...] = tuple(
            s[len(prefix) :] if s.startswith(prefix) else s for s in ROOT_SOURCES
        )
    else:
        sources = ROOT_SOURCES
    receipt = build_receipt(root, sources)
    views: Dict[str, Dict[str, str]] = {}
    for view, manifest_of in VIEW_MANIFESTS.items():
        manifest = manifest_of(build=receipt["build"])
        write_manifest(Path(store), manifest)
        views[view] = {"ui_map": manifest["ui_map"], "build": manifest["build"]}
    return {"receipt": receipt, "views": views}
