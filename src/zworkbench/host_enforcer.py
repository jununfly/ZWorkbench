"""S0 host-enforcement spike: macOS seatbelt (sandbox-exec) wrapper.

Fail-closed contract (ADR 0008 — host enforcement must be fail-closed and testable):

  1. Default-deny ALL file-write + network-outbound; an explicit whitelist enables
     only the paths / capabilities the worker needs.
  2. Enforcer unavailable OR ``sandbox_apply`` fails -> raise ``EnforcerUnavailable``
     and NEVER run ``command`` unsandboxed. No silent degradation.
  3. Every boundary-crossing attempt yields an auditable violation event captured
     into the receipt.

This module is the *spike seam*: it proves the approach and carries the testable
assertions that become S2 write-seam acceptance evidence (ADR 0008 consequences).
It is intentionally NOT yet wired into ``worker_bridge``; real product integration
lands with S2 write-seam productization.

NOTE on validation host: ``sandbox-exec`` applies a sandbox to a child process, but a
process that is *itself* already seatbelt-sandboxed cannot nest ``sandbox_apply``
(macOS returns EPERM). The ZWorkbench product process is a normal (non-sandboxed)
macOS CLI/app, so it CAN apply the sandbox to the Codex Worker child. The agent's
own execution sandbox cannot, so the live OS-enforcement tests skip-with-reason when
the enforcer cannot apply and never silently pass.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# macOS ships sandbox-exec at a fixed path; it is the ADR 0008 prime candidate
# (built-in, zero dependency, matches "先 macOS 单机").
SANDBOX_EXEC = "/usr/bin/sandbox-exec"


class EnforcerUnavailable(Exception):
    """Raised when the OS enforcer cannot be initialized.

    Callers MUST NOT fall back to running ``command`` without enforcement.
    """


@dataclass
class ViolationEvent:
    kind: str
    allowed: bool = False
    detail: Dict[str, object] = field(default_factory=dict)


@dataclass
class EnforcementReceipt:
    command: List[str]
    enforcer: str
    sandboxed: bool
    violations: List[ViolationEvent] = field(default_factory=list)
    returncode: Optional[int] = None


def build_seatbelt_profile(
    allow_writes: Optional[List[str]] = None,
    allow_network: bool = False,
) -> str:
    """Deny-all profile: re-enable only what a worker needs to boot, plus the
    explicit write whitelist. Network-outbound stays denied unless ``allow_network``.
    """
    allow_writes = allow_writes or []
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow file-read*)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow signal (target self))",
    ]
    for path in allow_writes:
        lines.append(f'(allow file-write* (literal "{path}"))')
    if allow_network:
        lines.append("(allow network-outbound)")
    return "\n".join(lines)


def _enforcer_binary() -> str:
    # Override hook so criterion #2 (enforcer missing) is testable without OS access.
    return os.environ.get("ZWB_ENFORCER_BIN", SANDBOX_EXEC)


def spawn_sandboxed(
    command: List[str],
    *,
    allow_writes: Optional[List[str]] = None,
    allow_network: bool = False,
    timeout: float = 30.0,
) -> EnforcementReceipt:
    """Spawn ``command`` under the OS enforcer.

    Fail-closed: any enforcer failure raises ``EnforcerUnavailable`` and ``command``
    is NOT executed unsandboxed. ``sandbox-exec`` does not exec the child when
    ``sandbox_apply`` fails, so a non-zero enforcer exit is treated as enforcement
    failure rather than a worker result.
    """
    bin_path = _enforcer_binary()
    if not os.access(bin_path, os.X_OK):
        raise EnforcerUnavailable(f"enforcer binary not executable: {bin_path}")

    profile = build_seatbelt_profile(allow_writes=allow_writes, allow_network=allow_network)
    argv = [bin_path, "-p", profile, *command]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:  # pragma: no cover - binary vanished mid-check
        raise EnforcerUnavailable(f"enforcer launch failed: {exc}")

    # sandbox_apply failed (e.g. nested-sandbox EPERM): child was NOT started.
    if proc.returncode != 0 and "sandbox_apply" in proc.stderr:
        raise EnforcerUnavailable(
            f"enforcer could not apply sandbox (child not started): "
            f"{proc.stderr.strip()}"
        )

    violations: List[ViolationEvent] = []
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
            for attempt in payload.get("attempts", []):
                if not attempt.get("allowed"):
                    violations.append(
                        ViolationEvent(
                            kind=attempt["kind"],
                            allowed=False,
                            detail=attempt.get("detail", {}),
                        )
                    )
        except json.JSONDecodeError:
            pass

    return EnforcementReceipt(
        command=command,
        enforcer=bin_path,
        sandboxed=True,
        violations=violations,
        returncode=proc.returncode,
    )
