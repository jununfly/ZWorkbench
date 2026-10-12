#!/usr/bin/env python3
"""End-to-end first-run regression for ZWorkbench (roadmap node 1-9-5).

This is the replayable "端到端首跑回归脚本" described by R4
(``docs/prds/r4-onboarding-first-run.md`` and
``docs/designs/ep-first-run-journey.md``). It exercises the default first-run
path with **zero credentials** and a **fake-loopback** provider:

    干净环境 -> zworkbench run --prompt ... -> recorded_view_present == true

The script writes a self-contained fake ``codex`` binary (a stdio JSON-RPC
harness that speaks the subset the executor needs) into a temporary directory
on ``PATH``, runs ``zworkbench run`` against a fresh empty ``case_root``, then
asserts the run completed and that the owner DB carries a ``recorded_view``
replay for the run id (proving the journey reached the "see your own run in the
read-only UI" state without any real Provider or credential).

Replayability: every run uses brand-new temporary directories, so the script
can be re-run any number of times and always starts from a clean slate.

Exit code: ``0`` on PASS, ``1`` on FAIL.

--------------------------------------------------------------------------------
Gate (do NOT silently skip): #40 已于 2026-10-13 关闭，本脚本的机械判据（干净 venv
``pip install .`` + fake-loopback 零凭证 + ``recorded_view_present == true``）
已在干净 venv 中复核通过，证据见
``docs/prds/r4-onboarding-first-run.md`` 的「验收进度」分栏。

R4 is now ``implemented`` (2026-10-13): the mechanical criteria are owner-backed,
and the "two human 走查记录" criterion was explicitly **waived** by the owner —
see the 「豁免留痕」 section of ``docs/prds/r4-onboarding-first-run.md``. A waiver
is not evidence: the first-run journey still has zero observation from a
non-author perspective, and the "卡点数 <= 2" target remains unmeasured.

This script stays unwired from any hard CI gate by deliberate product choice
(see roadmap 1-9-5 decision log), not because it is unreliable.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_PROMPT = "summarize the fixture and return the marker token"
DEFAULT_RUN_ID = "e2e-first-run"


_FAKE_CODEX_TEMPLATE = '''
import json
import sys

THREAD_ID = "e2e-thread"
TURN_ID = "e2e-turn"
MARKER = "__ZW_MARKER__"


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    request_id = message["id"]
    method = message.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "thread/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    elif method == "turn/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        send({"jsonrpc": "2.0", "method": "item/agentMessage/delta",
              "params": {"turnId": TURN_ID, "delta": MARKER}})
        send({"jsonrpc": "2.0", "method": "turn/completed",
              "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
    elif method == "thread/read":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
    else:
        send({"jsonrpc": "2.0", "id": request_id,
              "error": {"code": -32601, "message": "unknown method"}})
'''


def _fake_codex_source(marker: str) -> str:
    """A minimal Codex CLI harness: stdio JSON-RPC, no network, no credentials.

    It implements exactly the method subset ``CodexAppServerAdapter`` drives
    (initialize / thread.start / turn.start + agentMessage delta + turn.completed
    / thread.read) and echoes ``marker`` as the agent text so the run has a
    verifiable result. The marker is injected via a sentinel replace so the
    literal JSON braces in the harness are never treated as ``str.format`` fields.
    """
    return _FAKE_CODEX_TEMPLATE.replace("__ZW_MARKER__", marker)


def _write_fake_codex(bin_dir: Path, marker: str) -> Path:
    """Write an executable fake ``codex`` into ``bin_dir`` and return its path."""
    executable = bin_dir / "codex"
    executable.write_text(
        "#!{0}\n{1}".format(sys.executable, textwrap.dedent(_fake_codex_source(marker))),
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _invoke_zworkbench(zw_cmd: List[str], run_args: List[str], *,
                       cwd: Path, env: Dict[str, str]) -> Tuple[int, Optional[dict], str]:
    """Run ``zworkbench run`` and return (exit_code, parsed_stdout_json, stderr)."""
    full = zw_cmd + ["run"] + run_args
    proc = subprocess.run(
        full,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    payload: Optional[dict] = None
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = None
    return proc.returncode, payload, proc.stderr


def run_once(*, prompt: str, run_id: str, zw_module: str,
             case_root: Optional[Path], marker: str) -> Tuple[bool, List[str]]:
    """Execute one first-run journey and return (passed, failure_messages)."""
    failures: List[str] = []
    own_temp = case_root is None
    root = case_root if case_root is not None else Path(tempfile.mkdtemp(prefix="zw-e2e-"))
    bin_dir = root / "fake-codex-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = _write_fake_codex(bin_dir, marker)

    # Zero-credential loopback: default endpoint is loopback (matches 1-9-1),
    # no --provider-config, no real Provider. fake codex is the only thing on PATH.
    env = dict(os.environ)
    env["PATH"] = "{0}{1}{2}".format(str(bin_dir), os.pathsep, env.get("PATH", ""))
    # The subprocess runs in a fresh temp cwd, so any relative PYTHONPATH entry
    # must be resolved against this script's launch directory (the repo root),
    # otherwise ``python -m zworkbench.cli`` cannot locate the package.
    existing_pp = env.get("PYTHONPATH")
    if existing_pp:
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(p).resolve()) if not Path(p).is_absolute() else p
            for p in existing_pp.split(os.pathsep)
            if p
        )
    # Never reach a real Provider profile; keep the loopback baseline explicit.
    env.pop("ARK_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)

    zw_cmd = [sys.executable, "-m", zw_module]
    run_args = [
        "--prompt", prompt,
        "--codex", str(fake),
        "--run-id", run_id,
    ]

    exit_code, payload, stderr_text = _invoke_zworkbench(zw_cmd, run_args, cwd=root, env=env)

    if payload is None:
        failures.append("stdout was not valid JSON (exit={0})".format(exit_code))
        if stderr_text.strip():
            failures.append("stderr: " + stderr_text.strip().splitlines()[-1][:300])
        return False, failures

    status = payload.get("status")
    if status != "completed":
        failures.append("run status was {0!r}, expected 'completed'".format(status))

    owner = payload.get("owner", {})
    if not owner.get("database_present"):
        failures.append("owner DB not created under case_root")
    if not owner.get("recorded_view_present"):
        failures.append("recorded_view_present was False (journey did not reach recorded view)")

    next_steps = payload.get("next_steps") or []
    if not next_steps:
        failures.append("next_steps array missing/empty (value loop not stitched)")
    else:
        joined = " ".join(step.get("command", "") for step in next_steps)
        if "ui-host" not in joined:
            failures.append("next_steps does not include a ui-host command")

    if own_temp:
        shutil.rmtree(root, ignore_errors=True)
    return (len(failures) == 0), failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end first-run regression for ZWorkbench (1-9-5).",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt for the first run")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="run id for the first run")
    parser.add_argument(
        "--zw-module", default="zworkbench.cli",
        help="importable CLI module invoked as `<python> -m <module>` (default: zworkbench.cli)",
    )
    parser.add_argument(
        "--case-root", default=None,
        help="reuse this case_root instead of a fresh temp dir (debugging only)",
    )
    parser.add_argument(
        "--marker", default="e2e-ok",
        help="marker token the fake codex echoes back as the agent result",
    )
    args = parser.parse_args(argv)

    case_root = Path(args.case_root).resolve() if args.case_root else None
    passed, failures = run_once(
        prompt=args.prompt,
        run_id=args.run_id,
        zw_module=args.zw_module,
        case_root=case_root,
        marker=args.marker,
    )

    print("=" * 64)
    print("ZWorkbench first-run E2E regression")
    print("  fake-loopback | zero credentials | recorded_view_present check")
    print("=" * 64)
    if passed:
        print("PASS: first run completed and recorded_view_present == true")
        print("      next_steps value loop stitched (ui-host present)")
        return 0
    print("FAIL:")
    for message in failures:
        print("  - " + message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
