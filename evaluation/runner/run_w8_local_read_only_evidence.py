#!/usr/bin/env python3
"""Generate the first W8 local-read-only evidence package.

The package combines the 1-5-4 security controls with one real
case-local-owner backup/restore flow.  It never starts Codex, contacts a
Provider, reads credentials, or performs an external side effect.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, Iterable
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from evaluation.runner.run_w8_local_read_only import (  # noqa: E402
    _inside,
    read_json,
    run_case,
    write_json,
)
from evaluation.runner.run_w8_local_read_only_security import (  # noqa: E402
    network_tripwire,
    run_security_suite,
)


EVIDENCE_SCHEMA = "zworkbench-w8-local-read-only-evidence/v1"
SECRET_PATTERN = re.compile(rb"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,})")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _secret_scan(paths: Iterable[Path]) -> Dict[str, Any]:
    matches = 0
    matching_files = 0
    file_count = 0
    for path in sorted(paths):
        if not path.is_file():
            continue
        file_count += 1
        found = len(SECRET_PATTERN.findall(path.read_bytes()))
        matches += found
        if found:
            matching_files += 1
    return {"file_count": file_count, "matching_files": matching_files, "matches": matches}


def _backup_restore_case(output_dir: Path) -> Dict[str, Any]:
    """Create owner state, export/backup it, then replace a corrupt target."""

    run_result = run_case(output_dir / "run", "success")
    case_dir = Path(run_result["case_root"])
    paths = {
        "case_root": case_dir,
        "workspace": case_dir / "workspace",
        "database": case_dir / "state" / "composition.sqlite3",
        "code_home": case_dir / "codex-home",
        "codex_executable": case_dir / "bin" / "codex",
        "event_log": case_dir / "events" / "codex.jsonl",
    }
    from zworkbench import CompositionOwner

    backup_dir = case_dir / "backup"
    export_path = case_dir / "export" / "owner-state.json"
    restore_target = case_dir / "restore" / "composition.sqlite3"
    run_id = "w8-local-read-only-success-repeat-01"

    with CompositionOwner(paths["database"]) as owner:
        source_snapshot = owner.snapshot()
        source_digest = owner.state_digest()
        export_result = owner.export_state(export_path)
        backup_manifest = owner.backup(backup_dir)
        source_after_backup_digest = owner.state_digest()

    restore_target.parent.mkdir(parents=True, exist_ok=True)
    restore_target.write_bytes(b"corrupt local restore target")
    restore_result = CompositionOwner.restore(backup_dir, restore_target, replace=True)
    restored_database_sha256_at_restore = _sha256(restore_target)
    with CompositionOwner(restore_target) as restored_owner:
        restored_snapshot = restored_owner.snapshot()
        restored_digest = restored_owner.state_digest()

    backup_state = read_json(backup_dir / "state.json")
    backup_manifest_on_disk = read_json(backup_dir / "manifest.json")
    exported_state = read_json(export_path)
    backup_database = backup_dir / "composition.sqlite3"
    restored_database_sha256_after_open = _sha256(restore_target)
    evidence_paths = [path for path in case_dir.rglob("*") if path.is_file()]
    secrets = _secret_scan(evidence_paths)
    snapshot_matches = source_snapshot == restored_snapshot
    paths_inside = all(_inside(case_dir, path) for path in paths.values()) and all(
        _inside(case_dir, path) for path in (backup_dir, export_path, restore_target)
    )

    checks = {
        "fixture_run_passed": run_result["status"] == "pass",
        "run_id_present": any(item.get("run_id") == run_id for item in source_snapshot["runs"]),
        "owner_state_digest_present": bool(source_digest),
        "owner_state_unchanged_by_backup": source_after_backup_digest == source_digest,
        "export_file_present": export_path.is_file(),
        "export_digest_matches": exported_state.get("state_digest") == source_digest and export_result["state_digest"] == source_digest,
        "backup_manifest_present": (backup_dir / "manifest.json").is_file(),
        "backup_database_present": backup_database.is_file(),
        "backup_state_present": (backup_dir / "state.json").is_file(),
        "backup_integrity_ok": backup_manifest_on_disk.get("integrity_check", {}).get("ok") is True,
        "backup_database_digest_matches": backup_manifest_on_disk.get("database_sha256") == _sha256(backup_database),
        "backup_state_digest_matches": backup_manifest_on_disk.get("state_digest") == source_digest and backup_state.get("state_digest") == source_digest,
        "restore_target_replaced": restored_database_sha256_at_restore == _sha256(backup_database) and restore_result["database_sha256"] == restored_database_sha256_at_restore,
        "restore_digest_matches": restored_digest == source_digest and restore_result["state_digest"] == source_digest,
        "restore_snapshot_matches": snapshot_matches,
        "restored_run_completed": any(item.get("run_id") == run_id and item.get("status") == "completed" for item in restored_snapshot["runs"]),
        "effects_zero": len(source_snapshot["effects"]) == 0 and len(restored_snapshot["effects"]) == 0,
        "case_local_paths": paths_inside,
        "secret_pattern_matches_zero": secrets["matches"] == 0,
    }
    summary = {
        "control": "backup_restore",
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "run_id": run_id,
            "source_state_digest": source_digest,
            "restored_state_digest": restored_digest,
            "source_run_status": next((item.get("status") for item in source_snapshot["runs"] if item.get("run_id") == run_id), None),
            "restored_run_status": next((item.get("status") for item in restored_snapshot["runs"] if item.get("run_id") == run_id), None),
            "backup_database_sha256": _sha256(backup_database),
            "restored_database_sha256_at_restore": restored_database_sha256_at_restore,
            "restored_database_sha256_after_open": restored_database_sha256_after_open,
            "effects_count": len(source_snapshot["effects"]),
            "secret_scan": secrets,
        },
        "checks": checks,
        "evidence_files": {
            "export": str(export_path),
            "backup_manifest": str(backup_dir / "manifest.json"),
            "backup_database": str(backup_database),
            "backup_state": str(backup_dir / "state.json"),
            "restore_database": str(restore_target),
        },
        "case_root": str(case_dir),
    }
    write_json(case_dir / "backup-restore-summary.json", summary)
    return summary


def run_evidence_suite(output_dir: Path) -> Dict[str, Any]:
    """Generate and validate all first-slice evidence in one fresh root."""

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise FileExistsError("evidence output directory must be new or empty")
    else:
        output_dir.mkdir(parents=True)

    started_at = datetime.now(timezone.utc).isoformat()
    with network_tripwire() as network_attempts:
        security = run_security_suite(output_dir / "security")
        backup_restore = _backup_restore_case(output_dir / "backup-restore")

    checks = {
        "security_controls_pass": security["status"] == "pass",
        "backup_restore_pass": backup_restore["status"] == "pass",
        "network_attempts_zero": len(network_attempts) == 0,
        "real_credentials_zero": backup_restore["checks"]["secret_pattern_matches_zero"],
        "external_effects_zero": backup_restore["checks"]["effects_zero"],
        "case_local_backup_restore": backup_restore["checks"]["case_local_paths"],
    }
    summary = {
        "schema": EVIDENCE_SCHEMA,
        "fixture_schema": "zworkbench-w8-local-read-only-fixture/v1",
        "security_runner_schema": security["schema"],
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observed": {
            "network_attempts": network_attempts,
            "real_credentials": 0 if checks["real_credentials_zero"] else None,
            "external_side_effects": 0 if checks["external_effects_zero"] else None,
            "security_case_count": security["case_count"],
            "security_passed_case_count": security["passed_case_count"],
            "source_state_digest": backup_restore["observed"]["source_state_digest"],
            "restored_state_digest": backup_restore["observed"]["restored_state_digest"],
        },
        "controls": {
            "security": security,
            "backup_restore": backup_restore,
        },
        "non_claims": [
            "This evidence package validates the W8 local seam only.",
            "It does not prove host-level network isolation or Codex native approval.",
            "It does not validate real Provider remote retention or exit responsibility.",
        ],
    }
    write_json(output_dir / "first-slice-evidence.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh evidence directory; defaults to a temporary directory")
    args = parser.parse_args()
    output_dir = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="w8-local-read-only-evidence-"))
    try:
        summary = run_evidence_suite(output_dir)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
