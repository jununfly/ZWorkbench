"""1-7-3 — the read-only session reaches nothing and changes nothing.

Two claims, measured where each can actually fail.

*Zero remote requests* is asserted from the engine's own resource timeline
rather than from reading the source for suspicious strings. A page can reach
the network through a stylesheet import, a font, a favicon, a preconnect hint
or a script the document did not obviously name; only the engine knows what was
actually requested. Every entry must be the loopback host itself.

*Zero owner state change* is asserted as a digest taken before and after a full
review session -- serving all three views, following a deep link, selecting,
locking, copying and closing. The digest covers the owner's canonical state, so
a write anywhere in that path moves it.
"""

import json
import sys
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_token import build_deep_link
from zworkbench.ui_view_model import owner_view_source

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ROUTES = ("/home", "/task-detail", "/record-view")

#: Every resource the engine fetched for this document, by origin. Includes
#: subresources the markup never mentions by name.
RESOURCES = """
JSON.stringify({
  resources: performance.getEntriesByType('resource').map(entry => entry.name),
  document: location.origin,
})
"""


def seeded_owner(directory):
    owner = CompositionOwner(Path(directory) / "owner.sqlite3")
    for name in ("run-one", "run-two", "run-three"):
        owner.create_run(name, "local_read_only_run", {"prompt": "inspect"})
    return owner


class NotChangingOwnerStateTests(unittest.TestCase):
    """The owner is the durable source of truth; a viewer may not move it."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = seeded_owner(directory.name)
        self.addCleanup(self.owner.close)
        self.host = serve_workbench(
            view_source=owner_view_source(self.owner), review=True
        )
        self.addCleanup(self.host.close)

    def _fetch(self, path):
        with DIRECT.open(self.host.base_url + path, timeout=5) as response:
            return response.read().decode("utf-8")

    def test_the_digest_is_sensitive_enough_for_this_to_mean_anything(self):
        """A digest that never moves would make every assertion below free."""
        before = self.owner.state_digest()
        self.owner.create_run("run-four", "local_read_only_run", {})
        self.assertNotEqual(self.owner.state_digest(), before)

    def test_serving_every_view_changes_no_owner_state(self):
        before = self.owner.state_digest()
        for route in ROUTES:
            self._fetch(route)
        self.assertEqual(self.owner.state_digest(), before)

    def test_serving_the_same_view_repeatedly_changes_no_owner_state(self):
        """Accumulation is the failure a single request cannot show."""
        before = self.owner.state_digest()
        for _ in range(10):
            self._fetch("/home")
        self.assertEqual(self.owner.state_digest(), before)

    def test_following_a_deep_link_changes_no_owner_state(self):
        before = self.owner.state_digest()
        self._fetch(build_deep_link(home_manifest(), "home.record-list.item"))
        self.assertEqual(self.owner.state_digest(), before)

    def test_a_failing_deep_link_changes_no_owner_state(self):
        """The error path writes nothing either -- not even a record of itself."""
        before = self.owner.state_digest()
        self._fetch("/home?ui_ref=home.record-list&ui_map=" + "b" * 64)
        self.assertEqual(self.owner.state_digest(), before)

    def test_no_run_effect_or_approval_appears_during_a_served_session(self):
        """Stated against the counts, so a swap of equal size cannot hide.

        The tables come from the snapshot itself, not a hand-written list. A
        hand list went stale in practice: it named five tables while the owner
        already held seven, so two could have grown without a test noticing.
        """
        before = self.owner.snapshot()
        for route in ROUTES:
            self._fetch(route)
        after = self.owner.snapshot()
        for table, rows in before.items():
            if not isinstance(rows, list):
                continue
            with self.subTest(table=table):
                self.assertEqual(len(after[table]), len(rows))


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; the network surface stays unknown",
)
class NotReachingTheNetworkTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = seeded_owner(directory.name)
        self.addCleanup(self.owner.close)
        self.host = serve_workbench(
            view_source=owner_view_source(self.owner), review=True
        )
        self.addCleanup(self.host.close)

    def _load(self, path, interact=False):
        with browser() as engine:
            engine.open(self.host.base_url + path, viewport=(1280, 900))
            if interact:
                for action in ("select", "lock", "copy", "clear", "close"):
                    where = json.loads(engine.evaluate(
                        "(() => {"
                        "  const node = document.querySelector("
                        "    '[data-ui-panel-action=\\'" + action + "\\']');"
                        "  if (!node) return JSON.stringify({x: 0, y: 0});"
                        "  const box = node.getBoundingClientRect();"
                        "  return JSON.stringify({"
                        "    x: box.left + box.width / 2, y: box.top + box.height / 2});"
                        "})()"
                    ))
                    engine.click(where["x"], where["y"])
            return json.loads(engine.evaluate(RESOURCES))

    def test_every_view_fetches_only_from_the_host_itself(self):
        for route in ROUTES:
            observed = self._load(route)
            for resource in observed["resources"]:
                with self.subTest(route=route, resource=resource):
                    self.assertTrue(resource.startswith(observed["document"]))

    def test_the_timeline_is_not_empty_so_the_check_is_not_vacuous(self):
        """The stylesheet and the review layer are fetched, and are counted.

        An empty timeline would satisfy "every resource is local" trivially,
        which is how this assertion would rot if a future change stopped the
        subresources from loading.
        """
        observed = self._load("/home")
        self.assertTrue(observed["resources"])

    def test_a_full_review_interaction_fetches_nothing_further(self):
        """Selecting, copying and closing must not call anything home."""
        observed = self._load("/home", interact=True)
        for resource in observed["resources"]:
            with self.subTest(resource=resource):
                self.assertTrue(resource.startswith(observed["document"]))

    def test_the_document_origin_is_loopback(self):
        observed = self._load("/home")
        self.assertTrue(observed["document"].startswith("http://127.0.0.1:"))

    def test_a_review_interaction_changes_no_owner_state(self):
        """The engine-driven path, not just the HTTP one."""
        before = self.owner.state_digest()
        self._load("/home", interact=True)
        self.assertEqual(self.owner.state_digest(), before)


if __name__ == "__main__":
    unittest.main()
