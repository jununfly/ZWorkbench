"""Behaviour tests for consuming a review deep link at the host.

The seam under test is the host's HTTP contract: a request carrying ui_ref and
ui_map, observed through the response. build_deep_link has produced links since
the token work landed, but nothing consumed them -- the host discarded the
query string -- so the navigation the PRD describes did not exist.

A deep link is a locator used during review. It performs pure UI navigation:
it must not load a run, restore state, trigger preflight or turn on review
mode. These tests pin that alongside the happy path, because a locator that
quietly gains side effects is far worse than one that fails.
"""

import sys
import unittest
import unittest.mock
import unittest.mock
import urllib.parse
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_record_view import record_manifest
from zworkbench.ui_task_detail import task_detail_manifest
from zworkbench.ui_host import (
    REVIEW_HINT,
    REVIEW_SCRIPT_ROUTE,
    locate,
    render_document,
    serve_workbench,
)
from zworkbench.ui_token import build_deep_link
from zworkbench.ui_view_model import owner_view_source

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: A well-formed digest that no build produced.
FOREIGN_UI_MAP = "b" * 64


def fetch(base, path):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


class FollowingAValidDeepLinkTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)
        self.manifest = home_manifest()

    def test_a_generated_link_reaches_the_view_that_declares_the_reference(self):
        """The link builder and the host must agree without a translation step."""
        link = build_deep_link(self.manifest, "home.record-list")
        status, body = fetch(self.host.base_url, link)
        self.assertEqual(status, 200)
        self.assertIn('data-ui-ref="home.record-list"', body)

    def test_the_located_reference_is_marked_in_the_document(self):
        """A reviewer must be able to see which element was addressed."""
        link = build_deep_link(self.manifest, "home.preflight-run.action")
        _, body = fetch(self.host.base_url, link)
        self.assertIn('data-ui-located="home.preflight-run.action"', body)

    def test_only_one_instance_is_marked_when_the_reference_repeats(self):
        """A list item renders once per row, so the count has to bite.

        Mutation caught this: the first version addressed a singleton region,
        where marking "all matches" and "the first match" are the same thing,
        so removing the limit changed nothing.
        """
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(owner.close)
        for name in ("run-one", "run-two", "run-three"):
            owner.create_run(name, "local_read_only_run", {})
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)

        _, body = fetch(host.base_url, build_deep_link(self.manifest, "home.record-list.item"))
        self.assertEqual(body.count('data-ui-ref="home.record-list.item"'), 3)
        self.assertEqual(body.count("data-ui-located="), 1)


class OneElementPerStructuralReferenceTests(unittest.TestCase):
    """A structural reference names one element, so it must render exactly once.

    The page root used to borrow a child unit's reference (the record-picker,
    the intent region). The link then "located" the whole page: the marker
    lands on the first occurrence, and the first occurrence was <main>.
    Dedicated root units are what keep the located ring on the named unit.
    """

    VIEWS = (
        ("/home", home_manifest),
        ("/task-detail", task_detail_manifest),
        ("/record-view", record_manifest),
    )

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)

    def test_every_structural_reference_renders_exactly_once(self):
        for route, manifest_of in self.VIEWS:
            manifest = manifest_of()
            _, body = fetch(self.host.base_url, route)
            for entry in manifest["refs"]:
                if entry["kind"] == "list-item":
                    continue
                self.assertEqual(
                    body.count('data-ui-ref="{0}"'.format(entry["ref"])),
                    1,
                    "{0} renders {1} more than once".format(route, entry["ref"]),
                )

    def test_the_located_ring_lands_on_the_named_unit_not_the_page(self):
        for route, manifest_of, ref in (
            ("/task-detail", task_detail_manifest, "task-detail.intent"),
            ("/record-view", record_manifest, "record-view.record-picker"),
        ):
            manifest = manifest_of()
            _, body = fetch(
                self.host.base_url, build_deep_link(manifest, ref)
            )
            self.assertIn('data-ui-located="{0}"'.format(ref), body)
            self.assertNotIn(
                '<main data-ui-ref="{0}"'.format(ref), body,
                "{0} still borrows the page root for {1}".format(route, ref),
            )


class RetiredReferenceLinkTests(unittest.TestCase):
    """A retired reference gets its lifecycle outcome, not "unavailable".

    "Unavailable" tells the reviewer to reach the state that renders the unit;
    for a retired reference no such state exists, so that advice is always
    wrong. PRD story 9: old feedback must stay interpretable.
    """

    def _manifest_with_retired(self, replaced_by=None):
        manifest = home_manifest()
        entry = dict(manifest["refs"][0])
        entry["retired"] = True
        entry["replaced_by"] = replaced_by
        manifest["refs"] = [entry] + [
            dict(item) for item in manifest["refs"][1:]
        ]
        return manifest, entry["ref"]

    def test_a_retired_reference_reports_retired_with_its_replacement(self):
        manifest, ref = self._manifest_with_retired(replaced_by="home.record-list")
        outcome = locate(
            manifest, "ui_ref={0}&ui_map={1}".format(ref, manifest["ui_map"])
        )
        self.assertEqual(outcome["outcome"], "retired")
        self.assertEqual(outcome["replaced_by"], "home.record-list")

    def test_a_retired_reference_without_a_replacement_still_says_retired(self):
        manifest, ref = self._manifest_with_retired()
        outcome = locate(
            manifest, "ui_ref={0}&ui_map={1}".format(ref, manifest["ui_map"])
        )
        self.assertEqual(outcome["outcome"], "retired")
        self.assertNotIn("replaced_by", outcome)

    def test_the_served_notice_names_the_replacement(self):
        """Story 9 is honoured on the page, not only in locate()'s return value."""
        host = serve_workbench()
        self.addCleanup(host.close)
        manifest, ref = self._manifest_with_retired(replaced_by="home.record-list")
        with unittest.mock.patch(
            "zworkbench.ui_host.ROUTES",
            {"/home": ("工作台首页", lambda **kw: manifest, render_home)},
        ):
            _, body = fetch(
                host.base_url,
                "/home?ui_ref={0}&ui_map={1}".format(ref, manifest["ui_map"]),
            )
        self.assertIn('data-ui-link-outcome="retired"', body)
        self.assertIn('data-ui-link-replacement="home.record-list"', body)

    def test_unavailable_and_unknown_reference_keep_their_meanings(self):
        manifest = home_manifest()
        unavailable = locate(
            manifest,
            "ui_ref=home.record-list.item&ui_map={0}".format(manifest["ui_map"]),
            rendered="<main></main>",
        )
        self.assertEqual(unavailable["outcome"], "unavailable")
        unknown = locate(
            manifest,
            "ui_ref=home.never-declared&ui_map={0}".format(manifest["ui_map"]),
        )
        self.assertEqual(unknown["outcome"], "unknown-reference")


class RefusingALinkThatNoLongerLocatesAnythingTests(unittest.TestCase):
    """Failing visibly beats landing somewhere plausible.

    A deep link exists so two reviewers can look at the same element. Falling
    back to the unparameterised page would leave both believing they had, which
    is the failure mode worth spending assertions on.
    """

    def setUp(self):
        self.host = serve_workbench()
        self.addCleanup(self.host.close)
        self.manifest = home_manifest()

    def _follow(self, **parameters):
        query = urllib.parse.urlencode(parameters)
        return fetch(self.host.base_url, "/home?" + query)

    def test_a_link_from_a_different_mapping_version_says_so(self):
        status, body = self._follow(
            ui_ref="home.record-list", ui_map=FOREIGN_UI_MAP
        )
        self.assertEqual(status, 200)
        self.assertIn("ui-map-mismatch", body)

    def test_an_undeclared_reference_is_reported_as_such(self):
        """Distinct from a version mismatch: the two need different fixes."""
        _, body = self._follow(
            ui_ref="home.invented-element", ui_map=self.manifest["ui_map"]
        )
        self.assertIn("unknown-reference", body)
        self.assertNotIn("ui-map-mismatch", body)

    def test_a_failed_link_does_not_mark_any_element_as_located(self):
        _, body = self._follow(ui_ref="home.record-list", ui_map=FOREIGN_UI_MAP)
        self.assertNotIn("data-ui-located=", body)

    def test_a_parameter_outside_the_whitelist_is_refused(self):
        _, body = self._follow(
            ui_ref="home.record-list",
            ui_map=self.manifest["ui_map"],
            review="on",
        )
        self.assertNotIn("data-ui-located=", body)

    def test_the_rejection_does_not_echo_the_offending_input(self):
        """A reflected value is how a locator becomes an injection point.

        The link parser refuses this before the notice is built, so this
        assertion records the outcome of both defences together; the notice's
        own escaping is covered directly below.
        """
        _, body = self._follow(ui_ref="<script>alert(1)</script>", ui_map=FOREIGN_UI_MAP)
        self.assertNotIn("<script>alert(1)</script>", body)

    def test_the_document_escapes_a_hostile_outcome_before_showing_it(self):
        """Exercises the escaping at the point the product performs it.

        A first attempt called LINK_NOTICE.format directly with an already
        escaped value, which only demonstrated that the test could escape a
        string. Driving render_document with a manifest whose ui_map cannot
        match forces the real notice path.
        """
        hostile = {"outcome": "<script>alert(1)</script>"}
        with unittest.mock.patch("zworkbench.ui_host.locate", return_value=hostile):
            document = render_document("/home", {}, "ui_ref=x&ui_map=y")
        self.assertNotIn("<script>alert(1)</script>", document)
        self.assertIn("&lt;script&gt;", document)


class StayingAPureNavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.addCleanup(self.owner.close)
        self.owner.create_run("run-alpha", "local_read_only_run", {"prompt": "hello"})
        self.host = serve_workbench(view_source=owner_view_source(self.owner))
        self.addCleanup(self.host.close)

    def test_following_a_deep_link_changes_no_owner_state(self):
        before = self.owner.state_digest()
        fetch(self.host.base_url, build_deep_link(home_manifest(), "home.record-list"))
        self.assertEqual(self.owner.state_digest(), before)

    def test_a_deep_link_does_not_turn_on_review_mode(self):
        """Locating an element is not the same as starting an annotation.

        The markers are the ones review mode actually emits. An earlier version
        asserted the absence of ``data-ui-review-mode``, an attribute no
        renderer has ever produced, so it passed against every possible
        implementation -- including one that turned review mode fully on.
        """
        _, body = fetch(
            self.host.base_url, build_deep_link(home_manifest(), "home.record-list")
        )
        for marker in (
            "data-ui-overlay",
            'data-ui-panel="review"',
            "data-ui-review-entry",
            REVIEW_SCRIPT_ROUTE,
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, body)

    def test_those_markers_are_the_ones_review_mode_really_emits(self):
        """Pins the negative above to the product, not to a guessed spelling.

        A marker list that drifted from what the renderer emits would make the
        previous test vacuous again, silently.
        """
        review = serve_workbench(review=True)
        self.addCleanup(review.close)
        _, body = fetch(review.base_url, "/home")
        for marker in (
            "data-ui-overlay",
            'data-ui-panel="review"',
            "data-ui-review-entry",
            REVIEW_SCRIPT_ROUTE,
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)

    def test_the_page_content_is_the_same_with_and_without_the_link(self):
        _, plain = fetch(self.host.base_url, "/home")
        _, located = fetch(
            self.host.base_url, build_deep_link(home_manifest(), "home.record-list")
        )
        # The link adds annotation only: the located marker and, while review
        # mode is off, the hint that states the mode explicitly.
        self.assertEqual(
            located.replace(' data-ui-located="home.record-list"', "").replace(
                REVIEW_HINT, ""
            ),
            plain,
        )


if __name__ == "__main__":
    unittest.main()
