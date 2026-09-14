"""Behaviour tests for the `zworkbench ui-host` entry point.

The seam under test is the real process boundary: the command is spawned as a
subprocess, observed over HTTP, then asked to exit. Nothing here imports the
handler.

That choice is what makes the exit assertions mean anything. Calling close()
in-process can only show that a socket object changed state; it cannot show
that the process is gone and the port was returned to the operating system.
Those are the two ways a local service entry point actually fails a user.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests,
#: so a "refused" assertion routed through it would record the proxy's reply.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

STARTUP_TIMEOUT = 15
EXIT_TIMEOUT = 10


class Service:
    """A spawned entry point, with a stop that always runs.

    Tests that assert about resource cleanup must not leak resources
    themselves: the pipes are closed here, otherwise the suite reports
    ResourceWarning for its own file descriptors and the signal gets
    attributed to the product.
    """

    def __init__(self, *extra):
        environment = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUNBUFFERED="1")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "zworkbench.cli", "ui-host", *extra],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            cwd=str(REPO),
        )
        self.announcement = json.loads(self.process.stdout.readline())
        self.base_url = self.announcement["base_url"]
        self.port = int(self.base_url.rsplit(":", 1)[1])

    def interrupt(self):
        """Ask for a clean stop and return the exit status."""
        self.process.send_signal(signal.SIGINT)
        return self.process.wait(timeout=EXIT_TIMEOUT)

    def read_remaining_output(self):
        return self.process.communicate(timeout=EXIT_TIMEOUT)[0]

    def stop(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=EXIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=EXIT_TIMEOUT)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def port_is_free(port):
    """Whether the operating system will hand the port back out."""
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


class AnnouncingTheServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = Service()
        self.addCleanup(self.service.stop)

    def test_the_entry_point_announces_a_loopback_url_before_serving(self):
        """Reading the line is enough; the port must already accept requests."""
        self.assertTrue(self.service.base_url.startswith("http://127.0.0.1:"))
        with DIRECT.open(self.service.base_url + "/home", timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_the_announcement_states_the_service_is_read_only(self):
        self.assertEqual(self.service.announcement["mode"], "read-only")


class ExitingCleanlyTests(unittest.TestCase):
    """A service that keeps the port or the process is not an exit path.

    What the port check can and cannot show was established by mutation. The
    operating system reclaims a port when the process dies, whether or not the
    server was closed first, so this assertion detects a process that fails to
    exit -- a serving thread that outlives the signal, for instance -- rather
    than a missing close(). That close() releases the socket is covered at the
    host seam, in test_ui_host.py::test_a_closed_host_stops_answering.
    """

    def test_an_interrupt_stops_the_process_and_frees_the_port(self):
        service = Service()
        self.addCleanup(service.stop)
        with DIRECT.open(service.base_url + "/home", timeout=5) as response:
            self.assertEqual(response.status, 200)

        self.assertEqual(service.interrupt(), 0)

        deadline = time.time() + 5
        while time.time() < deadline and not port_is_free(service.port):
            time.sleep(0.1)
        self.assertTrue(port_is_free(service.port), "the port was not returned on exit")

    def test_the_exit_is_reported_on_the_announcement_stream(self):
        service = Service()
        self.addCleanup(service.stop)
        service.process.send_signal(signal.SIGINT)
        closing = json.loads(service.read_remaining_output().strip().splitlines()[-1])
        self.assertEqual(closing["event"], "stopped")


class ReviewModeSwitchTests(unittest.TestCase):
    """Review mode is an explicit, default-off start-up choice (PRD Story 1/13).

    The CLI is the only shipped entry point, so the switch must exist here --
    a flag that only tests can pass is a feature users cannot reach.
    """

    def test_review_mode_is_off_by_default(self):
        service = Service()
        self.addCleanup(service.stop)
        self.assertIs(service.announcement["review"], False)
        with DIRECT.open(service.base_url + "/home", timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertNotIn('data-ui-overlay', body)
        self.assertNotIn('data-ui-panel', body)
        try:
            DIRECT.open(service.base_url + "/static/review.js", timeout=5)
            self.fail("review.js must not exist as a resource in normal mode")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 404)

    def test_the_announcement_states_whether_review_mode_is_on(self):
        service = Service("--review")
        self.addCleanup(service.stop)
        self.assertIs(service.announcement["review"], True)
        self.assertEqual(service.announcement["mode"], "read-only")

    def test_the_review_flag_serves_the_review_layer(self):
        service = Service("--review")
        self.addCleanup(service.stop)
        with DIRECT.open(service.base_url + "/home", timeout=5) as response:
            body = response.read().decode("utf-8")
        self.assertIn('data-ui-overlay="review"', body)
        self.assertIn('data-ui-panel="review"', body)
        self.assertIn("review.js", body)
        with DIRECT.open(service.base_url + "/static/review.js", timeout=5) as response:
            self.assertEqual(response.status, 200)


class RefusingToBecomeMoreThanAViewerTests(unittest.TestCase):
    def test_the_entry_point_takes_no_owner_database(self):
        environment = dict(os.environ, PYTHONPATH=str(SRC))
        result = subprocess.run(
            [sys.executable, "-m", "zworkbench.cli", "ui-host", "--db", "owner.sqlite3"],
            capture_output=True, text=True, env=environment, cwd=str(REPO), timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--db", result.stderr)

    def test_a_non_loopback_bind_address_is_refused(self):
        """The host renders review material; it is not for the network."""
        environment = dict(os.environ, PYTHONPATH=str(SRC))
        result = subprocess.run(
            [sys.executable, "-m", "zworkbench.cli", "ui-host", "--host", "0.0.0.0"],
            capture_output=True, text=True, env=environment, cwd=str(REPO), timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_serving_creates_no_files_in_the_working_directory(self):
        before = set(os.listdir(REPO))
        service = Service()
        self.addCleanup(service.stop)
        DIRECT.open(service.base_url + "/home", timeout=5).close()
        service.interrupt()
        self.assertEqual(set(os.listdir(REPO)) - before, set())


if __name__ == "__main__":
    unittest.main()
