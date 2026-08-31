"""Command line inspection and lifecycle helpers for the composition owner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .composition import CompositionOwner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZWorkbench composition owner")
    parser.add_argument("--db", required=True, type=Path, help="SQLite composition state path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot", help="print durable owner state")
    export = commands.add_parser("export", help="write portable JSON state")
    export.add_argument("destination", type=Path)
    backup = commands.add_parser("backup", help="create a self-validating backup directory")
    backup.add_argument("destination", type=Path)
    restore = commands.add_parser("restore", help="validate and restore a backup")
    restore.add_argument("backup_directory", type=Path)
    restore.add_argument("--replace", action="store_true", help="explicitly replace an existing target DB")
    return parser


def main(argv: Any = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "restore":
        print(json.dumps(CompositionOwner.restore(args.backup_directory, args.db, replace=args.replace), ensure_ascii=False, indent=2))
        return 0
    with CompositionOwner(args.db) as owner:
        if args.command == "snapshot":
            print(json.dumps(owner.snapshot(), ensure_ascii=False, indent=2))
        elif args.command == "export":
            print(json.dumps(owner.export_state(args.destination), ensure_ascii=False, indent=2))
        elif args.command == "backup":
            print(json.dumps(owner.backup(args.destination), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
