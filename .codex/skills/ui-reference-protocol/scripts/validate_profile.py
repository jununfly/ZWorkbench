#!/usr/bin/env python3
"""Validate and canonicalise a portable UI Reference Protocol Profile.

This command is deliberately independent of ZWorkbench.  The profile is the
explicit handoff between protocol design and runtime implementation skills;
it contains contracts, not project data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA = "ui-reference-profile/v1"
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+"),
    re.compile(r"(?<![a-z0-9])sk-[a-z0-9]", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])ghp_[a-z0-9]", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])akia[0-9a-z]{8,}", re.IGNORECASE),
)
REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

_CONTRACT_FIELDS = {
    "declaration": (
        "reference",
        "semantic_name",
        "accessible_name",
        "presentation",
        "parent",
    ),
    "manifest": (
        "reference",
        "mapping_identity",
        "build_identity",
        "source_provenance",
    ),
    "token": (
        "reference",
        "mapping_identity",
        "build_identity",
        "viewport",
        "display_state",
        "instance",
    ),
    "deep_link": ("reference", "mapping_identity"),
    "source": ("repository_relative_anchor", "symbol", "content_identity"),
}


class ProfileError(ValueError):
    """A profile is not a valid instance of the public contract."""


def _reject_duplicate_keys(pairs: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError("profile contains duplicate fields")
        result[key] = value
    return result


def load_profile(path: str) -> Any:
    """Load profile JSON while preserving the strict duplicate-key contract."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def _keys(value: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual = set(value)
    unknown = actual - expected_set
    missing = expected_set - actual
    if unknown:
        raise ProfileError("{0} contains unknown fields".format(label))
    if missing:
        raise ProfileError("{0} omits required fields".format(label))


def _object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError("{0} must be an object".format(label))
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProfileError("{0} must be a non-empty string".format(label))
    return value


def _string_list(value: Any, label: str) -> List[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ProfileError("{0} must be a non-empty string list".format(label))
    if len(set(value)) != len(value):
        raise ProfileError("{0} must not repeat values".format(label))
    return sorted(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileError("{0} must be a boolean".format(label))
    return value


def _looks_like_absolute_path(value: str) -> bool:
    return (
        value.lower().startswith("file://")
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _reject_sensitive_strings(value: Any) -> None:
    if isinstance(value, str) and (
        _looks_like_absolute_path(value)
        or any(pattern.search(value) for pattern in SENSITIVE_PATTERNS)
    ):
        raise ProfileError("profile contains a forbidden data marker")
    if isinstance(value, dict):
        for nested in value.values():
            _reject_sensitive_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_strings(nested)


def _validate_contract(raw: Any) -> Dict[str, Any]:
    contract = _object(raw, "contract")
    _keys(
        contract,
        ("semantic_scope", "identity_separation", "schemas", "fields", "enums", "lifecycle"),
        "contract",
    )
    semantic_scope = _string_list(contract["semantic_scope"], "contract.semantic_scope")
    identity_separation = _string_list(
        contract["identity_separation"], "contract.identity_separation"
    )
    if set(identity_separation) != {
        "semantic",
        "accessible",
        "presentation",
        "source",
        "mapping",
        "build",
    }:
        raise ProfileError("contract.identity_separation must keep identity domains distinct")

    schemas = _object(contract["schemas"], "contract.schemas")
    _keys(schemas, ("manifest", "token"), "contract.schemas")
    if schemas["manifest"] != "ui-ref-manifest/v1":
        raise ProfileError("contract.schemas.manifest is unsupported")
    if schemas["token"] != "ui-ref/v1":
        raise ProfileError("contract.schemas.token is unsupported")

    fields = _object(contract["fields"], "contract.fields")
    _keys(fields, _CONTRACT_FIELDS, "contract.fields")
    canonical_fields: Dict[str, Dict[str, str]] = {}
    for group, expected in _CONTRACT_FIELDS.items():
        mapping = _object(fields[group], "contract.fields.{0}".format(group))
        _keys(mapping, expected, "contract.fields.{0}".format(group))
        canonical_fields[group] = {
            field: _string(mapping[field], "contract.fields.{0}.{1}".format(group, field))
            for field in expected
        }

    declaration = canonical_fields["declaration"]
    if len(
        {
            declaration["semantic_name"],
            declaration["accessible_name"],
            declaration["presentation"],
        }
    ) != 3:
        raise ProfileError("contract.fields.declaration must separate identity and presentation fields")
    for group in ("manifest", "token"):
        mapping = canonical_fields[group]
        if mapping["reference"] in {
            mapping.get("mapping_identity"),
            mapping.get("build_identity"),
        }:
            raise ProfileError(
                "contract.fields.{0}.mapping_identity collapses reference and identity fields".format(group)
            )

    enums = _object(contract["enums"], "contract.enums")
    _keys(enums, ("viewport", "display_state"), "contract.enums")
    viewport = _string_list(enums["viewport"], "contract.enums.viewport")
    display_state = _string_list(enums["display_state"], "contract.enums.display_state")
    if not {"compact", "wide"} <= set(viewport):
        raise ProfileError("contract.enums.viewport omits compact or wide")
    if not {"normal", "empty", "unknown"} <= set(display_state):
        raise ProfileError("contract.enums.display_state omits a required state")

    lifecycle = _object(contract["lifecycle"], "contract.lifecycle")
    _keys(
        lifecycle,
        ("alias_field", "replacement_field", "retired_field", "compatibility_window"),
        "contract.lifecycle",
    )
    if lifecycle["alias_field"] != "alias_of":
        raise ProfileError("contract.lifecycle.alias_field must be alias_of")
    if lifecycle["replacement_field"] != "replaced_by":
        raise ProfileError("contract.lifecycle.replacement_field must be replaced_by")
    if lifecycle["retired_field"] != "retired":
        raise ProfileError("contract.lifecycle.retired_field must be retired")
    if lifecycle["compatibility_window"] != "one-previous-mapping":
        raise ProfileError("contract.lifecycle.compatibility_window must be explicit")

    return {
        "semantic_scope": semantic_scope,
        "identity_separation": identity_separation,
        "schemas": {"manifest": schemas["manifest"], "token": schemas["token"]},
        "fields": canonical_fields,
        "enums": {"viewport": viewport, "display_state": display_state},
        "lifecycle": {
            "alias_field": lifecycle["alias_field"],
            "replacement_field": lifecycle["replacement_field"],
            "retired_field": lifecycle["retired_field"],
            "compatibility_window": lifecycle["compatibility_window"],
        },
    }
def validate_profile(raw: Any) -> Dict[str, Any]:
    profile = _object(raw, "profile")
    _keys(
        profile,
        (
            "schema",
            "protocol",
            "identity",
            "contract",
            "instances",
            "migration",
            "token",
            "deep_link",
            "security",
            "trust",
            "host",
            "review",
            "evidence",
            "acceptance",
        ),
        "profile",
    )
    if profile["schema"] != SCHEMA:
        raise ProfileError("profile schema is unsupported")

    protocol = _object(profile["protocol"], "protocol")
    _keys(protocol, ("name", "version"), "protocol")
    _string(protocol["name"], "protocol.name")
    _string(protocol["version"], "protocol.version")

    identity = _object(profile["identity"], "identity")
    _keys(
        identity,
        (
            "reference_pattern",
            "mapping_identity",
            "build_identity",
            "source_provenance",
        ),
        "identity",
    )
    for field in identity:
        _string(identity[field], "identity.{0}".format(field))
    if not REFERENCE_PATTERN.fullmatch(identity["reference_pattern"]):
        raise ProfileError("identity.reference_pattern is not a valid naming pattern")

    contract = _validate_contract(profile["contract"])

    instances = _object(profile["instances"], "instances")
    _keys(instances, ("scope", "handle", "outcomes"), "instances")
    if instances["scope"] != "review-session":
        raise ProfileError("instances.scope must be review-session")
    if instances["handle"] != "random-memory-only":
        raise ProfileError("instances.handle must be random-memory-only")
    instance_outcomes = _string_list(instances["outcomes"], "instances.outcomes")
    if not {"ambiguous", "unavailable", "expired"} <= set(instance_outcomes):
        raise ProfileError("instances.outcomes omits required uncertainty results")

    migration = _object(profile["migration"], "migration")
    _keys(migration, ("policy", "outcomes"), "migration")
    if migration["policy"] != "explicit-only":
        raise ProfileError("migration.policy must be explicit-only")
    migration_outcomes = _string_list(migration["outcomes"], "migration.outcomes")
    if not {"migrated", "retired", "incompatible"} <= set(migration_outcomes):
        raise ProfileError("migration.outcomes omits required lifecycle results")

    token = _object(profile["token"], "token")
    _keys(token, ("max_bytes", "fields"), "token")
    if not isinstance(token["max_bytes"], int) or isinstance(token["max_bytes"], bool):
        raise ProfileError("token.max_bytes must be an integer")
    if token["max_bytes"] <= 0:
        raise ProfileError("token.max_bytes must be positive")
    token_fields = _string_list(token["fields"], "token.fields")
    required_token_fields = {
        "protocol",
        "reference",
        "mapping_identity",
        "build_identity",
        "viewport",
        "display_state",
    }
    allowed_token_fields = required_token_fields | {"instance"}
    if not required_token_fields <= set(token_fields) <= allowed_token_fields:
        raise ProfileError("token.fields violates the field whitelist")

    deep_link = _object(profile["deep_link"], "deep_link")
    _keys(deep_link, ("fields", "side_effects"), "deep_link")
    if _string_list(deep_link["fields"], "deep_link.fields") != [
        "mapping_identity",
        "reference",
    ]:
        raise ProfileError("deep_link.fields must contain locator fields only")
    if _boolean(deep_link["side_effects"], "deep_link.side_effects"):
        raise ProfileError("deep links must be side-effect free")

    security = _object(profile["security"], "security")
    _keys(
        security,
        ("forbidden_data", "remote_requests", "persistent_storage"),
        "security",
    )
    forbidden_data = _string_list(security["forbidden_data"], "security.forbidden_data")
    if not {"prompt", "event-body", "credential", "absolute-path"} <= set(
        forbidden_data
    ):
        raise ProfileError("security.forbidden_data omits required privacy boundaries")
    if _boolean(security["remote_requests"], "security.remote_requests"):
        raise ProfileError("review protocol must not require remote requests")
    if _boolean(security["persistent_storage"], "security.persistent_storage"):
        raise ProfileError("review protocol must not require persistent storage")

    trust = _object(profile["trust"], "trust")
    _keys(trust, ("token_role", "state_owner", "review_state", "effects"), "trust")
    if trust["token_role"] != "locator-only":
        raise ProfileError("trust.token_role must be locator-only")
    if trust["state_owner"] != "project-owned":
        raise ProfileError("trust.state_owner must remain project-owned")
    if trust["review_state"] != "ephemeral":
        raise ProfileError("trust.review_state must be ephemeral")
    if trust["effects"] != "none":
        raise ProfileError("trust.effects must be none")

    host = _object(profile["host"], "host")
    _keys(host, ("capabilities", "missing_policy"), "host")
    capabilities = _string_list(host["capabilities"], "host.capabilities")
    required_capabilities = {
        "rendered-surface",
        "manifest-artifact",
        "source-provenance",
        "review-session",
        "local-navigation",
    }
    if not required_capabilities <= set(capabilities):
        raise ProfileError("host.capabilities omits a required capability")
    if host["missing_policy"] != "unknown":
        raise ProfileError("host.missing_policy must be unknown")

    review = _object(profile["review"], "review")
    _keys(
        review,
        (
            "default",
            "explicit_enable",
            "pointer_passthrough",
            "user_initiated_clipboard",
            "teardown",
        ),
        "review",
    )
    if review["default"] != "disabled":
        raise ProfileError("review.default must be disabled")
    for field in ("explicit_enable", "pointer_passthrough", "user_initiated_clipboard"):
        if not _boolean(review[field], "review.{0}".format(field)):
            raise ProfileError("review.{0} must be true".format(field))
    if review["teardown"] != "release-all-resources":
        raise ProfileError("review.teardown must release all resources")

    evidence = _object(profile["evidence"], "evidence")
    _keys(evidence, ("required", "unknown_policy"), "evidence")
    evidence_required = _string_list(evidence["required"], "evidence.required")
    if not {"profile", "artifact", "environment"} <= set(evidence_required):
        raise ProfileError("evidence.required omits identity evidence")
    if evidence["unknown_policy"] != "preserve-unknown":
        raise ProfileError("evidence.unknown_policy must preserve-unknown")

    acceptance = _object(profile["acceptance"], "acceptance")
    _keys(acceptance, ("required", "threshold", "unknown_policy"), "acceptance")
    acceptance_required = _string_list(
        acceptance["required"], "acceptance.required"
    )
    if acceptance["threshold"] != "all-required":
        raise ProfileError("acceptance.threshold must be all-required")
    if acceptance["unknown_policy"] != "preserve-unknown":
        raise ProfileError("acceptance.unknown_policy must preserve-unknown")

    _reject_sensitive_strings(profile)
    return {
        "schema": SCHEMA,
        "protocol": {"name": protocol["name"], "version": protocol["version"]},
        "identity": {field: identity[field] for field in sorted(identity)},
        "contract": contract,
        "instances": {
            "scope": instances["scope"],
            "handle": instances["handle"],
            "outcomes": instance_outcomes,
        },
        "migration": {"policy": migration["policy"], "outcomes": migration_outcomes},
        "token": {"max_bytes": token["max_bytes"], "fields": token_fields},
        "deep_link": {"fields": ["mapping_identity", "reference"], "side_effects": False},
        "security": {
            "forbidden_data": forbidden_data,
            "remote_requests": False,
            "persistent_storage": False,
        },
        "trust": {
            "token_role": trust["token_role"],
            "state_owner": trust["state_owner"],
            "review_state": trust["review_state"],
            "effects": trust["effects"],
        },
        "host": {
            "capabilities": capabilities,
            "missing_policy": host["missing_policy"],
        },
        "review": {
            "default": review["default"],
            "explicit_enable": True,
            "pointer_passthrough": True,
            "user_initiated_clipboard": True,
            "teardown": review["teardown"],
        },
        "evidence": {
            "required": evidence_required,
            "unknown_policy": evidence["unknown_policy"],
        },
        "acceptance": {
            "required": acceptance_required,
            "threshold": acceptance["threshold"],
            "unknown_policy": acceptance["unknown_policy"],
        },
    }


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_profile.py PROFILE.json", file=sys.stderr)
        return 2
    try:
        raw = load_profile(argv[1])
        canonical = validate_profile(raw)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("profile rejected: {0}".format(error), file=sys.stderr)
        return 1
    print(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
