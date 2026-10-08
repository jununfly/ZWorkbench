"""1-3-1: DSH adapter process_group_clean / orphan detection (setsid escape).

The worker is spawned with ``start_new_session=True`` (pgid == pid).  Any child
that calls ``os.setsid()`` becomes its own session leader and therefore escapes
``os.killpg`` aimed at the parent group.  ``detect_orphan_processes`` must find
those escapes so the exit receipt never reports a false ``orphan_processes: 0``.

Process enumeration uses ``ps``, which is unavailable in some sandboxes; in
that case ``detect_orphan_processes`` returns ``None`` and the receipt records
``UNKNOWN`` (fail-closed).  The pure filtering logic is tested against injected
snapshots so coverage does not depend on host ``ps`` access.
"""

import os
import signal
import subprocess
import sys
import time
import unittest

from zworkbench.worker_bridge import (
    _collect_descendants,
    _find_orphans_in_tree,
    _iter_all_processes,
    detect_orphan_processes,
)

LEAF_LIFETIME = 5.0


def _spawn_leader(*, setsid_child: bool) -> int:
    """Spawn a short-lived python leader that forks a child.

    The child optionally calls ``os.setsid()`` (escape) and then sleeps; the
    leader also sleeps so both are alive while we inspect.  Returns the leader
    pid.
    """

    child_body = "os.setsid()\n" if setsid_child else ""
    code = (
        "import os, time\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        f"    {child_body}"
        f"    time.sleep({LEAF_LIFETIME})\n"
        "    os._exit(0)\n"
        f"time.sleep({LEAF_LIFETIME})\n"
        "os._exit(0)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", code])
    return proc.pid


class OrphanPureLogicTest(unittest.TestCase):
    # (pid, ppid, pgid, sid)
    TREE = [
        (1, 0, 1, 1),        # init / session root
        (100, 1, 100, 100),  # worker leader: own session (start_new_session)
        (101, 100, 100, 100),  # normal child, same session
        (102, 100, 102, 102),  # setsid child: new session -> escape
        (103, 102, 102, 102),  # grandchild of the setsid child
        (200, 1, 200, 200),  # unrelated process
    ]

    def test_finds_setsid_escape_descendants(self):
        orphans = _find_orphans_in_tree(100, self.TREE)
        self.assertEqual(set(orphans), {102, 103})

    def test_excludes_same_session_child(self):
        # pid 101 shares session 100 -> not an orphan.
        self.assertNotIn(101, _find_orphans_in_tree(100, self.TREE))

    def test_excludes_unrelated_process(self):
        self.assertNotIn(200, _find_orphans_in_tree(100, self.TREE))

    def test_root_absent_yields_empty(self):
        self.assertEqual(_find_orphans_in_tree(999, self.TREE), [])

    def test_collect_descendants_recurses(self):
        self.assertEqual(set(_collect_descendants(100, self.TREE)), {101, 102, 103})


class OrphanEnumerationTest(unittest.TestCase):
    def test_unsupported_enumeration_returns_none(self):
        # In a sandbox where ``ps`` is blocked, enumeration is None and the
        # wrapper must surface None so the receipt records UNKNOWN (never 0).
        if _iter_all_processes() is not None:
            self.skipTest("ps enumeration available on this host")
        self.assertIsNone(detect_orphan_processes(12345))

    def test_dead_root_returns_none(self):
        # A root that never existed cannot be walked -> None (fail-closed).
        self.assertIsNone(detect_orphan_processes(2 ** 30))


class OrphanLiveTest(unittest.TestCase):
    """Runs only where host ``ps`` enumeration is available."""

    @classmethod
    def setUpClass(cls):
        if _iter_all_processes() is None:
            raise unittest.SkipTest("ps enumeration unavailable on this host")

    def _kill_tree(self, root_pid: int) -> None:
        tree = _iter_all_processes() or []
        pids = _collect_descendants(root_pid, tree) + [root_pid]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def test_detect_finds_setsid_child(self):
        leader = _spawn_leader(setsid_child=True)
        try:
            time.sleep(0.3)
            orphans = detect_orphan_processes(leader)
            self.assertIsNotNone(orphans)
            self.assertGreaterEqual(len(orphans), 1, orphans)
        finally:
            self._kill_tree(leader)

    def test_detect_excludes_normal_child(self):
        leader = _spawn_leader(setsid_child=False)
        try:
            time.sleep(0.3)
            orphans = detect_orphan_processes(leader)
            self.assertIsNotNone(orphans)
            self.assertEqual(orphans, [], orphans)
        finally:
            self._kill_tree(leader)

    def test_orphan_is_killed_after_sweep(self):
        leader = _spawn_leader(setsid_child=True)
        try:
            time.sleep(0.3)
            orphans = detect_orphan_processes(leader)
            self.assertIsNotNone(orphans)
            self.assertGreaterEqual(len(orphans), 1)
            for pid in orphans:
                os.kill(pid, signal.SIGKILL)
            time.sleep(0.2)
            for pid in orphans:
                self.assertRaises(
                    (ProcessLookupError, PermissionError), os.kill, pid, 0
                )
        finally:
            self._kill_tree(leader)


if __name__ == "__main__":
    unittest.main()
