"""Tests for the resident service runtime registry (sub-07 Backlog #3).

The registry is pure in-process logic with no external dependencies, so these
tests are fully deterministic (no real processes, no ``ps`` enumeration).  The
final test exercises the real registry instance owned by a CompositionOwner to
prove the ≤3 cap is shared across adapter kinds within one execution session.
"""

import tempfile
import unittest
from pathlib import Path

from zworkbench.composition import CompositionOwner
from zworkbench.resident_service_registry import (
    DEFAULT_RESIDENT_CAPACITY,
    ResidentServiceCapacityError,
    ResidentServiceRegistry,
)


class ResidentServiceRegistryTests(unittest.TestCase):
    def test_default_capacity_is_three(self) -> None:
        registry = ResidentServiceRegistry()
        self.assertEqual(registry.capacity, DEFAULT_RESIDENT_CAPACITY)
        self.assertEqual(registry.active_count, 0)
        self.assertFalse(registry.is_full)

    def test_capacity_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            ResidentServiceRegistry(capacity=0)
        with self.assertRaises(ValueError):
            ResidentServiceRegistry(capacity=-1)

    def test_acquire_increments_active_count(self) -> None:
        registry = ResidentServiceRegistry()
        lease = registry.acquire("a", "codex-app-server")
        self.assertEqual(lease.lease_id, "a")
        self.assertEqual(lease.kind, "codex-app-server")
        self.assertEqual(registry.active_count, 1)
        self.assertFalse(registry.is_full)

    def test_reacquire_same_lease_is_idempotent(self) -> None:
        registry = ResidentServiceRegistry()
        first = registry.acquire("a", "codex-app-server")
        second = registry.acquire("a", "codex-app-server")
        self.assertIs(first, second)
        self.assertEqual(registry.active_count, 1)

    def test_release_is_idempotent_noop(self) -> None:
        registry = ResidentServiceRegistry()
        registry.acquire("a", "codex-app-server")
        registry.release("a")
        registry.release("a")  # unheld -> no-op
        self.assertEqual(registry.active_count, 0)
        registry.release("never-held")  # no-op, must not raise

    def test_exceed_capacity_raises_fail_closed(self) -> None:
        registry = ResidentServiceRegistry(capacity=3)
        registry.acquire("a", "codex-app-server")
        registry.acquire("b", "dsh-runtime")
        registry.acquire("c", "codex-app-server")
        self.assertTrue(registry.is_full)
        with self.assertRaises(ResidentServiceCapacityError) as ctx:
            registry.acquire("d", "dsh-runtime")
        self.assertIn("capacity 3 exceeded", str(ctx.exception))
        self.assertIn("'d'", str(ctx.exception))
        # The over-capacity lease was NOT recorded.
        self.assertEqual(registry.active_count, 3)

    def test_active_snapshot_reflects_held_leases(self) -> None:
        registry = ResidentServiceRegistry()
        registry.acquire("a", "codex-app-server")
        registry.acquire("b", "dsh-runtime")
        kinds = {lease.kind for lease in registry.active()}
        self.assertEqual(kinds, {"codex-app-server", "dsh-runtime"})
        self.assertEqual(registry.active_count, 2)

    def test_reset_clears_leases(self) -> None:
        registry = ResidentServiceRegistry()
        registry.acquire("a", "codex-app-server")
        registry.reset()
        self.assertEqual(registry.active_count, 0)

    def test_acquire_rejects_empty_lease_id_or_kind(self) -> None:
        registry = ResidentServiceRegistry()
        with self.assertRaises(ValueError):
            registry.acquire("", "codex-app-server")
        with self.assertRaises(ValueError):
            registry.acquire("a", "")


class OwnerSharedRegistryTests(unittest.TestCase):
    """The real registry is owned by CompositionOwner and shared across adapters."""

    def setUp(self) -> None:
        self.db = Path(tempfile.mkdtemp()) / "owner.db"
        self.owner = CompositionOwner(self.db)

    def tearDown(self) -> None:
        self.owner.close()

    def test_owner_exposes_resident_registry(self) -> None:
        self.assertIsInstance(self.owner.resident_registry, ResidentServiceRegistry)
        self.assertEqual(self.owner.resident_registry.capacity, 3)

    def test_cap_enforced_across_adapter_kinds_in_one_session(self) -> None:
        registry = self.owner.resident_registry
        # Two codex servers + one DSH runtime fit within the cap.
        registry.acquire("codex-app-server:/tmp/c1", "codex-app-server")
        registry.acquire("codex-app-server:/tmp/c2", "codex-app-server")
        registry.acquire("run-1", "dsh-runtime")
        self.assertEqual(registry.active_count, 3)
        self.assertTrue(registry.is_full)
        # A fourth resident service (any kind) is rejected fail-closed.
        with self.assertRaises(ResidentServiceCapacityError):
            registry.acquire("run-2", "dsh-runtime")
        # Freeing a slot re-opens capacity.
        registry.release("run-1")
        registry.acquire("run-2", "dsh-runtime")
        self.assertEqual(registry.active_count, 3)

    def test_reopened_owner_has_fresh_empty_registry(self) -> None:
        self.owner.resident_registry.acquire("a", "codex-app-server")
        self.owner.close()
        reopened = CompositionOwner(self.db)
        try:
            self.assertEqual(reopened.resident_registry.active_count, 0)
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
