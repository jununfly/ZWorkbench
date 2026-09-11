"""Behaviour tests for the workbench host's public HTTP contract.

The seam under test is the loopback entry point, observed through real HTTP
requests. Nothing here reaches into the request handler: a rewrite of the
handler must not disturb these tests.

ADR 0003 fixes two properties that are easy to lose silently, so both are
asserted here rather than left to a later stage: the page is served over
http://127.0.0.1 (not file:// or data:, which are not secure contexts), and the
document carries a viewport meta (without it a narrow-viewport assertion passes
while measuring the fallback layout viewport).
"""

import contextlib
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_record_view import record_manifest
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_task_detail import task_detail_manifest

#: Route -> the manifest a response on that route must agree with.
VIEWS = (
    ("/home", home_manifest),
    ("/task-detail", task_detail_manifest),
    ("/record-view", record_manifest),
)


#: A loopback host must be reached directly. A machine-wide proxy would
#: otherwise answer in its place, and an assertion about "the host refused"
#: would really be recording what the proxy said.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.headers, response.read().decode("utf-8")


class ServingTheHomeViewTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_the_home_view_is_served_over_loopback(self):
        status, headers, body = fetch(self.host.base_url, "/home")
        self.assertTrue(self.host.base_url.startswith("http://127.0.0.1:"))
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("data-ui-ref", body)

    def test_the_served_document_declares_a_viewport_meta(self):
        _, _, body = fetch(self.host.base_url, "/home")
        self.assertIn('name="viewport"', body)

    def test_the_served_markup_uses_only_declared_references(self):
        _, _, body = fetch(self.host.base_url, "/home")
        self.assertEqual(audit_rendered_html(home_manifest(), body)["undeclared"], ())


class HostLifecycleTests(unittest.TestCase):
    """1-1-3 fixed this: a host that leaks its socket is not an exit path."""

    def test_a_closed_host_stops_answering(self):
        host = serve_workbench()
        base = host.base_url
        fetch(base, "/home")
        host.close()
        with self.assertRaises(urllib.error.URLError):
            fetch(base, "/home")

    def test_closing_twice_is_not_an_error(self):
        host = serve_workbench()
        host.close()
        host.close()

    def test_a_failing_body_still_releases_the_host(self):
        host = serve_workbench()
        base = host.base_url
        try:
            with contextlib.closing(host):
                raise RuntimeError("simulated failure inside a test body")
        except RuntimeError:
            pass
        with self.assertRaises(urllib.error.URLError):
            fetch(base, "/home")


class ServingEveryDeclaredViewTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_every_declared_view_has_a_route(self):
        for route, _ in VIEWS:
            with self.subTest(route=route):
                status, _, body = fetch(self.host.base_url, route)
                self.assertEqual(status, 200)
                self.assertIn("data-ui-ref", body)

    def test_every_view_serves_only_its_own_declared_references(self):
        for route, manifest_of in VIEWS:
            with self.subTest(route=route):
                _, _, body = fetch(self.host.base_url, route)
                self.assertEqual(audit_rendered_html(manifest_of(), body)["undeclared"], ())

    def test_a_path_that_is_not_a_view_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            fetch(self.host.base_url, "/owner-snapshot")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
