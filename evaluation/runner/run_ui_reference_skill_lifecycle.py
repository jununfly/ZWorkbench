#!/usr/bin/env python3
"""Install or remove a declared UI reference skill package locally.

This runner is evaluation infrastructure, not a package registry or a product
runtime. It operates on an explicit local package directory and emits a
redacted lifecycle receipt. The implementation deliberately copies only files
listed by ``SKILL-PACKAGE.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Iterable, List


SCHEMA = "ui-ref-skill-lifecycle/v1"
PACKAGE_SCHEMA = "codex-skill-package/v1"
RECEIPT_NAME = ".ui-reference-skill-receipt.json"


class LifecycleError(ValueError):
    """The requested package lifecycle operation is unsafe or invalid."""


def _load_package(root: Path) -> Dict[str, Any]:
    manifest = root / "SKILL-PACKAGE.json"
    try:
        package = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LifecycleError("package manifest is unreadable") from error
    if not isinstance(package, dict):
        raise LifecycleError("package manifest must be an object")
    if package.get("schema") != PACKAGE_SCHEMA:
        raise LifecycleError("package schema is unsupported")
    for field in ("name", "version", "entrypoint", "files", "dependencies", "install"):
        if field not in package:
            raise LifecycleError("package manifest omits " + field)
    if not isinstance(package["name"], str) or not package["name"]:
        raise LifecycleError("package name is invalid")
    if not isinstance(package["version"], str) or not package["version"]:
        raise LifecycleError("package version is invalid")
    files = package["files"]
    if not isinstance(files, list) or not files or any(
        not isinstance(item, str) or not item or Path(item).is_absolute() for item in files
    ):
        raise LifecycleError("package files must be relative paths")
    if len(set(files)) != len(files):
        raise LifecycleError("package files must not repeat values")
    if not isinstance(package["dependencies"], list) or package["dependencies"]:
        raise LifecycleError("package dependencies must be empty")
    source_metadata = package.get("source")
    if (
        not isinstance(source_metadata, dict)
        or source_metadata.get("kind") != "local-declared-files"
        or source_metadata.get("digest_scope") != "declared-files-excluding-manifest"
        or not isinstance(source_metadata.get("content_digest"), str)
    ):
        raise LifecycleError("package source provenance is invalid")
    install = package["install"]
    if not isinstance(install, dict) or install.get("mode") != "copy-declared-files":
        raise LifecycleError("package install mode is unsupported")
    if install.get("rollback") != "remove-installed-directory":
        raise LifecycleError("package rollback is unsupported")
    if any(".." in Path(item).parts for item in files):
        raise LifecycleError("package file escapes its source directory")

    resolved_root = root.resolve()
    for relative in files:
        source_file = root / relative
        try:
            resolved = source_file.resolve(strict=True)
        except OSError as error:
            raise LifecycleError("declared package file is missing") from error
        if resolved != resolved_root / relative or not source_file.is_file():
            raise LifecycleError("declared package file must be a regular local file")
    expected_digest = _declared_files_digest(root, package)
    if source_metadata["content_digest"] != expected_digest:
        raise LifecycleError("package source digest does not match declared files")
    return package


def _target_identity(target: Path) -> str:
    return "sha256:" + hashlib.sha256(str(target.resolve()).encode("utf-8")).hexdigest()


def _declared_files_digest(root: Path, package: Dict[str, Any]) -> str:
    entries = []
    for relative in sorted(package["files"]):
        if relative == "SKILL-PACKAGE.json":
            continue
        entries.append(
            {"path": relative, "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()}
        )
    return hashlib.sha256(
        json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _package_identity(root: Path, package: Dict[str, Any]) -> str:
    return "sha256:" + _declared_files_digest(root, package)


def _receipt(
    operation: str,
    status: str,
    package: Dict[str, Any],
    package_identity: str,
    target: Path,
    residuals: Iterable[str] = (),
    files: Iterable[str] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "operation": operation,
        "status": status,
        "package": {
            "name": package["name"],
            "version": package["version"],
            "identity": package_identity,
        },
        "target_identity": _target_identity(target),
        "files": sorted(files if files is not None else package["files"]),
        "residuals": sorted(residuals),
    }
    result.update(extra)
    return result


def _load_receipt(target: Path, identity_target: Path | None = None) -> Dict[str, Any]:
    receipt_path = target / RECEIPT_NAME
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LifecycleError("installed package receipt is unreadable") from error
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise LifecycleError("installed package receipt is unsupported")
    if receipt.get("status") not in {"installed", "upgraded", "rolled-back"}:
        raise LifecycleError("installed package receipt is not active")
    package = receipt.get("package")
    files = receipt.get("files")
    if (
        not isinstance(package, dict)
        or not isinstance(package.get("name"), str)
        or not isinstance(package.get("version"), str)
        or not isinstance(package.get("identity"), str)
        or not isinstance(files, list)
        or not files
        or any(not isinstance(item, str) or Path(item).is_absolute() for item in files)
        or len(set(files)) != len(files)
    ):
        raise LifecycleError("installed package receipt is malformed")
    identity_target = identity_target or target
    if receipt.get("target_identity") != _target_identity(identity_target):
        raise LifecycleError("installed package receipt targets another directory")
    return receipt


def _copy_files(source_root: Path, files: Iterable[str], target: Path) -> None:
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, destination)


def _active_files(target: Path, files: Iterable[str]) -> List[str]:
    expected = set(files) | {RECEIPT_NAME}
    actual = {
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise LifecycleError("installed target contains undeclared files")
    return sorted(actual)


def install(package_root: Path, target: Path) -> Dict[str, Any]:
    package = _load_package(package_root)
    if target.exists():
        raise LifecycleError("install target already exists")
    package_identity = _package_identity(package_root, package)
    try:
        target.mkdir(parents=True)
        for relative in package["files"]:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package_root / relative, destination)
        receipt = _receipt("install", "installed", package, package_identity, target)
        (target / RECEIPT_NAME).write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, shutil.Error) as error:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        raise LifecycleError("package install failed") from error
    return receipt


def upgrade(package_root: Path, target: Path) -> Dict[str, Any]:
    package = _load_package(package_root)
    if not target.is_dir():
        raise LifecycleError("upgrade target is not an installed skill")
    previous = _load_receipt(target)
    if previous["package"]["name"] != package["name"]:
        raise LifecycleError("upgrade package name does not match installed skill")
    if previous["package"]["version"] == package["version"]:
        raise LifecycleError("upgrade package version is unchanged")
    previous_files = list(previous["files"])
    _active_files(target, previous_files)

    rollback_root = target.parent / ("." + target.name + ".rollback")
    if rollback_root.exists():
        raise LifecycleError("rollback snapshot already exists")
    package_identity = _package_identity(package_root, package)
    rollback_root.mkdir(parents=True)
    try:
        _copy_files(target, previous_files, rollback_root)
        (rollback_root / RECEIPT_NAME).write_text(
            json.dumps(previous, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for relative in previous_files:
            if relative not in package["files"]:
                (target / relative).unlink()
        _copy_files(package_root, package["files"], target)
        receipt = _receipt(
            "upgrade",
            "upgraded",
            package,
            package_identity,
            target,
            rollback={"available": True, "snapshot": "local-target-backup"},
        )
        (target / RECEIPT_NAME).write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, shutil.Error) as error:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        rollback_root.rename(target)
        raise LifecycleError("package upgrade failed and was rolled back") from error
    return receipt


def rollback(target: Path) -> Dict[str, Any]:
    if not target.is_dir():
        raise LifecycleError("rollback target is not an installed skill")
    current = _load_receipt(target)
    rollback_root = target.parent / ("." + target.name + ".rollback")
    if not rollback_root.is_dir() or not current.get("rollback", {}).get("available"):
        raise LifecycleError("rollback snapshot is unavailable")
    previous = _load_receipt(rollback_root, target)
    _active_files(rollback_root, previous["files"])
    temporary_current = target.parent / ("." + target.name + ".rollback-current")
    if temporary_current.exists():
        raise LifecycleError("rollback staging directory already exists")
    try:
        target.rename(temporary_current)
        rollback_root.rename(target)
        receipt = _receipt(
            "rollback",
            "rolled-back",
            previous["package"],
            previous["package"]["identity"],
            target,
            files=previous["files"],
            rollback={"available": False},
        )
        (target / RECEIPT_NAME).write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, shutil.Error) as error:
        if target.exists() and not temporary_current.exists():
            target.rename(rollback_root)
        if temporary_current.exists():
            temporary_current.rename(target)
        raise LifecycleError("package rollback failed") from error
    shutil.rmtree(temporary_current, ignore_errors=True)
    return receipt


def uninstall(target: Path) -> Dict[str, Any]:
    if not target.is_dir():
        raise LifecycleError("uninstall target is not an installed skill")
    current = _load_receipt(target)
    _active_files(target, current["files"])
    rollback_root = target.parent / ("." + target.name + ".rollback")
    if rollback_root.exists():
        previous = _load_receipt(rollback_root, target)
        _active_files(rollback_root, previous["files"])
    package = current["package"]
    receipt = _receipt(
        "uninstall",
        "uninstalled",
        package,
        package["identity"],
        target,
        files=current["files"],
    )
    try:
        shutil.rmtree(target)
        if rollback_root.exists():
            shutil.rmtree(rollback_root)
    except OSError as error:
        raise LifecycleError("package uninstall failed") from error
    residuals = []
    if target.exists():
        residuals.append("target")
    if rollback_root.exists():
        residuals.append("rollback-snapshot")
    if residuals:
        raise LifecycleError("package uninstall left residuals")
    return receipt


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--operation",
        choices=("install", "upgrade", "rollback", "uninstall"),
        required=True,
    )
    parser.add_argument("--package")
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv[1:])
    try:
        if args.operation == "rollback":
            result = rollback(Path(args.target))
        elif args.operation == "uninstall":
            result = uninstall(Path(args.target))
        else:
            if not args.package:
                raise LifecycleError("--package is required for install and upgrade")
            operation = upgrade if args.operation == "upgrade" else install
            result = operation(Path(args.package), Path(args.target))
    except LifecycleError as error:
        result = {
            "schema": SCHEMA,
            "operation": args.operation,
            "status": "HOLD",
            "reason": str(error),
            "residuals": [],
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
