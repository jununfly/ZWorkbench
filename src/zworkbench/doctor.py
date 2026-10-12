"""Read-only self-check doctor for first-run readiness (roadmap 1-9-2).

The doctor answers one question — *can a zero-config ``zworkbench run``
start on this machine right now?* — by probing three things and never
writing anything:

  1. ``codex_executable`` — locate the Codex executable (explicit ``--codex``
     or ``shutil.which``) and run ``codex --version`` under a timeout;
  2. ``case_layout`` — stat the case root and workspace, and report the
     derived case-local paths (owner DB, CODEX_HOME, event log);
  3. ``loopback_provider`` — HTTP-probe the Provider endpoint, but ONLY when
     it is a loopback address.  A non-loopback endpoint is reported
     ``unknown`` and never contacted: doctor does not hold credentials and,
     per the 1-9 decision, must not claim a real Provider is configured.

Read-only is a hard constraint: no directory is created, no owner database
is opened, no run is started.  The result is one JSON-safe
:class:`DoctorReport` whose checks each carry an actionable ``fix_hint``.
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import urlsplit
from urllib.request import urlopen

DOCTOR_SCHEMA = "zworkbench-doctor/v1"

#: How long ``codex --version`` may take before the probe gives up.
CODEX_VERSION_TIMEOUT_SECONDS = 10.0

#: How long the loopback HTTP probe may take before it reports unreachable.
LOOPBACK_PROBE_TIMEOUT_SECONDS = 2.0

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

CodexProbe = Callable[[Path], Tuple[bool, str]]
HttpProbe = Callable[[str], Tuple[Optional[bool], str]]


@dataclass(frozen=True)
class DoctorCheck:
    """One probe outcome with an actionable fix hint when it did not pass."""

    name: str
    status: str  # "pass" | "fail" | "unknown"
    detail: str
    fix_hint: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "fix_hint": self.fix_hint,
        }


@dataclass(frozen=True)
class DoctorReport:
    """The aggregated readiness verdict across all doctor probes."""

    checks: Tuple[DoctorCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.status == "pass" for check in self.checks)

    @property
    def status(self) -> str:
        return "ready" if self.ready else "not_ready"

    def check(self, name: str) -> DoctorCheck:
        for item in self.checks:
            if item.name == name:
                return item
        raise KeyError(name)

    def to_dict(self) -> dict:
        return {
            "schema": DOCTOR_SCHEMA,
            "status": self.status,
            "ready": self.ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def _is_loopback_endpoint(endpoint: str) -> bool:
    try:
        host = urlsplit(endpoint).hostname or ""
    except ValueError:
        return False
    return host.lower() in LOOPBACK_HOSTS


def _probe_codex_version(path: Path) -> Tuple[bool, str]:
    """Locate-and-execute probe: run ``codex --version`` under a timeout."""

    if not path.exists():
        located = shutil.which(str(path)) or (shutil.which("codex") if path.name == "codex" else None)
        if located is None:
            return False, "codex executable not found"
        path = Path(located)
    if not path.exists():
        return False, "codex executable not found"
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=CODEX_VERSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, "codex --version timed out after {0}s".format(CODEX_VERSION_TIMEOUT_SECONDS)
    except OSError as exc:
        return False, "codex could not be executed: {0}".format(type(exc).__name__)
    if completed.returncode != 0:
        return False, "codex --version exited with code {0}".format(completed.returncode)
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    detail = output[0].strip() if output else "codex --version produced no output"
    return True, detail


def _probe_loopback_http(endpoint: str, timeout: float) -> Tuple[Optional[bool], str]:
    """HTTP-GET the endpoint; loopback only, short timeout, no retries."""

    try:
        with urlopen(endpoint, timeout=timeout) as response:
            return True, "endpoint responded with HTTP {0}".format(getattr(response, "status", "?"))
    except Exception as exc:  # noqa: BLE001 - any failure means "unreachable"
        return False, "endpoint unreachable: {0}".format(type(exc).__name__)


def run_doctor(
    *,
    case_root: Path,
    workspace: Optional[Path] = None,
    codex: Optional[Path] = None,
    endpoint: str = "http://127.0.0.1:11434",
    codex_probe: Optional[CodexProbe] = None,
    http_probe: Optional[HttpProbe] = None,
    loopback_timeout: float = LOOPBACK_PROBE_TIMEOUT_SECONDS,
) -> DoctorReport:
    """Probe first-run readiness without writing anything.

    ``codex_probe`` / ``http_probe`` are injectable so tests can exercise
    failure paths without real processes or sockets.
    """

    case_root = Path(case_root).expanduser().resolve(strict=False)
    workspace = (
        case_root
        if workspace is None
        else Path(workspace).expanduser().resolve(strict=False)
    )
    database = case_root / "state" / "composition.sqlite3"
    code_home = case_root / "codex-home"
    event_log = case_root / "events" / "codex.jsonl"

    # -- codex_executable ------------------------------------------------
    probe = codex_probe or _probe_codex_version
    target = Path(codex).expanduser().resolve(strict=False) if codex is not None else Path("codex")
    codex_ok, codex_detail = probe(target)
    codex_check = DoctorCheck(
        name="codex_executable",
        status="pass" if codex_ok else "fail",
        detail=codex_detail,
        fix_hint=None
        if codex_ok
        else "install the Codex CLI or pass --codex /path/to/codex "
        "(doctor probes `which codex`, then runs `codex --version`)",
    )

    # -- case_layout (pure stat; never creates anything) -----------------
    problems = []
    if not case_root.is_dir():
        problems.append("case_root {0} does not exist".format(case_root))
    if not workspace.is_dir():
        problems.append("workspace {0} does not exist".format(workspace))
    layout_detail = "; ".join(problems) if problems else (
        "case_root and workspace present; derived paths: "
        "database={0} code_home={1} event_log={2}".format(database, code_home, event_log)
    )
    layout_check = DoctorCheck(
        name="case_layout",
        status="fail" if problems else "pass",
        detail=layout_detail,
        fix_hint=None
        if not problems
        else "create the missing directory, or pass --case-root (and "
        "--workspace) pointing at existing directories",
    )

    # -- loopback_provider (loopback only; never contact remote) ---------
    if not _is_loopback_endpoint(endpoint):
        provider_check = DoctorCheck(
            name="loopback_provider",
            status="unknown",
            detail="non-loopback endpoint {0} was not contacted by doctor".format(endpoint),
            fix_hint="real Provider endpoints are not probed by doctor; "
            "configure --provider-profile and run with --real-provider-gate "
            "per docs/references/optional-real-provider-staging.md",
        )
    else:
        net_probe = http_probe or (lambda ep: _probe_loopback_http(ep, loopback_timeout))
        reachable, reach_detail = net_probe(endpoint)
        provider_check = DoctorCheck(
            name="loopback_provider",
            status="pass" if reachable else "fail",
            detail=reach_detail,
            fix_hint=None
            if reachable
            else "start the loopback Provider or pass --endpoint "
            "http://127.0.0.1:<port> (default expects an ollama-compatible "
            "endpoint on 127.0.0.1:11434)",
        )

    return DoctorReport(checks=(codex_check, layout_check, provider_check))
