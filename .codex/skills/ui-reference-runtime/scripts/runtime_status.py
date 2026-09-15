#!/usr/bin/env python3
"""Check portable runtime evidence without project or skill imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


SCHEMA = "ui-reference-profile/v1"
RUNTIME_SKILL = "ui-reference-runtime@1"
EVIDENCE_FIELDS = {
    "status",
    "profile_schema",
    "profile_identity",
    "protocol_version",
    "skill",
    "manifest_schema",
    "token_schema",
    "evidence_identity",
    "runtime_adapter",
    "environment",
    "host_capabilities",
    "evidence_kind",
    "browser",
    "browser_version",
    "browser_protocol_version",
    "artifact",
    "mapping_identity",
    "build_identity",
    "source_identity",
    "rendered",
    "resolution",
    "scope",
    "runtime_gates",
    "side_effects",
}
EVIDENCE_KINDS = {
    "source-capability",
    "native",
    "plugin-composed",
    "outer-composed",
    "owner-backed",
}
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+"),
    re.compile(r"(?<![a-z0-9])sk-[a-z0-9]", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])ghp_[a-z0-9]", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])akia[0-9a-z]{8,}", re.IGNORECASE),
)
REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")

RUNTIME_GATES = (
    "dynamic-session",
    "interaction",
    "teardown",
    "coverage-matrix",
)

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
    """A profile does not satisfy the portable handoff contract."""


class EvidenceError(ValueError):
    """Evidence is malformed or contradicts a safety invariant."""


def _reject_duplicate_keys(pairs: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError("profile contains duplicate fields")
        result[key] = value
    return result


def _object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError("{0} must be an object".format(label))
    return value


def _keys(value: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    actual = set(value)
    if actual - expected_set:
        raise ProfileError("{0} contains unknown fields".format(label))
    if expected_set - actual:
        raise ProfileError("{0} omits required fields".format(label))


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


def _looks_like_absolute_path(value: str) -> bool:
    return (
        value.lower().startswith("file://")
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, str):
        return _looks_like_absolute_path(value) or any(
            pattern.search(value) for pattern in SENSITIVE_PATTERNS
        )
    if isinstance(value, dict):
        return any(_contains_sensitive(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sensitive(item) for item in value)
    return False


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


def _validate_profile(raw: Any) -> Dict[str, Any]:
    """Validate the handoff locally so this package remains independently installable."""
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
        ("reference_pattern", "mapping_identity", "build_identity", "source_provenance"),
        "identity",
    )
    for field, value in identity.items():
        _string(value, "identity.{0}".format(field))
    if not REFERENCE_PATTERN.fullmatch(identity["reference_pattern"]):
        raise ProfileError("identity.reference_pattern is not a valid naming pattern")

    _validate_contract(profile["contract"])

    instances = _object(profile["instances"], "instances")
    _keys(instances, ("scope", "handle", "outcomes"), "instances")
    if instances["scope"] != "review-session":
        raise ProfileError("instances.scope must be review-session")
    if instances["handle"] != "random-memory-only":
        raise ProfileError("instances.handle must be random-memory-only")
    _string_list(instances["outcomes"], "instances.outcomes")
    if not {"ambiguous", "unavailable", "expired"} <= set(instances["outcomes"]):
        raise ProfileError("instances.outcomes omits required uncertainty results")

    migration = _object(profile["migration"], "migration")
    _keys(migration, ("policy", "outcomes"), "migration")
    if migration["policy"] != "explicit-only":
        raise ProfileError("migration.policy must be explicit-only")
    _string_list(migration["outcomes"], "migration.outcomes")
    if not {"migrated", "retired", "incompatible"} <= set(migration["outcomes"]):
        raise ProfileError("migration.outcomes omits required lifecycle results")

    token = _object(profile["token"], "token")
    _keys(token, ("max_bytes", "fields"), "token")
    if not isinstance(token["max_bytes"], int) or isinstance(token["max_bytes"], bool):
        raise ProfileError("token.max_bytes must be an integer")
    if token["max_bytes"] <= 0:
        raise ProfileError("token.max_bytes must be positive")
    _string_list(token["fields"], "token.fields")
    required_token_fields = {
        "protocol",
        "reference",
        "mapping_identity",
        "build_identity",
        "viewport",
        "display_state",
    }
    if not required_token_fields <= set(token["fields"]) <= required_token_fields | {"instance"}:
        raise ProfileError("token.fields violates the field whitelist")

    deep_link = _object(profile["deep_link"], "deep_link")
    _keys(deep_link, ("fields", "side_effects"), "deep_link")
    _string_list(deep_link["fields"], "deep_link.fields")
    if set(deep_link["fields"]) != {"mapping_identity", "reference"}:
        raise ProfileError("deep_link.fields must contain locator fields only")
    if deep_link["side_effects"] is not False:
        raise ProfileError("deep links must be side-effect free")

    security = _object(profile["security"], "security")
    _keys(security, ("forbidden_data", "remote_requests", "persistent_storage"), "security")
    _string_list(security["forbidden_data"], "security.forbidden_data")
    if not {"prompt", "event-body", "credential", "absolute-path"} <= set(
        security["forbidden_data"]
    ):
        raise ProfileError("security.forbidden_data omits required privacy boundaries")
    if security["remote_requests"] is not False:
        raise ProfileError("review protocol must not require remote requests")
    if security["persistent_storage"] is not False:
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
    _string_list(host["capabilities"], "host.capabilities")
    required_capabilities = {
        "rendered-surface",
        "manifest-artifact",
        "source-provenance",
        "review-session",
        "local-navigation",
    }
    if not required_capabilities <= set(host["capabilities"]):
        raise ProfileError("host.capabilities omits a required capability")
    if host["missing_policy"] != "unknown":
        raise ProfileError("host.missing_policy must be unknown")

    review = _object(profile["review"], "review")
    _keys(
        review,
        ("default", "explicit_enable", "pointer_passthrough", "user_initiated_clipboard", "teardown"),
        "review",
    )
    if review["default"] != "disabled":
        raise ProfileError("review.default must be disabled")
    for field in ("explicit_enable", "pointer_passthrough", "user_initiated_clipboard"):
        if review[field] is not True:
            raise ProfileError("review.{0} must be true".format(field))
    if review["teardown"] != "release-all-resources":
        raise ProfileError("review.teardown must release all resources")

    evidence = _object(profile["evidence"], "evidence")
    _keys(evidence, ("required", "unknown_policy"), "evidence")
    _string_list(evidence["required"], "evidence.required")
    if not {"profile", "artifact", "environment"} <= set(evidence["required"]):
        raise ProfileError("evidence.required omits identity evidence")
    if evidence["unknown_policy"] != "preserve-unknown":
        raise ProfileError("evidence.unknown_policy must preserve-unknown")

    acceptance = _object(profile["acceptance"], "acceptance")
    _keys(acceptance, ("required", "threshold", "unknown_policy"), "acceptance")
    _string_list(acceptance["required"], "acceptance.required")
    if acceptance["threshold"] != "all-required":
        raise ProfileError("acceptance.threshold must be all-required")
    if acceptance["unknown_policy"] != "preserve-unknown":
        raise ProfileError("acceptance.unknown_policy must preserve-unknown")

    if _contains_sensitive(profile):
        raise ProfileError("profile contains a forbidden data marker")
    return profile


def _load_valid_profile(path: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    try:
        raw_bytes = Path(path).read_bytes()
        profile = json.loads(
            raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
        _validate_profile(profile)
    except (OSError, UnicodeError, ValueError, TypeError):
        return None
    return hashlib.sha256(raw_bytes).hexdigest(), profile


def _digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _evidence_content_digest(evidence: Mapping[str, Any]) -> str:
    payload = dict(evidence)
    payload.pop("evidence_identity", None)
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _evidence_string(evidence: Mapping[str, Any], field: str) -> str:
    value = evidence[field]
    if not isinstance(value, str) or not value:
        raise EvidenceError("evidence.{0} must be a non-empty string".format(field))
    return value


def _evidence_count(value: Any, label: str, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise EvidenceError("{0} must be an integer at least {1}".format(label, minimum))
    return value


def _report(
    status: str,
    reason: str,
    *,
    profile_identity: str = "unknown",
    artifact_identity: str = "unknown",
    environment_identity: str = "unknown",
    evidence: Optional[Iterable[str]] = None,
    uncovered_items: Optional[Iterable[str]] = None,
    next_evidence: Optional[Iterable[str]] = None,
    verification: str = "unverified",
    complete: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "reason": reason,
        "profile_identity": profile_identity,
        "artifact_identity": artifact_identity,
        "environment_identity": environment_identity,
        "evidence": sorted(evidence or ()),
        "uncovered_items": sorted(uncovered_items or ()),
        "next_evidence": sorted(next_evidence or ()),
        "owner": "project-maintainer",
        "rollback_path": "discard generated diff/evidence; no project state was changed",
        "verification": verification,
        "complete": complete,
    }
    result.update(extra)
    return result


def _validate_evidence_shape(
    evidence: Mapping[str, Any], profile: Tuple[str, Mapping[str, Any]]
) -> None:
    for field in (
        "status",
        "profile_schema",
        "profile_identity",
        "protocol_version",
        "skill",
        "manifest_schema",
        "token_schema",
        "evidence_identity",
        "runtime_adapter",
        "environment",
        "evidence_kind",
        "browser",
        "browser_version",
        "browser_protocol_version",
        "artifact",
        "mapping_identity",
        "build_identity",
        "source_identity",
        "scope",
        "side_effects",
    ):
        _evidence_string(evidence, field)

    host_capabilities = evidence["host_capabilities"]
    if (
        not isinstance(host_capabilities, list)
        or not host_capabilities
        or any(not isinstance(item, str) or not item for item in host_capabilities)
        or len(set(host_capabilities)) != len(host_capabilities)
    ):
        raise EvidenceError("evidence.host_capabilities must be a unique string list")

    if evidence["profile_schema"] != SCHEMA:
        raise EvidenceError("profile-identity-mismatch")
    if evidence["profile_identity"] != profile[0]:
        raise EvidenceError("profile-identity-mismatch")
    if evidence["protocol_version"] != profile[1]["protocol"]["version"]:
        raise EvidenceError("protocol-identity-mismatch")
    if evidence["skill"] != RUNTIME_SKILL:
        raise EvidenceError("skill-identity-mismatch")
    schemas = profile[1]["contract"]["schemas"]
    if evidence["manifest_schema"] != schemas["manifest"]:
        raise EvidenceError("manifest-schema-mismatch")
    if evidence["token_schema"] != schemas["token"]:
        raise EvidenceError("token-schema-mismatch")
    if not _digest(evidence["evidence_identity"]):
        raise EvidenceError("evidence-identity-invalid")
    if evidence["evidence_identity"] != _evidence_content_digest(evidence):
        raise EvidenceError("evidence-identity-mismatch")
    for field in ("runtime_adapter", "environment"):
        if "@" not in evidence[field] or not evidence[field].rsplit("@", 1)[1]:
            raise EvidenceError("evidence.{0} must carry a version".format(field))
    if evidence["evidence_kind"] not in EVIDENCE_KINDS:
        raise EvidenceError("evidence-kind-invalid")
    if evidence["browser"] not in {"verified", "unknown"}:
        raise EvidenceError("browser-status-invalid")
    if evidence["artifact"] not in {"exact", "missing"}:
        raise EvidenceError("artifact-status-invalid")
    if evidence["source_identity"] not in {"exact", "unknown"}:
        raise EvidenceError("source-identity-invalid")
    if not _digest(evidence["mapping_identity"]) or not _digest(evidence["build_identity"]):
        raise EvidenceError("artifact-identity-invalid")
    if evidence["scope"] not in {"static-closure", "full-runtime"}:
        raise EvidenceError("verification-scope-invalid")
    runtime_gates = evidence["runtime_gates"]
    if not isinstance(runtime_gates, dict) or set(runtime_gates) != set(RUNTIME_GATES):
        raise EvidenceError("runtime-gates-invalid")
    if any(value not in {"verified", "unknown"} for value in runtime_gates.values()):
        raise EvidenceError("runtime-gate-status-invalid")

    rendered = evidence["rendered"]
    if not isinstance(rendered, dict) or set(rendered) != {"declared", "undeclared"}:
        raise EvidenceError("rendered-evidence-invalid")
    _evidence_count(rendered["declared"], "rendered.declared", 1)
    if _evidence_count(rendered["undeclared"], "rendered.undeclared", 0) != 0:
        raise EvidenceError("undeclared-reference-present")

    resolution = evidence["resolution"]
    if not isinstance(resolution, dict) or set(resolution) != {"manifest", "source"}:
        raise EvidenceError("resolution-evidence-invalid")
    for field in ("manifest", "source"):
        if resolution[field] not in {"exact", "unknown"}:
            raise EvidenceError("resolution-is-contradictory")

    if evidence["side_effects"] != "none":
        raise EvidenceError("side-effects-not-zero")
    if evidence["status"] not in {"implemented", "unknown", "HOLD"}:
        raise EvidenceError("status-unsupported")


def check(profile_path: str, evidence: Any) -> Dict[str, Any]:
    loaded = _load_valid_profile(profile_path)
    if loaded is None:
        return _report("HOLD", "profile-missing-or-invalid")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
        return _report("HOLD", "evidence-shape-invalid")
    if _contains_sensitive(evidence):
        return _report("HOLD", "evidence-contains-sensitive-data")

    profile_identity = loaded[0]
    artifact_identity = "{0}/{1}".format(
        evidence.get("mapping_identity", "unknown"),
        evidence.get("build_identity", "unknown"),
    )
    environment_identity = evidence.get("environment", "unknown")

    try:
        _validate_evidence_shape(evidence, loaded)
    except EvidenceError as error:
        return _report(
            "HOLD",
            str(error),
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
        )

    if evidence["browser"] == "unknown":
        return _report(
            "unknown",
            "browser-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=("browser",),
            next_evidence=("verified browser and browser protocol",),
        )
    missing_capabilities = sorted(
        set(loaded[1]["host"]["capabilities"])
        - set(evidence["host_capabilities"])
    )
    if missing_capabilities:
        return _report(
            "unknown",
            "host-capability-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=missing_capabilities,
            next_evidence=[
                "verified host capability: {0}".format(capability)
                for capability in missing_capabilities
            ],
        )
    if (
        evidence["browser_version"] == "unknown"
        or evidence["browser_protocol_version"] == "unknown"
    ):
        return _report(
            "unknown",
            "browser-version-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=("browser-version",),
            next_evidence=("measured browser protocol version",),
        )
    if evidence["artifact"] == "missing":
        return _report(
            "unknown",
            "historical-artifact-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=("historical-artifact",),
            next_evidence=("exact historical manifest artifact",),
        )
    if evidence["source_identity"] == "unknown":
        return _report(
            "unknown",
            "source-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=("source-identity",),
            next_evidence=("exact source content identity",),
        )
    if any(value == "unknown" for value in evidence["resolution"].values()):
        return _report(
            "unknown",
            "resolution-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=("exact-resolution",),
            next_evidence=("exact manifest and source resolution",),
        )
    if evidence["status"] != "implemented":
        return _report(
            evidence["status"],
            "evidence-is-not-complete",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification=evidence["scope"],
            uncovered_items=RUNTIME_GATES if evidence["scope"] == "full-runtime" else (),
            next_evidence=("complete runtime evidence",),
        )

    missing_gates = [
        gate for gate in RUNTIME_GATES if evidence["runtime_gates"][gate] == "unknown"
    ]
    if evidence["scope"] == "full-runtime" and missing_gates:
        return _report(
            "unknown",
            "runtime-gate-evidence-missing",
            profile_identity=profile_identity,
            artifact_identity=artifact_identity,
            environment_identity=environment_identity,
            verification="full-runtime",
            uncovered_items=missing_gates,
            next_evidence=["verified runtime gate: {0}".format(gate) for gate in missing_gates],
        )
    return _report(
        "implemented",
        "full-runtime-verified"
        if evidence["scope"] == "full-runtime"
        else "static-closure-verified",
        profile_identity=profile_identity,
        artifact_identity=artifact_identity,
        environment_identity=environment_identity,
        evidence=("profile", "artifact", "environment", "static-closure"),
        uncovered_items=missing_gates if evidence["scope"] == "static-closure" else (),
        next_evidence=(
            ["verified runtime gate: {0}".format(gate) for gate in missing_gates]
            if evidence["scope"] == "static-closure"
            else []
        ),
        verification=evidence["scope"],
        complete=evidence["scope"] == "full-runtime",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile")
    args = parser.parse_args(argv[1:])
    try:
        evidence = json.load(sys.stdin)
    except (ValueError, TypeError):
        result = {"status": "HOLD", "reason": "evidence-json-invalid"}
    else:
        try:
            result = check(args.profile, evidence)
        except (TypeError, ValueError):
            result = {"status": "HOLD", "reason": "evidence-shape-invalid"}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
