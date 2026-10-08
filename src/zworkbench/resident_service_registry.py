"""Resident service runtime registry with a hard ≤N capacity.

A "resident service" is a long-lived process launched by an execution-layer
adapter — e.g. the Codex app-server or a DSH bootstrap runtime.  ZWorkbench must
not let an execution session fork an unbounded number of them; this registry is
the single in-process guardrail enforcing the ≤3 cap that the termination &
resource-lifecycle design (sub-07, Backlog #3) names as a known gap ("no
runtime registry, convention only").

The registry is *runtime* state only.  It is owned by the CompositionOwner but
never persisted to SQLite: process / resource state is a host-side runtime fact
and, per the design doc, may only ever be evidence — never durable truth.  A
fresh owner (re)opened in another process gets a fresh, empty registry, which is
exactly the intended per-session capacity boundary.

Fail-closed: when the cap is exceeded, :class:`ResidentServiceCapacityError`
is raised.  Adapters must not swallow it into a silent "unknown".
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List

DEFAULT_RESIDENT_CAPACITY = 3


class ResidentServiceCapacityError(Exception):
    """Raised when acquiring a resident-service slot would exceed capacity."""


@dataclass
class ResidentServiceLease:
    """A held resident-service slot."""

    lease_id: str
    kind: str
    acquired_at: float = field(default_factory=time.monotonic)


class ResidentServiceRegistry:
    """Thread-safe in-process registry with a hard capacity cap (default 3)."""

    def __init__(self, capacity: int = DEFAULT_RESIDENT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._lock = threading.RLock()
        self._leases: Dict[str, ResidentServiceLease] = {}

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._leases)

    @property
    def is_full(self) -> bool:
        with self._lock:
            return len(self._leases) >= self._capacity

    def acquire(self, lease_id: str, kind: str) -> ResidentServiceLease:
        """Claim a resident-service slot, or raise if the cap is exceeded.

        Re-acquiring an already-held ``lease_id`` is idempotent (returns the
        existing lease) so adapters may call it defensively.
        """

        if not lease_id or not isinstance(lease_id, str):
            raise ValueError("lease_id must be a non-empty string")
        if not kind or not isinstance(kind, str):
            raise ValueError("kind must be a non-empty string")
        with self._lock:
            existing = self._leases.get(lease_id)
            if existing is not None:
                return existing
            if len(self._leases) >= self._capacity:
                active = sorted(self._leases)
                raise ResidentServiceCapacityError(
                    f"resident service capacity {self._capacity} exceeded: "
                    f"cannot acquire '{lease_id}' ({kind}); active={active}"
                )
            lease = ResidentServiceLease(lease_id, kind)
            self._leases[lease_id] = lease
            return lease

    def release(self, lease_id: str) -> None:
        """Release a slot.  Idempotent: releasing an unheld id is a no-op."""

        with self._lock:
            self._leases.pop(lease_id, None)

    def active(self) -> List[ResidentServiceLease]:
        """Snapshot of currently held leases."""

        with self._lock:
            return list(self._leases.values())

    def reset(self) -> None:
        """Drop all leases.  Intended for tests / explicit teardown only."""

        with self._lock:
            self._leases.clear()


__all__ = [
    "DEFAULT_RESIDENT_CAPACITY",
    "ResidentServiceCapacityError",
    "ResidentServiceLease",
    "ResidentServiceRegistry",
]
