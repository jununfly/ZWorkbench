"""1-7-4 — a deep link locates, and does nothing else.

``tests/test_ui_deep_link.py`` covers the happy path and the ways a link can
fail to locate. This file covers the ways a link must fail to *act*: it may not
restore business state, enable review mode, expand anything it was not aimed
at, trigger the preflight action, or carry an instruction the host obeys.

The distinction being defended is that a link is a coordinate, not a command.
Everything it can reach is already on the page; what it adds is a marker saying
"this one". A locator that quietly grew side effects would be far more
dangerous than one that failed loudly, because it would be used casually --
pasted into chats, reopened weeks later, followed by someone who was not there.
"""

import json
import sys
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import REVIEW_SCRIPT_ROUTE, serve_workbench
from zworkbench.ui_host import REVIEW_HINT
from zworkbench.ui_record_view import record_manifest
from zworkbench.ui_task_detail import task_detail_manifest
from zworkbench.ui_token import build_deep_link
from zworkbench.ui_view_model import owner_view_source

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: Everything review mode puts in a document. A deep link must produce none of
#: it; tests/test_ui_deep_link.py pins this list against a real review page.
REVIEW_MARKERS = (
    "data-ui-overlay",
    'data-ui-panel="review"',
    "data-ui-review-entry",
    REVIEW_SCRIPT_ROUTE,
)


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


class ALinkCannotEnableReviewModeTests(unittest.TestCase):
    """Review mode is a start-up choice, so this is structural, not a filter."""

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def _follow(self, **parameters):
        return fetch(
            self.host.base_url, "/home?" + urllib.parse.urlencode(parameters)
        )

    def test_no_parameter_spelling_turns_review_on(self):
        """Tried several ways, because a whitelist is only as good as its default.

        The host never reads a review flag from a request at all, so each of
        these is refused by construction rather than by being listed.
        """
        manifest = home_manifest()
        for name in ("review", "mode", "annotate", "ui_review", "review_mode"):
            for value in ("1", "on", "true", "review"):
                _, body = self._follow(
                    ui_ref="home.record-list", ui_map=manifest["ui_map"], **{name: value}
                )
                for marker in REVIEW_MARKERS:
                    with self.subTest(parameter=name, value=value, marker=marker):
                        self.assertNotIn(marker, body)

    def test_an_unknown_parameter_does_not_even_reach_the_locator(self):
        """An extra key invalidates the link rather than being ignored.

        Ignoring unknown keys is how a link from a future version half-works:
        it would locate correctly while silently dropping the part that
        mattered.
        """
        manifest = home_manifest()
        _, body = self._follow(
            ui_ref="home.record-list", ui_map=manifest["ui_map"], extra="x"
        )
        self.assertNotIn("data-ui-located=", body)


class ALinkCannotRestoreBusinessStateTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(self.owner.close)
        for name in ("run-one", "run-two"):
            self.owner.create_run(name, "local_read_only_run", {"prompt": "inspect"})
        self.host = serve_workbench(view_source=owner_view_source(self.owner))
        self.addCleanup(self.host.close)

    def test_the_located_page_differs_from_the_plain_page_only_by_annotation(self):
        """The whole claim in one assertion: a marker, a mode hint, nothing else.

        Subtracting the located marker and the review-mode hint must yield the
        unparameterised page byte for byte. Any state a link restored -- an
        expanded section, a selected record, a different status -- would
        survive the subtraction. The hint is annotation, not state: it tells
        the reviewer the mode is off rather than quietly turning it on.
        """
        link = build_deep_link(home_manifest(), "home.record-list.item")
        _, located = fetch(self.host.base_url, link)
        _, plain = fetch(self.host.base_url, "/home")
        self.assertIn("data-ui-located=", located)
        self.assertEqual(
            located.replace(' data-ui-located="home.record-list.item"', "").replace(
                REVIEW_HINT, ""
            ),
            plain,
        )

    def test_a_link_to_a_detail_view_does_not_select_a_different_run(self):
        """The view model is the facade's decision, not the link's."""
        link = build_deep_link(task_detail_manifest(), "task-detail.timeline")
        _, located = fetch(self.host.base_url, link)
        _, plain = fetch(self.host.base_url, "/task-detail")
        self.assertEqual(
            located.replace(' data-ui-located="task-detail.timeline"', "").replace(
                REVIEW_HINT, ""
            ),
            plain,
        )

    def test_following_a_link_repeatedly_changes_no_owner_state(self):
        before = self.owner.state_digest()
        link = build_deep_link(home_manifest(), "home.record-list.item")
        for _ in range(5):
            fetch(self.host.base_url, link)
        self.assertEqual(self.owner.state_digest(), before)


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; this surface stays unknown",
)
class ALinkFollowedWithoutReviewModeSaysSoTests(unittest.TestCase):
    """The PRD's middle path: never silently enable, never silently annotate.

    A link followed on a host without the review layer still locates -- that
    is pure annotation -- but the page must say review mode is off and how to
    enter it explicitly, instead of presenting a located mark as if the mode
    were on.
    """

    def test_normal_mode_locates_and_prompts_for_explicit_review_mode(self):
        host = serve_workbench()
        self.addCleanup(host.close)
        link = build_deep_link(home_manifest(), "home.record-list")
        _, body = fetch(host.base_url, link)
        self.assertIn('data-ui-review-hint="off"', body)
        self.assertIn("data-ui-located=", body)
        self.assertNotIn("review.js", body)

    def test_review_mode_needs_no_hint(self):
        host = serve_workbench(review=True)
        self.addCleanup(host.close)
        link = build_deep_link(home_manifest(), "home.record-list")
        _, body = fetch(host.base_url, link)
        self.assertNotIn("data-ui-review-hint", body)
        self.assertIn('data-ui-overlay="review"', body)

    def test_a_link_that_finds_nothing_gets_no_hint(self):
        """The failure notice already says what happened; a mode hint on top
        of it would suggest the link half-worked."""
        host = serve_workbench()
        self.addCleanup(host.close)
        manifest = home_manifest()
        _, body = fetch(
            host.base_url,
            "/home?ui_ref=home.invented-element&ui_map={0}".format(manifest["ui_map"]),
        )
        self.assertIn("unknown-reference", body)
        self.assertNotIn("data-ui-review-hint", body)


class ALinkPerformsNoActionInARealEngineTests(unittest.TestCase):
    """What a string comparison cannot see: what the engine did on load."""

    def setUp(self):
        self.clicks = []
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(self.owner.close)
        self.owner.create_run("run-one", "local_read_only_run", {"prompt": "inspect"})
        self.host = serve_workbench(view_source=owner_view_source(self.owner))
        self.addCleanup(self.host.close)

    def _observe(self, path):
        with browser() as engine:
            engine.open(self.host.base_url + path, viewport=(1280, 900))
            return json.loads(engine.evaluate("""
              JSON.stringify({
                located: Array.from(document.querySelectorAll('[data-ui-located]'))
                  .map(node => node.getAttribute('data-ui-located')),
                openDisclosures: Array.from(document.querySelectorAll('details'))
                  .filter(node => node.open).length,
                totalDisclosures: document.querySelectorAll('details').length,
                focused: document.activeElement === document.body
                  ? null
                  : document.activeElement.getAttribute('data-ui-ref'),
                scripts: document.querySelectorAll('script').length,
                locatedVisible: (() => {
                  const node = document.querySelector('[data-ui-located]');
                  return node ? node.checkVisibility() : null;
                })(),
              })
            """))

    def test_a_link_marks_exactly_one_element(self):
        link = build_deep_link(home_manifest(), "home.record-list.item")
        observed = self._observe(link)
        self.assertEqual(observed["located"], ["home.record-list.item"])

    def test_a_link_does_not_move_focus_on_load(self):
        """Marking is not focusing: a link may not hijack the caret.

        Deciding otherwise would be a legitimate design choice, but it is not
        the one made here, and an accidental focus move is how a link starts
        interfering with whatever the reviewer was doing.
        """
        link = build_deep_link(home_manifest(), "home.record-list.item")
        self.assertIsNone(self._observe(link)["focused"])

    def test_a_link_opens_only_the_disclosure_its_target_sits_behind(self):
        """Serving one disclosure open is navigation; opening all is a change.

        The comparison is against the same page without the link, so a view
        with no disclosures cannot make this pass by accident. The record view
        is the one that uses disclosures: the detail-level units live behind
        ``<details>`` by design.
        """
        plain = self._observe("/record-view")
        link = build_deep_link(record_manifest(), "record-view.replay-metadata")
        located = self._observe(link)
        self.assertGreater(located["totalDisclosures"], 0)
        self.assertEqual(located["openDisclosures"], plain["openDisclosures"] + 1)

    def test_the_opened_disclosure_is_the_one_the_target_lives_in(self):
        """Opening one is not enough; it must be the right one.

        A renderer that always opened the first disclosure would satisfy the
        count and reveal nothing, which is the failure this catches.
        """
        link = build_deep_link(record_manifest(), "record-view.replay-metadata")
        observed = self._observe(link)
        self.assertEqual(observed["located"], ["record-view.replay-metadata"])
        visible = observed["locatedVisible"]
        self.assertTrue(visible)

    def test_a_link_loads_no_script_into_a_normal_page(self):
        """Review mode brings the only script there is; a link brings none."""
        link = build_deep_link(home_manifest(), "home.record-list.item")
        self.assertEqual(self._observe(link)["scripts"], 0)


if __name__ == "__main__":
    unittest.main()
