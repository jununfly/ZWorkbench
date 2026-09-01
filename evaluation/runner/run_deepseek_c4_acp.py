#!/usr/bin/env python3
"""Probe DeepSeek Harness ACP persistence and interruption semantics.

This is an acceptance/evaluation runner, not ZWorkbench product code.  It
drives the fixed DeepSeek source checkout over ACP stdio, using only the W6
loopback fake Provider and a case-local DSH_HOME.  The probe deliberately
reports the narrow ACP lifecycle facts separately from the full W6 C4 gate:
ACP session persistence/resume is candidate evidence; a generic durable effect
ledger, replay contract, and every W6 injection point are not inferred from it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
MANIFEST_PATH = REPO_ROOT / "evaluation" / "candidates" / "deepseek" / "manifest.json"
SCHEMA = "zworkbench-deepseek-c4-acp/v1"
PROMPT = "C4 ACP probe. Reply exactly fixture-ok and stop. Do not use tools."

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(command: list[str], *, timeout: float = 30.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
            "timed_out": False,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "returncode": None,
            "stdout": (error.stdout or "")[-12000:] if isinstance(error.stdout, str) else "",
            "stderr": (error.stderr or "")[-12000:] if isinstance(error.stderr, str) else "",
            "timed_out": True,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }


class AcpProcess:
    """Small line-oriented ACP client for the candidate's stdio server."""

    def __init__(self, *, entrypoint: Path, project: Path, environment: dict[str, str], transcript: Path):
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("node is not installed")
        self.process = subprocess.Popen(
            [node, str(entrypoint), "--profile", "acp"],
            cwd=project,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.transcript = transcript
        self.transcript.parent.mkdir(parents=True, exist_ok=True)
        self.transcript_handle = transcript.open("w", encoding="utf-8")
        self.next_id = 1
        self.notifications: list[dict[str, Any]] = []

    def send(self, method: str, params: dict[str, Any], request_id: int | None = None) -> int:
        if request_id is None:
            request_id = self.next_id
            self.next_id += 1
        elif request_id >= self.next_id:
            self.next_id = request_id + 1
        frame = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        self._record("client", frame)
        return request_id

    def send_notification(self, method: str, params: dict[str, Any]) -> None:
        frame = {"jsonrpc": "2.0", "method": method, "params": params}
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        self._record("client", frame)

    def read_until(self, request_ids: set[int], timeout: float = 30.0) -> dict[int, dict[str, Any]]:
        responses: dict[int, dict[str, Any]] = {}
        deadline = time.monotonic() + timeout
        assert self.process.stdout is not None
        while request_ids - responses.keys():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"ACP response timeout; pending={sorted(request_ids - responses.keys())}")
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                raise TimeoutError(f"ACP response timeout; pending={sorted(request_ids - responses.keys())}")
            line = self.process.stdout.readline()
            if line == "":
                raise RuntimeError(f"ACP process exited while waiting; returncode={self.process.poll()}")
            try:
                frame = json.loads(line)
            except json.JSONDecodeError as error:
                self._record("server-invalid", {"line": line.rstrip("\n"), "error": str(error)})
                continue
            self._record("server", frame)
            frame_id = frame.get("id")
            if isinstance(frame_id, int) and frame_id in request_ids:
                responses[frame_id] = frame
            elif frame.get("method") == "session/update":
                self.notifications.append(frame)
        return responses

    def request(self, method: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        request_id = self.send(method, params)
        return self.read_until({request_id}, timeout)[request_id]

    def close_session(self, session_id: str) -> dict[str, Any]:
        return self.request("session/close", {"sessionId": session_id})

    def close(self) -> dict[str, Any]:
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        return self._finish_process()

    def kill(self) -> dict[str, Any]:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        return self._finish_process()

    def _record(self, side: str, frame: dict[str, Any]) -> None:
        self.transcript_handle.write(json.dumps({"side": side, "frame": frame}, ensure_ascii=False, sort_keys=True) + "\n")
        self.transcript_handle.flush()

    def _finish_process(self) -> dict[str, Any]:
        if not self.transcript_handle.closed:
            self.transcript_handle.close()
        stderr = ""
        if self.process.stderr is not None:
            try:
                stderr = self.process.stderr.read()[-12000:]
            except OSError:
                stderr = ""
        return {"returncode": self.process.returncode, "stderr": stderr}


def environment_for(home: Path, base_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "DSH_HOME": str(home),
        "DSH_TELEMETRY_DISABLED": "1",
        "DEEPSEEK_API_KEY": "w6-fake-key",
        "DEEPSEEK_BASE_URL": base_url + "/v1",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    })
    return environment


def response_ok(frame: dict[str, Any]) -> bool:
    return "result" in frame and "error" not in frame


def session_paths(home: Path) -> list[Path]:
    return sorted(home.rglob("session.jsonl.zstd"))


def decode_session(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    result = subprocess.run(["zstd", "-d", "-c", str(path)], capture_output=True, check=False, timeout=20)
    if result.returncode != 0:
        return [], [result.stderr.decode("utf-8", errors="replace")[-2000:]]
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid.append(line[-2000:])
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            invalid.append(line[-2000:])
    return events, invalid


def wait_for_request(request_path: Path, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if request_path.is_file() and request_path.read_text(encoding="utf-8").strip():
            return True
        time.sleep(0.05)
    return False


def start_process(entrypoint: Path, project: Path, home: Path, base_url: str, transcript: Path) -> AcpProcess:
    return AcpProcess(
        entrypoint=entrypoint,
        project=project,
        environment=environment_for(home, base_url),
        transcript=transcript,
    )


def initialize_and_new(agent: AcpProcess, project: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    initialize = agent.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    created = agent.request("session/new", {"cwd": str(project), "mcpServers": []})
    session_id = created.get("result", {}).get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"session/new did not return a session id: {created}")
    return session_id, initialize, created


def prompt(agent: AcpProcess, session_id: str, request_id: int | None = None) -> dict[str, Any]:
    if request_id is None:
        return agent.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": PROMPT}]})
    agent.send("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": PROMPT}]}, request_id)
    return {}


def run_clean_resume(entrypoint: Path, case_dir: Path, repeat: int, server: dict[str, Any]) -> dict[str, Any]:
    project = case_dir / "project"
    shutil.copytree(FIXTURE / "code-project", project)
    home = case_dir / "dsh-home"
    first = start_process(entrypoint, project, home, server["base_url"], case_dir / "first-transcript.jsonl")
    session_id = ""
    first_result: dict[str, Any] = {}
    second_result: dict[str, Any] = {}
    try:
        session_id, initialize, created = initialize_and_new(first, project)
        first_result = prompt(first, session_id)
        closed = first.close_session(session_id)
        first_exit = first.close()
    except Exception:
        first_exit = first.kill()
        raise

    second = start_process(entrypoint, project, home, server["base_url"], case_dir / "second-transcript.jsonl")
    try:
        resumed_list = second.request("session/list", {})
        resumed = second.request("session/resume", {"sessionId": session_id, "cwd": str(project), "mcpServers": []})
        second_result = prompt(second, session_id)
        second_closed = second.close_session(session_id)
        second_exit = second.close()
    except Exception:
        second_exit = second.kill()
        raise

    paths = session_paths(home)
    events, invalid = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    listed_ids = [item.get("sessionId") for item in resumed_list.get("result", {}).get("sessions", [])]
    checks = {
        "initialize_ok": response_ok(initialize),
        "session_new_ok": response_ok(created),
        "first_prompt_completed": first_result.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "first_close_ok": response_ok(closed),
        "first_process_exited": first_exit["returncode"] == 0,
        "session_list_contains_id": session_id in listed_ids,
        "session_resume_ok": response_ok(resumed),
        "resumed_prompt_completed": second_result.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "second_close_ok": response_ok(second_closed),
        "second_process_exited": second_exit["returncode"] == 0,
        "one_persisted_session_log": len(paths) == 1,
        "session_log_decodes": not invalid,
        "session_log_has_events": len(events) > 0,
        "workspace_unchanged": not any(project.rglob("*.created-by-probe")),
    }
    return {
        "scenario": "clean_resume",
        "repeat": repeat,
        "session_id": session_id,
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "session_paths": [str(path) for path in paths],
            "event_count": len(events),
            "event_types": sorted({str(event.get("type")) for event in events}),
            "invalid_session_lines": invalid,
            "provider": {"endpoint": server["base_url"], "transport": "loopback-only"},
        },
    }


def run_cancel_resume(entrypoint: Path, case_dir: Path, repeat: int, timeout_server: dict[str, Any], recovery_server: dict[str, Any]) -> dict[str, Any]:
    project = case_dir / "project"
    shutil.copytree(FIXTURE / "code-project", project)
    home = case_dir / "dsh-home"
    first = start_process(entrypoint, project, home, timeout_server["base_url"], case_dir / "first-transcript.jsonl")
    session_id = ""
    try:
        session_id, initialize, created = initialize_and_new(first, project)
        prompt_id = 3
        prompt(first, session_id, request_id=prompt_id)
        request_seen = wait_for_request(timeout_server["request_path"])
        first.send_notification("session/cancel", {"sessionId": session_id})
        cancel_sent = True
        responses = first.read_until({prompt_id}, timeout=30)
        first_closed = first.close_session(session_id)
        first_exit = first.close()
    except Exception:
        first_exit = first.kill()
        raise

    second = start_process(entrypoint, project, home, recovery_server["base_url"], case_dir / "second-transcript.jsonl")
    try:
        listed = second.request("session/list", {})
        resumed = second.request("session/resume", {"sessionId": session_id, "cwd": str(project), "mcpServers": []})
        resumed_prompt = prompt(second, session_id)
        second_closed = second.close_session(session_id)
        second_exit = second.close()
    except Exception:
        second_exit = second.kill()
        raise

    paths = session_paths(home)
    events, invalid = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    listed_ids = [item.get("sessionId") for item in listed.get("result", {}).get("sessions", [])]
    prompt_response = responses.get(prompt_id, {})
    checks = {
        "initialize_ok": response_ok(initialize),
        "session_new_ok": response_ok(created),
        "provider_request_observed_before_cancel": request_seen,
        "cancel_request_sent": cancel_sent,
        "prompt_cancelled": prompt_response.get("result", {}).get("stopReason") == "cancelled",
        "first_close_ok": response_ok(first_closed),
        "first_process_exited": first_exit["returncode"] == 0,
        "session_list_contains_id": session_id in listed_ids,
        "session_resume_ok": response_ok(resumed),
        "post_cancel_prompt_completed": resumed_prompt.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "second_close_ok": response_ok(second_closed),
        "second_process_exited": second_exit["returncode"] == 0,
        "one_persisted_session_log": len(paths) == 1,
        "session_log_decodes": not invalid,
        "session_log_has_events": len(events) > 0,
    }
    return {
        "scenario": "cancel_resume",
        "repeat": repeat,
        "session_id": session_id,
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "session_paths": [str(path) for path in paths],
            "event_count": len(events),
            "event_types": sorted({str(event.get("type")) for event in events}),
            "invalid_session_lines": invalid,
            "provider": {"timeout_endpoint": timeout_server["base_url"], "recovery_endpoint": recovery_server["base_url"], "transport": "loopback-only"},
        },
    }


def run_process_kill_resume(entrypoint: Path, case_dir: Path, repeat: int, interrupted_server: dict[str, Any], recovery_server: dict[str, Any]) -> dict[str, Any]:
    project = case_dir / "project"
    shutil.copytree(FIXTURE / "code-project", project)
    home = case_dir / "dsh-home"
    first = start_process(entrypoint, project, home, interrupted_server["base_url"], case_dir / "first-transcript.jsonl")
    session_id = ""
    try:
        session_id, initialize, created = initialize_and_new(first, project)
        prompt(first, session_id, request_id=3)
        request_seen = wait_for_request(interrupted_server["request_path"])
        killed = first.kill()
    except Exception:
        first.kill()
        raise

    second = start_process(entrypoint, project, home, recovery_server["base_url"], case_dir / "second-transcript.jsonl")
    try:
        listed = second.request("session/list", {})
        resumed = second.request("session/resume", {"sessionId": session_id, "cwd": str(project), "mcpServers": []})
        resumed_prompt = prompt(second, session_id)
        second_closed = second.close_session(session_id)
        second_exit = second.close()
    except Exception:
        second_exit = second.kill()
        raise

    paths = session_paths(home)
    events, invalid = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    listed_ids = [item.get("sessionId") for item in listed.get("result", {}).get("sessions", [])]
    checks = {
        "initialize_ok": response_ok(initialize),
        "session_new_ok": response_ok(created),
        "provider_request_observed_before_kill": request_seen,
        "first_process_was_killed": killed["returncode"] == -signal.SIGKILL,
        "session_list_contains_id": session_id in listed_ids,
        "session_resume_ok": response_ok(resumed),
        "post_kill_prompt_completed": resumed_prompt.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "second_close_ok": response_ok(second_closed),
        "second_process_exited": second_exit["returncode"] == 0,
        "one_persisted_session_log": len(paths) == 1,
        "session_log_decodes": not invalid,
        "session_log_has_events": len(events) > 0,
    }
    return {
        "scenario": "process_kill_resume",
        "repeat": repeat,
        "session_id": session_id,
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "observed": {
            "session_paths": [str(path) for path in paths],
            "event_count": len(events),
            "event_types": sorted({str(event.get("type")) for event in events}),
            "invalid_session_lines": invalid,
            "provider": {"interrupted_endpoint": interrupted_server["base_url"], "recovery_endpoint": recovery_server["base_url"], "transport": "loopback-only"},
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    candidate_repo = args.candidate_repo.resolve()
    candidate_entry = (args.candidate_entry or candidate_repo / manifest["runtime"]["entrypoint"]).resolve()
    from evaluation.runner.run_deepseek_challenger import candidate_preflight
    preflight = candidate_preflight(candidate_repo, candidate_entry, manifest)
    output_dir = args.output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "candidate-manifest.json", manifest)
    write_json(output_dir / "preflight.json", preflight)
    if preflight["status"] != "pass":
        summary = {"schema": SCHEMA, "status": "blocked", "classification": "acceptance/evaluation", "candidate": manifest, "preflight": preflight, "candidate_c4_status": "unknown"}
        write_json(output_dir / "summary.json", summary)
        return summary

    from evaluation.runner.run_baseline import start_fake_provider, stop_fake_provider

    cases: list[dict[str, Any]] = []
    for repeat in range(1, args.repeats + 1):
        with tempfile.TemporaryDirectory(prefix=f"zwb-w8-deepseek-c4-{repeat:02d}-") as temp:
            root = Path(temp)
            (root / "plain-server").mkdir()
            (root / "cancel-server").mkdir()
            (root / "kill-server").mkdir()
            plain, plain_error = start_fake_provider(root / "plain-server", "fake-a", "plain", port=0)
            cancel_server, cancel_error = start_fake_provider(root / "cancel-server", "fake-a", "plain", port=0, fault="timeout_once")
            kill_server, kill_error = start_fake_provider(root / "kill-server", "fake-a", "plain", port=0, fault="timeout_once")
            if plain_error or cancel_error or kill_error:
                raise RuntimeError(f"fake Provider startup failed: plain={plain_error}, cancel={cancel_error}, kill={kill_error}")
            try:
                case_specs = [
                    ("clean_resume", lambda case: run_clean_resume(candidate_entry, case, repeat, plain)),
                    ("cancel_resume", lambda case: run_cancel_resume(candidate_entry, case, repeat, cancel_server, plain)),
                    ("process_kill_resume", lambda case: run_process_kill_resume(candidate_entry, case, repeat, kill_server, plain)),
                ]
                for scenario, execute_case in case_specs:
                    case_dir = output_dir / scenario / f"repeat-{repeat:02d}"
                    case_dir.mkdir(parents=True, exist_ok=True)
                    started = datetime.now(timezone.utc)
                    try:
                        result = execute_case(case_dir)
                    except Exception as error:
                        result = {"scenario": scenario, "repeat": repeat, "status": "unknown", "error": repr(error)}
                    result["started_at"] = started.isoformat()
                    result["finished_at"] = datetime.now(timezone.utc).isoformat()
                    write_json(case_dir / "result.json", result)
                    cases.append(result)
            finally:
                stop_fake_provider(kill_server)
                stop_fake_provider(cancel_server)
                stop_fake_provider(plain)
                for server, name in ((plain, "plain"), (cancel_server, "cancel"), (kill_server, "kill")):
                    if server:
                        for source, target in ((server["request_path"], f"{name}-provider-requests.jsonl"), (server["output_path"], f"{name}-provider.log")):
                            if source.exists():
                                shutil.copyfile(source, output_dir / target)

    scenario_summaries: dict[str, Any] = {}
    for scenario in {item["scenario"] for item in cases}:
        rows = [item for item in cases if item["scenario"] == scenario]
        scenario_summaries[scenario] = {
            "status": "pass" if len(rows) == args.repeats and all(row["status"] == "pass" for row in rows) else "fail",
            "repeat_count": len(rows),
            "passed_count": sum(row["status"] == "pass" for row in rows),
            "checks": {key: all(row.get("checks", {}).get(key, False) for row in rows) for key in sorted({key for row in rows for key in row.get("checks", {})})},
        }
    lifecycle_pass = all(value["status"] == "pass" for value in scenario_summaries.values())
    summary = {
        "schema": SCHEMA,
        "status": "pass" if lifecycle_pass else "fail",
        "classification": "acceptance/evaluation",
        "candidate": manifest,
        "preflight": preflight,
        "scenarios": scenario_summaries,
        "candidate_c4_status": "partial: ACP lifecycle pass; full W6 C4 remains unknown",
        "threshold_interpretation": {
            "w6_c4_required_injection_points": ["before_tool", "after_tool_before_commit", "committed_before_next_step", "provider_timeout", "tool_timeout", "process_interrupted"],
            "candidate_verified": ["session/new", "session/list", "session/resume", "session/cancel", "persistent_session_log", "cross_process_resume"],
            "not_verified": ["candidate-owned effect ledger", "tool/provider injection matrix", "idempotent external side-effect retry", "transcript replay"],
            "unknown_rule": "ACP lifecycle evidence does not upgrade the candidate to full C4 pass; missing effect/replay semantics remain unknown.",
        },
        "checks": {
            "preflight_passed": preflight["status"] == "pass",
            "all_acp_scenarios_passed": lifecycle_pass,
            "no_real_credentials": True,
            "no_external_network": True,
            "no_production_data": True,
            "no_external_side_effects": True,
        },
        "cases": cases,
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--candidate-entry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    summary = run(args)
    print(json.dumps({"status": summary["status"], "output": str(args.output.resolve()), "candidate_c4_status": summary.get("candidate_c4_status")}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
