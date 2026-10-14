"""Static guard for ADR 0013 (roadmap 1-1-4).

ZWorkbench's Python runtime is zero third-party dependency (comparison item
C32). The Electron desktop shell legitimately needs Node, so ADR 0013 declares
that a *bounded* deviation: Node lives in ``desktop/`` only, as a build-time
devDependency, and never enters the Python packaging metadata.

A boundary nobody can check silently erodes, so these tests assert the boundary
mechanically:

* ``pyproject.toml`` keeps ``[project].dependencies = []``.
* ``electron`` is a devDependency, never a runtime dependency.
* no Node ecosystem file at the repo root -- ``desktop/`` is the only holder.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DESKTOP_DIR = REPO_ROOT / "desktop"
DESKTOP_PACKAGE_JSON = DESKTOP_DIR / "package.json"


def _project_dependencies(raw: str) -> list[str]:
    """Return the entries of ``[project].dependencies`` from a pyproject file.

    Parsed by hand rather than with ``tomllib`` on purpose: the project still
    declares ``requires-python = ">=3.9"`` and ``tomllib`` only exists from 3.11,
    so importing it would make the guard unrunnable on a supported interpreter.
    """
    lines = raw.splitlines()
    in_project = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if not in_project or not stripped.startswith("dependencies"):
            continue
        value = stripped.split("=", 1)[1].strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
        else:
            # Multi-line array: gather until the closing bracket.
            buffer = value
            for following in lines[index + 1 :]:
                buffer += following.strip()
                if buffer.endswith("]"):
                    break
            inner = buffer[buffer.index("[") + 1 : buffer.rindex("]")]
        return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    raise AssertionError("no [project].dependencies declaration found in pyproject.toml")


class ZeroDependencyGuardTests(unittest.TestCase):
    def test_python_runtime_declares_no_third_party_dependency(self) -> None:
        self.assertTrue(PYPROJECT.is_file(), "pyproject.toml is missing")
        dependencies = _project_dependencies(PYPROJECT.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            dependencies,
            "pyproject.toml must keep dependencies=[] -- ADR 0013 bounds the "
            "Node/Electron deviation to desktop/, the Python core stays pure.",
        )

    def test_electron_is_a_dev_dependency_not_a_runtime_dependency(self) -> None:
        if not DESKTOP_PACKAGE_JSON.is_file():
            self.skipTest("desktop/package.json absent; desktop shell not checked out")
        package = json.loads(DESKTOP_PACKAGE_JSON.read_text(encoding="utf-8"))
        self.assertIn(
            "electron",
            package.get("devDependencies", {}),
            "electron must be a devDependency of desktop/ (build-time only)",
        )
        self.assertNotIn(
            "electron",
            package.get("dependencies", {}),
            "electron must not be a runtime dependency, even of the shell",
        )

    def test_node_ecosystem_is_confined_to_the_desktop_directory(self) -> None:
        self.assertFalse(
            (REPO_ROOT / "package.json").exists(),
            "a root package.json would put Node at the repo root; ADR 0013 "
            "confines it to desktop/",
        )
        self.assertTrue(
            DESKTOP_DIR.is_dir(),
            "desktop/ is expected to exist; if the shell was withdrawn, retire "
            "ADR 0013 with a superseding ADR instead of leaving this guard stale",
        )


if __name__ == "__main__":
    unittest.main()
