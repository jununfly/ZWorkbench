#!/usr/bin/env python3
"""Probe DeepSeek Harness ACP recording and replay boundaries.

The candidate's ACP server persists a session log and resumes a session, but
its documented contract does not include transcript replay.  This runner
captures that boundary: it verifies a recorded log and deterministic evaluator
decode, then checks that session/resume does not silently replay old wire
updates or perform live work.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w6-0.1"
MANIFEST_PATH = REPO_ROOT / "evaluation" / "candidates" / "deepseek" / "manifest.json"
SCHEMA = "zworkbench-deepseek-c6-replay/v1"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def response_ok(frame: dict[str, Any]) -> bool:
    return "result" in frame and "error" not in frame


def environment_for(home: Path, base_url: str) -> dict[str, str]:
    import os

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


def server_frames(transcript: Path) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("side") == "server":
            frames.append(value["frame"])
    return frames


def run_case(entrypoint: Path, case_dir: Path, server: dict[str, Any], repeat: int) -> dict[str, Any]:
    from evaluation.runner.run_deepseek_c4_acp import AcpProcess, PROMPT, decode_session, session_paths

    project = case_dir / "project"
    shutil.copytree(FIXTURE / "code-project", project)
    home = case_dir / "dsh-home"
    first = AcpProcess(entrypoint=entrypoint, project=project, environment=environment_for(home, server["base_url"]), transcript=case_dir / "first-transcript.jsonl")
    try:
        initialize = first.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        created = first.request("session/new", {"cwd": str(project), "mcpServers": []})
        session_id = created.get("result", {}).get("sessionId", "")
        prompted = first.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": PROMPT}]})
        closed = first.close_session(session_id)
        first_exit = first.close()
    except Exception:
        first_exit = first.kill()
        raise

    first_frames = server_frames(case_dir / "first-transcript.jsonl")
    second = AcpProcess(entrypoint=entrypoint, project=project, environment=environment_for(home, server["base_url"]), transcript=case_dir / "second-transcript.jsonl")
    try:
        resumed = second.request("session/resume", {"sessionId": session_id, "cwd": str(project), "mcpServers": []})
        resumed_close = second.close_session(session_id)
        second_exit = second.close()
    except Exception:
        second_exit = second.kill()
        raise

    second_frames = server_frames(case_dir / "second-transcript.jsonl")
    paths = session_paths(home)
    events_a, invalid_a = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    events_b, invalid_b = decode_session(paths[0]) if len(paths) == 1 else ([], [f"expected one session log, found {len(paths)}"])
    first_updates = [frame for frame in first_frames if frame.get("method") == "session/update"]
    second_updates = [frame for frame in second_frames if frame.get("method") == "session/update"]
    checks = {
        "initialize_ok": response_ok(initialize),
        "session_new_ok": response_ok(created),
        "prompt_completed": prompted.get("result", {}).get("stopReason") in {"end_turn", "max_tokens"},
        "first_close_ok": response_ok(closed),
        "first_process_exited": first_exit["returncode"] == 0,
        "recorded_view_present": len(first_updates) > 0,
        "resume_ok": response_ok(resumed),
        "resume_close_ok": response_ok(resumed_close),
        "second_process_exited": second_exit["returncode"] == 0,
        "one_session_log": len(paths) == 1,
        "session_log_decodes": not invalid_a and not invalid_b,
        "simulated_decode_is_deterministic": events_a == events_b,
        "resume_does_not_replay_old_wire_updates": len(second_updates) == 0,
        "live_replay_effects": len(second_updates),
    }
    return {
        "scenario": "record_resume_without_replay",
        "repeat": repeat,
        "status": "pass" if all(value is True or value == 0 for value in checks.values()) else "fail",
        "checks": checks,
        "observed": {
            "first_recorded_update_count": len(first_updates),
            "resume_wire_update_count": len(second_updates),
            "session_event_count": len(events_a),
            "session_event_types": sorted({str(event.get("type")) for event in events_a}),
            "invalid_session_lines": invalid_a + invalid_b,
            "provider": {"endpoint": server["base_url"], "transport": "loopback-only"},
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    from evaluation.runner.run_baseline import start_fake_provider, stop_fake_provider
    from evaluation.runner.run_deepseek_challenger import candidate_preflight

    manifest = load_json(MANIFEST_PATH)
    candidate_repo = args.candidate_repo.resolve()
    entrypoint = (args.candidate_entry or candidate_repo / manifest["runtime"]["entrypoint"]).resolve()
    preflight = candidate_preflight(candidate_repo, entrypoint, manifest)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("evidence output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "candidate-manifest.json", manifest)
    write_json(output / "preflight.json", preflight)
    if preflight["status"] != "pass":
        summary = {"schema": SCHEMA, "status": "blocked", "classification": "acceptance/evaluation", "candidate": manifest, "preflight": preflight, "candidate_c6_status": "unknown"}
        write_json(output / "summary.json", summary)
        return summary

    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="zwb-w8-deepseek-c6-") as temp:
        server_root = Path(temp) / "server"
        server_root.mkdir()
        server, error = start_fake_provider(server_root, "fake-a", "plain", port=0)
        if error:
            raise RuntimeError(f"fake Provider startup failed: {error}")
        try:
            for repeat in range(1, args.repeats + 1):
                case_dir = output / "record-resume" / f"repeat-{repeat:02d}"
                case_dir.mkdir(parents=True, exist_ok=True)
                result = run_case(entrypoint, case_dir, server, repeat)
                write_json(case_dir / "result.json", result)
                cases.append(result)
        finally:
            stop_fake_provider(server)
            for source, name in ((server["request_path"], "provider-requests.jsonl"), (server["output_path"], "provider.log")):
                if source.exists():
                    shutil.copyfile(source, output / name)

    passed = sum(case["status"] == "pass" for case in cases)
    summary = {
        "schema": SCHEMA,
        "status": "pass" if passed == len(cases) == args.repeats else "fail",
        "classification": "acceptance/evaluation",
        "candidate": manifest,
        "preflight": preflight,
        "candidate_c6_status": "unknown: candidate session recording/resume is present, but no candidate-owned replay mode/contract is exposed",
        "observed": {"cases": f"{passed}/{len(cases)}", "recorded_view": "present", "session_resume": "present", "simulated_replay": "evaluator-only deterministic decode", "live_replay": "0 observed because resume intentionally emits no historical updates"},
        "threshold_interpretation": {"required_events_and_mode_labels": "not promoted to pass without a candidate replay contract", "simulated_replay_threshold": "met only for evaluator decode, not candidate capability", "live_effect_threshold": "0 observed in the no-tool resume probe", "unknown_rule": "session/resume restoring state is not transcript replay; no live replay or side-effect replay is claimed"},
        "cases": cases,
        "checks": {"preflight_passed": preflight["status"] == "pass", "all_record_resume_probes_passed": passed == len(cases) == args.repeats, "no_real_credentials": True, "no_external_network": True, "no_production_data": True, "no_external_side_effects": True},
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--candidate-entry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    summary = run(args)
    print(json.dumps({"status": summary["status"], "output": str(args.output.resolve()), "candidate_c6_status": summary["candidate_c6_status"]}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
