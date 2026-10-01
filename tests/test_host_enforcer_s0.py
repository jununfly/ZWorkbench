"""S0 host-enforcement spike — fail-closed three-criteria testable assertions (ADR 0008).

These are the spike exit criteria: testable assertions, not a demo. The enforcer is
macOS sandbox-exec (seatbelt). Criterion #2 (enforcer unavailable -> refuse to start,
never degrade to unsandboxed) is fully exercised here. Criteria #1 and #3 require the
OS to actually apply the sandbox; when the host process is itself sandboxed (nested
sandbox_apply is denied by macOS) the live tests SKIP with an explicit reason instead
of silently passing — see host_enforcer.py module docstring.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from zworkbench.host_enforcer import (
    EnforcerUnavailable,
    build_seatbelt_profile,
    spawn_sandboxed,
)

PROBE = Path(__file__).parent / "spike_child_probe.py"


def _run_probe(allow_writes=None, allow_network=False, allowed_arg=None):
    """Spawn the probe child under the enforcer; skip (not fail) if the host cannot
    apply a nested sandbox. Returns the EnforcementReceipt on a real non-sandboxed host."""
    command = [sys.executable, "-B", str(PROBE)]
    if allowed_arg is not None:
        command.append(allowed_arg)
    try:
        return spawn_sandboxed(
            command, allow_writes=allow_writes, allow_network=allow_network
        )
    except EnforcerUnavailable as exc:
        pytest.skip(
            "enforcer could not apply from this (already-sandboxed) process; "
            "validate live OS enforcement on a non-sandboxed host (Terminal / mac CI): "
            f"{exc}"
        )


# --- profile unit (no OS access needed) -------------------------------------


def test_build_seatbelt_profile_denies_by_default_and_whitelists():
    # default profile (no whitelist, no network) must deny writes + network
    default = build_seatbelt_profile(allow_writes=[], allow_network=False)
    assert "(deny default)" in default
    assert "(allow file-write*)" not in default
    assert "(allow network-outbound)" not in default
    # explicit whitelist appears exactly as given
    whitelisted = build_seatbelt_profile(allow_writes=["/tmp/ok"], allow_network=False)
    assert '(allow file-write* (literal "/tmp/ok"))' in whitelisted
    # explicit network enable appears only when requested
    with_net = build_seatbelt_profile(allow_writes=[], allow_network=True)
    assert "(allow network-outbound)" in with_net


# --- criterion #2: enforcer unavailable -> refuse, never unsandboxed ---------


@pytest.mark.exercises_default_product_path
def test_criterion2_missing_enforcer_refuses_start(tmp_path):
    target = tmp_path / "must_not_be_created"
    os.environ["ZWB_ENFORCER_BIN"] = "/nonexistent/sandbox-exec"
    try:
        with pytest.raises(EnforcerUnavailable):
            spawn_sandboxed([str(target)])
        # the hard guarantee: command never ran unsandboxed
        assert not target.exists(), "command executed without an enforcer!"
    finally:
        os.environ.pop("ZWB_ENFORCER_BIN", None)


@pytest.mark.exercises_default_product_path
def test_criterion2_apply_failure_refuses_start(tmp_path):
    fake = tmp_path / "fake_enforcer"
    fake.write_text(
        '#!/bin/sh\n'
        'cat >&2 "sandbox_apply: Operation not permitted"\n'
        "exit 71\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    target = tmp_path / "must_not_be_created"
    os.environ["ZWB_ENFORCER_BIN"] = str(fake)
    try:
        with pytest.raises(EnforcerUnavailable):
            spawn_sandboxed([str(target)])
        assert not target.exists(), "command executed when sandbox_apply failed!"
    finally:
        os.environ.pop("ZWB_ENFORCER_BIN", None)


# --- criterion #1: default-deny all write + network (live, gated) ------------


@pytest.mark.exercises_default_product_path
def test_criterion1_default_deny_write_and_network():
    receipt = _run_probe(allow_writes=[], allow_network=False)
    kinds = {v.kind for v in receipt.violations}
    assert "file-write" in kinds, "default profile must deny writes"
    assert "network-outbound" in kinds, "default profile must deny network"


@pytest.mark.exercises_default_product_path
def test_criterion1_whitelist_enables_explicit_write(tmp_path):
    allowed = tmp_path / "allowed_write"
    receipt = _run_probe(
        allow_writes=[str(allowed)], allow_network=False, allowed_arg=str(allowed)
    )
    allowed_attempts = [a for a in receipt.violations if a.kind == "file-write-allowed"]
    # the whitelisted path must have been allowed (no violation for it)
    assert not allowed_attempts, "whitelisted write was denied"
    # and the non-whitelisted path must still be denied
    assert any(v.kind == "file-write" for v in receipt.violations)


# --- criterion #3: every boundary-cross yields an auditable violation --------


@pytest.mark.exercises_default_product_path
def test_criterion3_violation_events_recorded():
    receipt = _run_probe(allow_writes=[], allow_network=False)
    assert receipt.violations, "every boundary-cross must produce a violation event"
    for violation in receipt.violations:
        assert violation.kind
        assert violation.detail, "violation event must carry auditable detail (path/errno)"
