#!/usr/bin/env python3
"""Run H3 fixture and real-Codex/loopback Worker coding probes.

The real path launches the installed ``codex-cli 0.139.0`` app-server behind
the H3 Worker wire and points it at a case-local fake loopback Provider.  It
does not use the user's Codex home or credentials, and it never applies a
diff to the repository.  The fixture path remains separate so a failure in
real runtime staging cannot be hidden by a composed probe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_coding" / "v1"
FIXTURE_WORKER = FIXTURE_ROOT / "worker_fixture.py"
CODEX_WORKER = FIXTURE_ROOT / "codex_worker_adapter.py"
FAKE_PROVIDER = REPO_ROOT / "evaluation" / "fixtures" / "w7-codex-c5-c6" / "fake-provider.py"
RUNNER_SCHEMA = "zworkbench-w8-worker-coding-runner/v1"
CODEX_VERSION = "codex-cli 0.139.0"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench import (  # noqa: E402
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


def digest(value: Any) -> str:
    if isinstance(value, Path):
        data = value.read_bytes()
    else:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot(root: Path) -> Dict[str, str]:
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def wait_ready(path: Path, process: subprocess.Popen[bytes], timeout: float = 8.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"fake Provider exited before readiness: {process.returncode}")
        time.sleep(0.05)
    raise TimeoutError("fake Provider readiness timed out")


def stop_process(process: Optional[subprocess.Popen[bytes]], stream: Any = None) -> None:
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    if stream is not None:
        stream.close()


def start_provider(case_root: Path) -> Dict[str, Any]:
    ready = case_root / "provider.ready.json"
    requests = case_root / "provider-requests.jsonl"
    stderr_path = case_root / "provider-stderr.log"
    stderr = stderr_path.open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            str(FAKE_PROVIDER),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--provider-id",
            "h3-loopback-fake",
            "--mode",
            "normal",
            "--capabilities",
            "tool_calls,streaming,structured_output",
            "--emit-tool",
            "--command",
            "printf fixture-ok",
            "--request-log",
            str(requests),
            "--ready-file",
            str(ready),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        start_new_session=True,
    )
    info = wait_ready(ready, process)
    return {
        "process": process,
        "stderr": stderr,
        "endpoint": f"http://127.0.0.1:{info['port']}",
        "requests": requests,
    }


def bridge_for(owner: CompositionOwner, case_root: Path, worker: Path, worker_args: tuple[str, ...], provider_endpoint: str) -> WorkerBridge:
    workspace_digest = digest({"kind": "case-local", "relative_path": "workspace"})
    return WorkerBridge(
        owner,
        sys.executable,
        case_root,
        worker_args=(str(worker), *worker_args),
        worker_artifact_identity=ComponentIdentity(
            name="codex-worker" if worker == CODEX_WORKER else "codex-worker-fixture",
            version=CODEX_VERSION if worker == CODEX_WORKER else "1.0.0",
            digest=digest(worker),
            source="evaluation/fixtures/w8_worker_coding/v1",
        ),
        worker_schema_identity=ComponentIdentity(
            name="zworkbench.worker",
            version="v1",
            digest=digest("zworkbench.worker.v1"),
            source="src/zworkbench/worker_contract.py",
        ),
        provider_identity=ProviderIdentity(
            provider="h3-loopback-fake",
            model="fake-model",
            endpoint=provider_endpoint,
            transport="loopback-only",
        ),
        policy_digest=digest("h3-read-only-policy"),
        environment_digest=digest({"runner": RUNNER_SCHEMA, "codex": CODEX_VERSION, "workspace": workspace_digest}),
        workspace_digest=workspace_digest,
    )


def run_case(output_dir: Path, name: str, worker: Path, worker_args: tuple[str, ...], real_codex: bool) -> Dict[str, Any]:
    case_root = output_dir / name
    case_root.mkdir(parents=True, exist_ok=False)
    workspace = case_root / "workspace"
    artifact_root = case_root / "evidence" / "artifacts"
    workspace.mkdir()
    artifact_root.mkdir(parents=True)
    (workspace / "README.md").write_text("fixture project\n", encoding="utf-8")
    provider = None
    error = None
    execution = None
    before_workspace = snapshot(workspace)
    try:
        provider = start_provider(case_root)
        with CompositionOwner(case_root / "state" / "composition.sqlite3") as owner:
            owner.create_run("parent-1", "dsh.bootstrap", {"operation": "read-only-coding"})
            owner.start_run("parent-1")
            args = worker_args + (("--provider-endpoint", provider["endpoint"]) if real_codex else ())
            bridge = bridge_for(owner, case_root, worker, args, provider["endpoint"])
            try:
                execution = bridge.read_only_coding(
                    "parent-1",
                    child_run_id="child-1",
                    attempt_id="attempt-1",
                    dsh_session_id="dsh-session-1",
                    dsh_turn_id="dsh-turn-1",
                    prompt="Inspect README.md, run the read-only test probe, and return fixture-ok. Do not edit files.",
                    artifact_root=artifact_root,
                    timeout=30.0,
                )
            except WorkerBridgeError as exc:
                error = {"type": type(exc).__name__, "code": exc.code}
            finally:
                bridge.close()
            parent = owner.get_run("parent-1")
            child = owner.get_run("child-1")
            child_kinds = sorted(item["kind"] for item in child["results"])
            artifacts = (execution.artifacts if execution is not None else {})
            checks = {
                "execution_completed": execution is not None and execution.status == "completed",
                "codex_runtime_identity": (not real_codex) or (execution is not None and execution.worker_artifact_identity.version == CODEX_VERSION),
                "semantic_result_present": execution is not None and execution.semantic_result.get("status") == "completed",
                "parent_remains_running": parent["status"] == "running",
                "child_completed": child["status"] == "completed",
                "workspace_unchanged": snapshot(workspace) == before_workspace,
                "artifact_digests_verified": bool(artifacts) and all(
                    digest(artifact_root / descriptor["path"]) == descriptor["digest"]
                    for descriptor in artifacts.values()
                ),
                "effects_zero": not parent["effects"] and not child["effects"],
                "provider_requests_loopback_only": (provider["requests"].is_file() and provider["requests"].read_text(encoding="utf-8").strip() != "")
                if real_codex
                else (not provider["requests"].exists() or provider["requests"].read_text(encoding="utf-8").strip() == ""),
                "worker_process_absent": bridge.process is None,
                "semantic_result_recorded": "semantic" in child_kinds and "worker.coding" in child_kinds,
            }
            observed = {
                "error": error,
                "parent_status": parent["status"],
                "child_status": child["status"],
                "child_result_kinds": child_kinds,
                "semantic_text": execution.semantic_result.get("text") if execution else None,
                "artifact_names": sorted(artifacts),
                "provider_request_count": len(provider["requests"].read_text(encoding="utf-8").splitlines()) if provider["requests"].is_file() else 0,
            }
    finally:
        stop_process(provider.get("process") if provider else None, provider.get("stderr") if provider else None)
    summary = {
        "schema": RUNNER_SCHEMA,
        "evidence_level": "real-Codex-runtime + loopback-Provider" if real_codex else "fixture-composed",
        "scenario": name,
        "status": "pass" if all(checks.values()) else "unknown/stop",
        "observed": observed,
        "checks": checks,
        "non_claims": [
            "This does not prove compatibility with a real remote Provider or production credentials.",
            "This does not prove H4 lifecycle/recovery or H5 replay.",
        ],
    }
    write_json(case_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="new or empty output directory")
    parser.add_argument("--codex", type=Path, default=Path("/opt/homebrew/bin/codex"))
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args()
    output_dir = args.output.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit("H3 output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [run_case(output_dir, "fixture", FIXTURE_WORKER, (), False)]
    if not args.fixture_only:
        if not args.codex.is_file():
            raise SystemExit(f"Codex executable not found: {args.codex}")
        cases.append(run_case(output_dir, "real-codex-loopback", CODEX_WORKER, ("--codex", str(args.codex.resolve())), True))
    summary = {
        "schema": RUNNER_SCHEMA,
        "status": "pass" if all(case["status"] == "pass" for case in cases) else "unknown/stop",
        "cases_passed": sum(case["status"] == "pass" for case in cases),
        "cases_total": len(cases),
        "codex_runtime": CODEX_VERSION if not args.fixture_only else "not-run",
        "cases": cases,
        "real_provider_compatibility": "HOLD: only fake loopback Provider is exercised",
        "h4_h5_status": "HOLD: lifecycle/recovery and evidence/replay are separate roadmap nodes",
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
