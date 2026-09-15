"""Shared evidence builders for the portable UI reference tests."""

import hashlib
import json
from pathlib import Path


def profile_identity(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_evidence(
    profile_path: Path,
    *,
    mapping_identity: str = "a" * 64,
    build_identity: str = "b" * 64,
    status: str = "implemented",
    browser: str = "verified",
    artifact: str = "exact",
    source_identity: str = "exact",
    rendered=None,
    resolution=None,
    side_effects: str = "none",
    browser_version: str = "test-browser@1",
    browser_protocol_version: str = "cdp/1.3",
    protocol_version: str = "1",
    manifest_schema: str = "ui-ref-manifest/v1",
    token_schema: str = "ui-ref/v1",
    host_capabilities=None,
    evidence_kind: str = "outer-composed",
    runtime_adapter: str = "test-adapter@1",
    environment: str = "test-environment@1",
    scope: str = "static-closure",
    runtime_gates=None,
):
    runtime_gates = runtime_gates or {
        "dynamic-session": "unknown",
        "interaction": "unknown",
        "teardown": "unknown",
        "coverage-matrix": "unknown",
    }
    evidence = {
        "status": status,
        "profile_schema": "ui-reference-profile/v1",
        "profile_identity": profile_identity(profile_path),
        "protocol_version": protocol_version,
        "skill": "ui-reference-runtime@1",
        "manifest_schema": manifest_schema,
        "token_schema": token_schema,
        "evidence_identity": "unknown",
        "runtime_adapter": runtime_adapter,
        "environment": environment,
        "host_capabilities": (
            host_capabilities
            if host_capabilities is not None
            else [
                "rendered-surface",
                "manifest-artifact",
                "source-provenance",
                "review-session",
                "local-navigation",
            ]
        ),
        "evidence_kind": evidence_kind,
        "browser": browser,
        "browser_version": browser_version,
        "browser_protocol_version": browser_protocol_version,
        "artifact": artifact,
        "mapping_identity": mapping_identity,
        "build_identity": build_identity,
        "source_identity": source_identity,
        "rendered": rendered or {"declared": 2, "undeclared": 0},
        "resolution": resolution or {"manifest": "exact", "source": "exact"},
        "scope": scope,
        "runtime_gates": runtime_gates,
        "side_effects": side_effects,
    }
    identity_payload = dict(evidence)
    identity_payload.pop("evidence_identity")
    evidence["evidence_identity"] = hashlib.sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return evidence
