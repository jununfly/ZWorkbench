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
import html as html_module
import json
import re
import socket
import sys
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import (
    LIVE_FACTS_ROUTE,
    LIVE_SCRIPT_ROUTE,
    REVIEW_SCRIPT_ROUTE,
    serve_workbench,
)
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


class ServedTokensResolveAgainstTheBuildStoreTests(unittest.TestCase):
    """ADR 0006: one build identity. Before this, the host served per-module
    digests while the store addressed artifacts by the whole-tree receipt, and
    a reviewer's copied token answered ``manifest-missing`` on the same tree.
    """

    def test_a_served_token_resolves_against_a_receipt_built_store(self):
        import tempfile

        from zworkbench.ui_build import build_ui_artifacts
        from zworkbench.ui_manifest import load_manifest

        with tempfile.TemporaryDirectory() as store:
            build_ui_artifacts(
                Path(__file__).resolve().parents[1], Path(store)
            )
            host = serve_workbench(
                view_source=lambda route: {"records": [{"title": "run-one"}]},
                review=True,
            )
            self.addCleanup(host.close)
            _, _, document = fetch(host.base_url, "/home")
            match = re.search(
                r'data-ui-panel-tokens=\'([^\']+)\'', document
            )
            self.assertIsNotNone(match)
            tokens = json.loads(html_module.unescape(match.group(1)))
            token = json.loads(tokens["home.record-list.item"]["wide"])
            resolved = load_manifest(
                Path(store), ui_map=token["ui_map"], build=token["build"]
            )
        self.assertEqual(resolved["outcome"], "found")


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

    def test_an_idle_preconnected_socket_does_not_block_real_requests(self):
        """Browsers preconnect: they open a TCP connection and say nothing on
        it until a navigation needs it. A single-threaded server blocks in
        ``recv`` on that idle socket and every real request queues behind it --
        the page loads forever while the host looks perfectly healthy."""
        host = serve_workbench()
        self.addCleanup(host.close)
        host_port = int(host.base_url.rsplit(":", 1)[1])
        idle = socket.create_connection(("127.0.0.1", host_port), timeout=5)
        self.addCleanup(idle.close)
        # The idle connection never sends a byte; the real request must still
        # be answered promptly on its own connection.
        status, _, body = fetch(host.base_url, "/home")
        self.assertEqual(status, 200)
        self.assertIn("home", body)

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


class StartupBuildIdentityTests(unittest.TestCase):
    """ADR 0006: the receipt is computed once, at startup, and fails loud there.

    The first version computed it lazily inside the first request, so an
    unreadable source surfaced as a dropped connection on a healthy-looking
    service. The decision record puts the failure at the startup line.
    """

    def test_an_unreadable_source_fails_at_startup_before_serving(self):
        with unittest.mock.patch(
            "zworkbench.ui_host.build_receipt",
            side_effect=OSError("source tree unreadable"),
        ):
            with self.assertRaises(OSError):
                serve_workbench()

    def test_the_receipt_is_computed_once_at_startup_not_per_request(self):
        """Mutation target: routing requests through _served_build() (or
        recomputing per request) must fail this, and a cache that skips the
        startup read entirely must fail it too -- exactly one startup read."""
        calls = []
        real = __import__("zworkbench.ui_host", fromlist=["build_receipt"]).build_receipt

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        with unittest.mock.patch("zworkbench.ui_host.build_receipt", counting):
            host = serve_workbench()
            self.addCleanup(host.close)
            fetch(host.base_url, "/home")
            fetch(host.base_url, "/task-detail")
            fetch(host.base_url, "/home")
        self.assertEqual(len(calls), 1)


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


class TheReviewBehaviourLayerTests(unittest.TestCase):
    """ADR 0005 -- the script exists only where review mode does.

    Not linking it in normal mode is not enough on its own: a resource that is
    still served can be fetched and injected. Refusing the route unless the
    host was started in review mode makes the absence structural, which is the
    same reasoning that keeps review mode out of the query string.
    """

    def setUp(self):
        self.plain = serve_workbench(view_source=lambda route: {})
        self.addCleanup(self.plain.close)
        self.review = serve_workbench(view_source=lambda route: {}, review=True)
        self.addCleanup(self.review.close)

    def _get(self, base, path):
        request = urllib.request.Request(base + path)
        try:
            with DIRECT.open(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, ""

    def test_review_mode_serves_the_behaviour_layer(self):
        status, body = self._get(self.review.base_url, REVIEW_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("clipboard", body)

    def test_normal_mode_does_not_serve_it_at_all(self):
        status, _ = self._get(self.plain.base_url, REVIEW_SCRIPT_ROUTE)
        self.assertEqual(status, 404)

    def test_normal_documents_carry_no_script_except_home_live(self):
        # F7/1-2-3 introduces exactly one scoped exception to the "normal
        # documents carry no script" convention: /home may load the live
        # poller (/static/live.js). task-detail and record-view stay
        # script-free in normal mode, and the review layer must still be absent.
        for route in ("/task-detail", "/record-view"):
            with self.subTest(route=route):
                _, body = self._get(self.plain.base_url, route)
                self.assertNotIn("<script", body)
        _, home = self._get(self.plain.base_url, "/home")
        self.assertIn(LIVE_SCRIPT_ROUTE, home)
        self.assertNotIn(REVIEW_SCRIPT_ROUTE, home)
        # The live script is a separate resource, not inline executable text.
        self.assertNotIn("setInterval", home)

    def test_live_facts_endpoint_serves_read_only_json(self):
        # The live endpoint re-projects /home's facts: it must answer JSON and
        # never carry a business action or a script.
        status, body = self._get(self.plain.base_url, LIVE_FACTS_ROUTE)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("evidence_count", data)
        self.assertNotIn("<script", body)

    def test_live_script_resource_is_served(self):
        status, body = self._get(self.plain.base_url, LIVE_SCRIPT_ROUTE)
        self.assertEqual(status, 200)
        self.assertIn("/api/home-facts", body)
        self.assertIn("setInterval", body)

    def test_the_behaviour_layer_is_a_separate_resource_not_inline_text(self):
        """The document stays free of executable text, so it can be diffed."""
        _, body = self._get(self.review.base_url, "/home")
        self.assertIn(REVIEW_SCRIPT_ROUTE, body)
        self.assertNotIn("navigator.clipboard", body)


if __name__ == "__main__":
    unittest.main()
