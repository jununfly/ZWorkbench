"""Behaviour tests for the control-plane facade that feeds the views.

The seam under test is the facade's public functions, exercised against a real
CompositionOwner. The owner is this repository's own SQLite implementation, so
building genuine state costs less than maintaining a stand-in -- and a stand-in
would only prove the facade agrees with our idea of the owner.

Two properties are the reason this layer exists at all. The views must not read
owner storage themselves, and whatever reaches a view must already be redacted.
Both are asserted here against real durable state rather than described in a
docstring, which is all that backed them until now.
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import urllib.request

from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import home_manifest
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_view_model import (
    REDACTED,
    display_text,
    home_view_model,
    owner_view_source,
    record_view_model,
    task_detail_view_model,
)

#: See tests/test_ui_host.py: a machine-wide proxy answers loopback requests.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: A credential value the owner's field-name check does not catch: the key is
#: innocuous, the value is not. Free text is exactly where one turns up.
LEAKED_SECRET = "sk-live-000111222333444555666777"


def owner_with_state(directory):
    """Build durable state through the owner's public interface."""
    owner = CompositionOwner(Path(directory) / "owner.sqlite3")
    owner.create_run(
        "run-alpha",
        "local_read_only_run",
        {"prompt": "summarise the repository"},
        metadata={"workspace": "case-local"},
    )
    owner.start_run("run-alpha")
    owner.record_event("run-alpha", "worker.started", {"note": "read-only"})
    owner.complete_run("run-alpha", {"summary": "done"})
    return owner


class ProjectingOwnerStateForTheHomeViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = owner_with_state(self.directory.name)
        self.addCleanup(self.owner.close)

    def test_the_home_view_lists_the_runs_the_owner_holds(self):
        view = home_view_model(self.owner)
        self.assertEqual([record["title"] for record in view["records"]], ["run-alpha"])

    def test_the_home_view_reports_the_run_status_the_owner_recorded(self):
        self.assertEqual(home_view_model(self.owner)["run_facts"]["status"], "completed")

    def test_an_empty_owner_yields_a_view_that_says_so(self):
        """No runs is a legible state, not a crash and not a fake row."""
        with TemporaryDirectory() as empty:
            owner = CompositionOwner(Path(empty) / "owner.sqlite3")
            self.addCleanup(owner.close)
            view = home_view_model(owner)
            self.assertEqual(view["records"], [])
            self.assertEqual(view["run_facts"]["status"], "unknown")


class ReadingWithoutWritingTests(unittest.TestCase):
    """A view is a reader. The facade must not be able to change history."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = owner_with_state(self.directory.name)
        self.addCleanup(self.owner.close)

    def test_building_every_view_leaves_the_owner_state_unchanged(self):
        before = self.owner.state_digest()
        home_view_model(self.owner)
        task_detail_view_model(self.owner, "run-alpha")
        record_view_model(self.owner)
        self.assertEqual(self.owner.state_digest(), before)


class RedactingBeforeTheViewSeesAnythingTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.addCleanup(self.owner.close)
        self.owner.create_run(
            "run-leak",
            "local_read_only_run",
            {"prompt": "authenticate using " + LEAKED_SECRET},
            metadata={"note": LEAKED_SECRET},
        )

    def test_the_owner_itself_still_holds_the_secret(self):
        """Establishes that the next assertion is testing the facade.

        If the owner had rejected this input, a view free of the secret would
        prove nothing about redaction.
        """
        self.assertIn(LEAKED_SECRET, json.dumps(self.owner.snapshot()))

    def test_a_credential_inside_displayed_text_is_replaced(self):
        """Covers the value-level pass directly, because the whitelist hides it.

        Mutation showed that removing redaction entirely left every leak
        assertion green: none of the fields the facade selects happened to
        contain the secret, so the whitelist alone was doing the work. Field
        selection is the first defence, but it cannot be the only one -- a
        run_id or an event type is free text a caller chooses.
        """
        self.assertEqual(
            display_text("authenticate using " + LEAKED_SECRET),
            "authenticate using " + REDACTED,
        )

    def test_a_credential_in_a_field_the_view_does_show_is_redacted(self):
        """A run identifier is displayed, and its text is caller-supplied."""
        self.owner.create_run("run-" + LEAKED_SECRET, "local_read_only_run", {})
        titles = [record["title"] for record in home_view_model(self.owner)["records"]]
        self.assertIn("run-" + REDACTED, titles)
        self.assertNotIn(LEAKED_SECRET, json.dumps(titles))

    def test_no_view_model_carries_a_credential_out_of_the_owner(self):
        """The whitelist keeps unselected owner fields out of every view."""
        for name, view in (
            ("home", home_view_model(self.owner)),
            ("task-detail", task_detail_view_model(self.owner, "run-leak")),
            ("record", record_view_model(self.owner)),
        ):
            with self.subTest(view=name):
                self.assertNotIn(LEAKED_SECRET, json.dumps(view, ensure_ascii=False))

    def test_a_field_the_facade_does_not_name_never_reaches_a_view(self):
        """Selection is a whitelist: new owner columns are absent by default.

        A blacklist would admit anything nobody thought to exclude, which for
        a presentation layer means it leaks by default.
        """
        view = json.dumps(home_view_model(self.owner), ensure_ascii=False)
        self.assertNotIn("input_json", view)
        self.assertNotIn("metadata", view)


class ServingOwnerStateThroughTheHostTests(unittest.TestCase):
    """The path the PRD describes, end to end: owner -> facade -> document."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.owner = owner_with_state(self.directory.name)
        self.addCleanup(self.owner.close)
        self.host = serve_workbench(view_source=owner_view_source(self.owner))
        self.addCleanup(self.host.close)

    def _home(self):
        with DIRECT.open(self.host.base_url + "/home", timeout=5) as response:
            return response.read().decode("utf-8")

    def test_the_served_home_page_shows_a_run_the_owner_holds(self):
        self.assertIn("run-alpha", self._home())

    def test_the_list_item_reference_now_renders(self):
        """Until an owner supplied rows, this declared reference never rendered.

        The manifest declares a record-list item, so a coverage count that
        never saw one was reporting on markup the product could not produce.
        """
        audit = audit_rendered_html(home_manifest(), self._home())
        self.assertEqual(audit["instances"].get("home.record-list.item"), 1)
        self.assertEqual(audit["undeclared"], ())

    def test_the_served_page_carries_no_credential_from_the_owner(self):
        self.owner.create_run(
            "run-leak",
            "local_read_only_run",
            {"prompt": "authenticate using " + LEAKED_SECRET},
        )
        self.assertNotIn(LEAKED_SECRET, self._home())


if __name__ == "__main__":
    unittest.main()
