"""Host sandbox boundary attestation for the coding Worker path (node 1-8-1).

The roadmap node 1-8-1 asks for a host sandbox as a real pre-condition for
Workspace writes performed by the coding Worker.  ADR 0008 (#2) requires that a
missing enforcer refuse to start rather than degrade to a bare run.  ADR 0010
established that OS-level wrapping (seatbelt / unshare) is not viable on the
dominant host (macOS 26 forbids ``sandbox-exec`` for ordinary processes and the
S0 enforcer was removed); a Worker subprocess inherits that same limitation.

The honest control is therefore an OPERATOR-ATTESTED host-require contract:

* ``require_host_sandbox`` is the operator's intent (off by default; production
  deployments turn it on).
* When required, a non-empty ``attestation`` MUST be supplied -- either via the
  ``WorkerBridge`` constructor (``host_sandbox_attestation``) or the environment
  variable ``ZW_HOST_SANDBOX_ATTESTED``.  Missing attestation refuses to start
  (fail-closed).
* A best-effort runtime detection (``detect_os_sandbox``) is auxiliary only.
  When the operator attests but the host is provably *without* a detectable
  boundary, we also refuse (conflict = fail-closed).  When detection cannot
  tell, we accept (warn-only) so a host we cannot introspect is not wrongly
  blocked.

The gate runs BEFORE the coding Worker is spawned; a missing/conflicting
boundary is a precondition failure, not a Worker violation, so it is raised as
a fail-stop error and never reaches the safe-stop accounting path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

HOST_SANDBOX_ATTESTED_ENV = "ZW_HOST_SANDBOX_ATTESTED"


def detect_os_sandbox(environ: Mapping[str, str] = os.environ) -> Optional[bool]:
    """Best-effort: is this process inside an OS-enforced sandbox?

    Returns ``True`` when a boundary is clearly present, ``False`` when it is
    clearly absent, and ``None`` when it cannot be determined.  This is an
    auxiliary signal only -- it is never used alone to gate the Worker.
    """

    # macOS App Sandbox advertises a container id in the environment.
    if environ.get("APP_SANDBOX_CONTAINER_ID"):
        return True
    # Linux: a seccomp filter (mode 2) is a strong positive signal of a real
    # kernel-enforced boundary.
    status = Path("/proc/self/status")
    if status.is_file():
        try:
            text = status.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        for line in text.splitlines():
            if line.startswith("Seccomp:"):
                try:
                    mode = int(line.split(":", 1)[1].strip())
                except ValueError:
                    return None
                # mode 2 == SECCOMP_MODE_FILTER: a real sandbox policy is in
                # effect.  mode 0 (disabled) does not prove the absence of some
                # other boundary, so we return None rather than False there.
                return True if mode == 2 else None
        return None
    return None


def verify_host_sandbox_boundary(
    *,
    require: bool,
    attestation: Optional[str],
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Fail-closed gate run BEFORE the coding Worker is spawned.

    ``require`` mirrors ``WorkerBridge.require_host_sandbox``.  When ``require``
    is ``False`` the gate is inert.  When ``True``, an ``attestation`` string is
    mandatory; a detectable contradiction between the attestation and the host
    also refuses to start.
    """

    if not require:
        return
    # Lazy import (function scope) avoids a circular dependency at module load
    # time: worker_bridge imports this module, so importing WorkerBridgeError at
    # module top would deadlock.  By the time this function runs, worker_bridge
    # is fully loaded.
    from .worker_bridge import WorkerBridgeError

    if not attestation:
        raise WorkerBridgeError(
            "host sandbox boundary is required (require_host_sandbox=True) but no "
            "operator attestation was supplied; refusing to start the Worker",
            code="host_sandbox_absent",
            safe_stop=False,
        )
    signal = detect_os_sandbox(environ)
    if signal is False:
        raise WorkerBridgeError(
            "operator attested a host sandbox boundary but the OS boundary is "
            "detectable and absent; refusing to start the Worker",
            code="host_sandbox_absent",
            safe_stop=False,
        )
