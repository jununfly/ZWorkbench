#!/usr/bin/env python3
"""Validate the declaration graph consumed by a UI Reference manifest build."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping


SCHEMA = "ui-reference-declarations/v1"
REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")
MAX_REFERENCE_LENGTH = 128
DECLARATION_FIELDS = ("ref", "parent", "alias_of", "retired", "replaced_by")


class DeclarationError(ValueError):
    """A declaration graph cannot produce an unambiguous manifest."""


def _reject_duplicate_keys(pairs: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeclarationError("document contains duplicate fields")
        result[key] = value
    return result


def _object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise DeclarationError("{0} must be an object".format(label))
    return value


def _keys(value: Mapping[str, Any], expected: List[str], label: str) -> None:
    actual = set(value)
    expected_set = set(expected)
    if actual - expected_set:
        raise DeclarationError("{0} contains unknown fields".format(label))
    if expected_set - actual:
        raise DeclarationError("{0} omits required fields".format(label))


def _reference(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_REFERENCE_LENGTH
        or REFERENCE_PATTERN.fullmatch(value) is None
    ):
        raise DeclarationError("{0} violates the reference naming contract".format(label))
    return value


def _optional_reference(value: Any, label: str) -> Any:
    if value is None:
        return None
    return _reference(value, label)


def _aliases(value: Any, label: str) -> List[str]:
    if not isinstance(value, list):
        raise DeclarationError("{0} must be a list".format(label))
    aliases = [_reference(item, "{0}[]".format(label)) for item in value]
    if len(set(aliases)) != len(aliases):
        raise DeclarationError("{0} must not repeat values".format(label))
    return sorted(aliases)


def _validate_graph(raw: Any) -> Dict[str, Any]:
    document = _object(raw, "document")
    _keys(document, ["declarations"], "document")
    raw_declarations = document["declarations"]
    if not isinstance(raw_declarations, list) or not raw_declarations:
        raise DeclarationError("declarations must be a non-empty list")

    declarations: Dict[str, Dict[str, Any]] = {}
    for index, raw_entry in enumerate(raw_declarations):
        entry = _object(raw_entry, "declarations[{0}]".format(index))
        _keys(entry, list(DECLARATION_FIELDS), "declarations[{0}]".format(index))
        ref = _reference(entry["ref"], "declarations[{0}].ref".format(index))
        if ref in declarations:
            raise DeclarationError("duplicate declaration for ref {0!r}".format(ref))
        parent = _optional_reference(
            entry["parent"], "declarations[{0}].parent".format(index)
        )
        alias_of = _aliases(entry["alias_of"], "declarations[{0}].alias_of".format(index))
        if not isinstance(entry["retired"], bool):
            raise DeclarationError("declarations[{0}].retired must be a boolean".format(index))
        replaced_by = _optional_reference(
            entry["replaced_by"], "declarations[{0}].replaced_by".format(index)
        )
        if replaced_by is not None and not entry["retired"]:
            raise DeclarationError(
                "declarations[{0}].replaced_by requires retired=true".format(index)
            )
        declarations[ref] = {
            "ref": ref,
            "parent": parent,
            "alias_of": alias_of,
            "retired": entry["retired"],
            "replaced_by": replaced_by,
        }

    for ref, entry in declarations.items():
        parent = entry["parent"]
        if parent is None:
            continue
        if parent == ref:
            raise DeclarationError("declaration {0!r} is its own parent".format(ref))
        if parent not in declarations:
            raise DeclarationError(
                "declaration {0!r} names undeclared parent {1!r}".format(ref, parent)
            )
        _reject_cycle(declarations, ref, "parent")

    aliases: Dict[str, str] = {}
    for ref, entry in declarations.items():
        for alias in entry["alias_of"]:
            if alias == ref:
                raise DeclarationError("declaration {0!r} aliases itself".format(ref))
            if alias in declarations:
                raise DeclarationError(
                    "alias {0!r} collides with a live declaration".format(alias)
                )
            if alias in aliases:
                raise DeclarationError(
                    "alias {0!r} is claimed by both {1!r} and {2!r}".format(
                        alias, aliases[alias], ref
                    )
                )
            aliases[alias] = ref

    for ref, entry in declarations.items():
        target = entry["replaced_by"]
        if target is None:
            continue
        if target == ref:
            raise DeclarationError("declaration {0!r} replaces itself".format(ref))
        if target not in declarations:
            raise DeclarationError(
                "declaration {0!r} names undeclared replacement {1!r}".format(ref, target)
            )
        if declarations[target]["retired"]:
            raise DeclarationError(
                "declaration {0!r} names a retired replacement {1!r}".format(ref, target)
            )
        _reject_cycle(declarations, ref, "replaced_by")

    return {"schema": SCHEMA, "declarations": [declarations[ref] for ref in sorted(declarations)]}


def _reject_cycle(declarations: Mapping[str, Mapping[str, Any]], start: str, edge: str) -> None:
    seen = {start}
    cursor = declarations[start][edge]
    while cursor is not None:
        if cursor in seen:
            raise DeclarationError(
                "declaration {0!r} sits in a {1} cycle".format(start, edge)
            )
        seen.add(cursor)
        if cursor not in declarations:
            return
        cursor = declarations[cursor][edge]


def load(path: str) -> Any:
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_declarations.py DECLARATIONS.json", file=sys.stderr)
        return 2
    try:
        canonical = _validate_graph(load(argv[1]))
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        print("declarations rejected: {0}".format(error), file=sys.stderr)
        return 1
    print(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
