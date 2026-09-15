#!/usr/bin/env python3
"""Report the protocol-design skill's explicit workflow status."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from validate_profile import ProfileError, load_profile, validate_profile


REQUIRED_DISCOVERY_FIELDS = {
    "reference_attribute",
    "renderer",
    "manifest_artifact",
    "source_anchor",
    "host_boundary",
    "browser",
    "local_navigation",
}


def _text_list(value: Any, label: str) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("{0} must be a string list".format(label))
    if len(set(value)) != len(value):
        raise ValueError("{0} must not repeat values".format(label))
    return sorted(value)


def _load_discovery(path: str) -> Dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "conventions",
        "capabilities",
        "assumptions",
        "unknowns",
    }:
        raise ValueError("discovery must contain the declared fields")
    conventions = raw["conventions"]
    if not isinstance(conventions, dict) or set(conventions) != REQUIRED_DISCOVERY_FIELDS:
        raise ValueError("discovery.conventions is incomplete")
    if any(not isinstance(value, str) or not value for value in conventions.values()):
        raise ValueError("discovery.conventions must contain strings")
    return {
        "conventions": dict(sorted(conventions.items())),
        "capabilities": _text_list(raw["capabilities"], "discovery.capabilities"),
        "assumptions": _text_list(raw["assumptions"], "discovery.assumptions"),
        "unknowns": _text_list(raw["unknowns"], "discovery.unknowns"),
    }


def _report(
    *,
    mode: str,
    status: str,
    profile_identity: str = "unknown",
    artifact_identity: str = "unknown",
    environment_identity: str = "unknown",
    evidence: Optional[List[str]] = None,
    uncovered_items: Optional[List[str]] = None,
    next_evidence: Optional[List[str]] = None,
    owner: str = "project-maintainer",
    rollback_path: str = "discard the generated profile/report; no project state was changed",
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "mode": mode,
        "status": status,
        "profile_identity": profile_identity,
        "artifact_identity": artifact_identity,
        "environment_identity": environment_identity,
        "evidence": evidence or [],
        "uncovered_items": uncovered_items or [],
        "next_evidence": next_evidence or [],
        "owner": owner,
        "rollback_path": rollback_path,
    }
    result.update(extra)
    return result


def report(
    mode: str, profile_path: Optional[str], discovery_path: Optional[str] = None
) -> Dict[str, Any]:
    if mode == "design":
        if not profile_path and not discovery_path:
            return _report(
                mode="design",
                status="target",
                next_evidence=["validated project-neutral profile", "project discovery input"],
                unknowns=["project-discovery-input"],
                assumptions=[],
                required_capabilities=[],
            )
        if not profile_path or not Path(profile_path).is_file():
            return _report(
                mode="design",
                status="HOLD",
                next_evidence=["an accepted protocol profile"],
                unknowns=["profile"],
                assumptions=[],
                required_capabilities=[],
            )
        try:
            raw = load_profile(profile_path)
            profile = validate_profile(raw)
            if not discovery_path or not Path(discovery_path).is_file():
                return _report(
                    mode="design",
                    status="unknown",
                    profile_identity=hashlib.sha256(Path(profile_path).read_bytes()).hexdigest(),
                    evidence=["validated-profile"],
                    uncovered_items=["project-conventions"],
                    next_evidence=["project discovery input"],
                    unknowns=["project-discovery-input"],
                    assumptions=[],
                    required_capabilities=profile["host"]["capabilities"],
                )
            discovery = _load_discovery(discovery_path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, ProfileError):
            return _report(
                mode="design",
                status="HOLD",
                next_evidence=["valid profile and discovery input"],
                unknowns=["profile-or-discovery"],
                assumptions=[],
                required_capabilities=[],
            )
        profile_identity = hashlib.sha256(Path(profile_path).read_bytes()).hexdigest()
        required = sorted(set(profile["host"]["capabilities"]))
        missing = sorted(set(required) - set(discovery["capabilities"]))
        unknowns = sorted(set(discovery["unknowns"]) | set(missing))
        return _report(
            mode="design",
            status="unknown" if unknowns else "implemented",
            profile_identity=profile_identity,
            evidence=["validated-profile", "project-discovery"],
            uncovered_items=unknowns,
            next_evidence=["host evidence for {0}".format(item) for item in unknowns],
            assumptions=discovery["assumptions"],
            unknowns=unknowns,
            required_capabilities=required,
            conventions=discovery["conventions"],
        )
    if not profile_path or not Path(profile_path).is_file():
        return _report(
            mode="missing-profile",
            status="HOLD",
            next_evidence=["an accepted protocol profile"],
            uncovered_items=["profile"],
        )
    try:
        raw = load_profile(profile_path)
        profile = validate_profile(raw)
    except (OSError, ValueError, json.JSONDecodeError, ProfileError):
        return _report(
            mode="audit",
            status="HOLD",
            next_evidence=["a profile satisfying the v1 contract"],
            uncovered_items=["profile-contract"],
        )
    return _report(
        mode="audit",
        status="implemented",
        profile_identity=hashlib.sha256(Path(profile_path).read_bytes()).hexdigest(),
        evidence=["validated-profile"],
        next_evidence=["project-specific implementation evidence"],
        required_capabilities=profile["host"]["capabilities"],
    )


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("design", "audit"), required=True)
    parser.add_argument("--profile")
    parser.add_argument("--discovery")
    args = parser.parse_args(argv[1:])
    print(json.dumps(report(args.mode, args.profile, args.discovery), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
