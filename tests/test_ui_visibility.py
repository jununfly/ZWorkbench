"""Behaviour tests for locating a unit that is not on the page.

A manifest says a semantic unit exists somewhere in the view; only the rendered
document says it exists *here*. Deciding from the manifest alone reported
success for a reference no element carried, and the reviewer then saw an
unmarked page with no explanation.

``unavailable`` (declared, but the state that renders it does not hold) and
``unknown-reference`` (never declared) are kept apart on purpose: they call for
different fixes.
"""

import sys
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import locate, serve_workbench
from zworkbench.ui_token import build_deep_link
from zworkbench.ui_view_model import owner_view_source

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


class LocatingAHiddenUnitTests(unittest.TestCase):
    """1-5-2 — a unit that is not on this page answers ``unavailable``."""

    def setUp(self):
        self.manifest = home_manifest()

    def test_a_declared_unit_absent_from_the_document_is_unavailable(self):
        empty = "<main></main>"
        outcome = locate(
            self.manifest,
            "ui_ref=home.record-list.item&ui_map=" + self.manifest["ui_map"],
            empty,
        )
        self.assertEqual(outcome["outcome"], "unavailable")

    def test_unavailable_is_distinct_from_never_declared(self):
        """The two need different fixes, so they must not share one word."""
        rendered = "<main></main>"
        unknown = locate(
            self.manifest,
            "ui_ref=home.invented&ui_map=" + self.manifest["ui_map"],
            rendered,
        )
        self.assertEqual(unknown["outcome"], "unknown-reference")

    def test_an_empty_list_makes_its_item_unavailable_over_http(self):
        """A real hidden state: no records, so no row exists to point at."""
        host = serve_workbench(view_source=lambda route: {"records": []})
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertIn("unavailable", body)
        self.assertNotIn("data-ui-located=", body)

    def test_the_same_link_locates_the_item_once_a_record_exists(self):
        """Without this the test above would pass on a permanently broken link."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(owner.close)
        owner.create_run("run-one", "local_read_only_run", {})
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertIn('data-ui-located="home.record-list.item"', body)
        self.assertNotIn("unavailable", body)

    def test_an_unavailable_link_does_not_fall_back_to_another_element(self):
        host = serve_workbench(view_source=lambda route: {"records": []})
        self.addCleanup(host.close)
        _, body = fetch(
            host.base_url, build_deep_link(self.manifest, "home.record-list.item")
        )
        self.assertEqual(body.count("data-ui-located="), 0)


if __name__ == "__main__":
    unittest.main()
