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
    UNKNOWN,
    UI_REFERENCE_STATUS_CATALOG,
    display_text,
    home_view_model,
    owner_view_source,
    record_view_model,
    task_detail_view_model,
    ui_reference_collab_view_model,
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

    def test_the_home_run_facts_use_recorded_provider_and_evidence_identity(self):
        self.owner.record_replay_metadata(
            "run-alpha",
            "run-alpha:recorded-view",
            "recorded_view",
            "event-digest-1",
            "environment-digest-1",
            {"provider": "loopback", "model": "fixture-model"},
        )

        facts = home_view_model(self.owner)["run_facts"]

        self.assertEqual(facts["workspace"], "case-local")
        self.assertEqual(facts["provider"], "loopback")
        self.assertEqual(facts["model"], "fixture-model")
        self.assertEqual(facts["event_digest"], "event-digest-1")
        self.assertEqual(facts["environment_digest"], "environment-digest-1")
        self.assertEqual(facts["evidence"], "recorded_view")

    def test_the_home_lists_owner_recorded_artifact_metadata(self):
        self.owner.record_result(
            "run-alpha",
            "artifact",
            {
                "name": "summary.json",
                "path": "case-local/artifacts/summary.json",
                "digest": "artifact-digest-1",
                "bytes": 128,
                "private_note": "must not be projected",
            },
            source_id="artifact-1",
        )

        artifacts = home_view_model(self.owner)["artifacts"]

        self.assertEqual(artifacts[0]["title"], "summary.json")
        self.assertEqual(artifacts[0]["path"], "case-local/artifacts/summary.json")
        self.assertEqual(artifacts[0]["digest"], "artifact-digest-1")
        self.assertEqual(artifacts[0]["bytes"], 128)
        self.assertNotIn("private_note", artifacts[0])

    def test_the_home_lists_owner_event_evidence_without_event_payloads(self):
        self.owner.record_event(
            "run-alpha",
            "evidence.saved",
            {"digest": "evidence-digest-1", "private_note": "must not be projected"},
            event_id="event-evidence-1",
        )

        evidence = home_view_model(self.owner)["evidence"]
        saved = next(item for item in evidence if item["title"] == "evidence.saved")

        self.assertEqual(saved["source"], "CompositionOwner")
        self.assertEqual(saved["identity"], "event-evidence-1")
        self.assertNotIn("private_note", json.dumps(evidence, ensure_ascii=False))

    def test_the_home_explains_a_recorded_preflight_denial(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-denied",
                "local_read_only_run",
                {"prompt": "不会开始执行"},
                metadata={
                    "preflight": {
                        "status": "deny",
                        "mode": "local_read_only",
                        "config_digest": "config-denied-1",
                        "allowed": False,
                        "checks": {"workspace_inside_case": False},
                        "violations": [
                            {
                                "code": "workspace_outside_case_root",
                                "message": "workspace must remain inside the case",
                            }
                        ],
                    }
                },
            )

            preflight = home_view_model(owner)["preflight_result"]

            self.assertEqual(preflight["status"], "deny")
            self.assertFalse(preflight["allowed"])
            self.assertEqual(preflight["checks"]["workspace_inside_case"], False)
            self.assertEqual(
                preflight["violations"][0]["code"],
                "workspace_outside_case_root",
            )
            self.assertEqual(preflight["source"], "Owner / recorded preflight")

    def test_the_home_record_keeps_identity_status_and_last_activity(self):
        record = home_view_model(self.owner)["records"][0]

        self.assertEqual(record["run_id"], "run-alpha")
        self.assertEqual(record["status"], "completed")
        self.assertTrue(record["updated_at"])

    def test_an_empty_owner_yields_a_view_that_says_so(self):
        """No runs is a legible state, not a crash and not a fake row."""
        with TemporaryDirectory() as empty:
            owner = CompositionOwner(Path(empty) / "owner.sqlite3")
            self.addCleanup(owner.close)
            view = home_view_model(owner)
            self.assertEqual(view["records"], [])
            self.assertEqual(view["run_facts"]["status"], "unknown")

    def test_the_home_view_projects_recorded_context_with_provenance(self):
        """The workbench context comes from durable owner facts, not guesses."""
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-context",
                "local_read_only_run",
                {"prompt": "检查仓库的 UI 记录"},
                metadata={
                    "workspace": "case-local",
                    "workspace_mode": "local_read_only",
                    "plan": [
                        {
                            "title": "读取已保存记录",
                            "status": "running",
                            "description": "只读读取 Owner 事件",
                        }
                    ],
                    "preflight": {
                        "status": "pass",
                        "mode": "local_read_only",
                        "config_digest": "config-123",
                    },
                },
            )

            view = home_view_model(owner)

            self.assertEqual(view["workspace"]["name"], "case-local")
            self.assertEqual(view["workspace"]["mode"], "local_read_only")
            self.assertEqual(view["workspace"]["source"], "CompositionOwner")
            self.assertEqual(view["intent"]["summary"], "已记录输入")
            self.assertEqual(view["intent"]["source"], "Owner / recorded input")
            self.assertEqual(view["plan"]["steps"][0]["title"], "读取已保存记录")
            self.assertEqual(view["plan"]["steps"][0]["description"], "只读读取 Owner 事件")
            self.assertEqual(view["preflight_result"]["status"], "pass")
            self.assertEqual(view["preflight_result"]["source"], "Owner / recorded preflight")

    def test_partial_workspace_identity_stays_unknown(self):
        """A name without scope cannot prove a usable workspace boundary."""
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-partial-workspace",
                "local_read_only_run",
                {"prompt": "检查边界"},
                metadata={"workspace": "case-local"},
            )

            workspace = home_view_model(owner)["workspace"]

            self.assertEqual(workspace["status"], "unknown")
            self.assertEqual(workspace["source"], "source unknown")

    def test_empty_workspace_identity_stays_unknown(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-empty-workspace",
                "local_read_only_run",
                {},
                metadata={"workspace": "", "workspace_mode": "local_read_only"},
            )

            workspace = home_view_model(owner)["workspace"]

            self.assertEqual(workspace["status"], "unknown")
            self.assertEqual(workspace["source"], "source unknown")

    def test_the_home_view_uses_the_public_safe_stopped_status(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-safe-stop", "local_read_only_run", {})
            owner.safe_stop_run("run-safe-stop", "missing identity")

            facts = home_view_model(owner)["run_facts"]

            self.assertEqual(facts["status"], "safe-stopped")


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


class ProjectingTaskDetailAdmissionTests(unittest.TestCase):
    def test_task_detail_explains_a_denied_preflight_without_exposing_prompt(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-denied-detail",
                "local_read_only_run",
                {"prompt": "读取 /Users/canary/private.md 并总结"},
                metadata={
                    "preflight": {
                        "status": "deny",
                        "mode": "local_read_only",
                        "allowed": False,
                        "checks": {"workspace_inside_case": False},
                        "violations": [
                            {
                                "code": "workspace_outside_case_root",
                                "message": "workspace must remain inside the case",
                            }
                        ],
                    }
                },
            )

            model = task_detail_view_model(owner, "run-denied-detail")

            self.assertEqual(model["intent"]["task_type"], "local_read_only_run")
            self.assertEqual(model["intent"]["summary"], "已记录输入")
            self.assertEqual(model["intent"]["source"], "Owner / recorded input")
            self.assertEqual(model["admission"]["status"], "denied")
            self.assertEqual(model["admission"]["source"], "Owner / recorded preflight")
            self.assertEqual(
                model["denial"]["violations"][0]["code"],
                "workspace_outside_case_root",
            )
            self.assertEqual(model["identity"]["run_id"], "run-denied-detail")
            self.assertNotIn("/Users/canary", json.dumps(model, ensure_ascii=False))

    def test_worker_completion_does_not_complete_a_parent_with_incomplete_identity(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "parent-incomplete",
                "worker_diff_run",
                {"prompt": "检查隔离工作区"},
                metadata={
                    "parent_run_id": "parent-incomplete",
                    "child_run_id": "child-worker",
                    "attempt_id": "attempt-1",
                },
            )
            owner.start_run("parent-incomplete")
            owner.record_result(
                "parent-incomplete",
                "worker.completed",
                {"status": "completed"},
                source_id="child-worker",
            )

            model = task_detail_view_model(owner, "parent-incomplete")

            self.assertEqual(model["admission"]["status"], "running")
            self.assertEqual(model["identity"]["run_id"], "parent-incomplete")
            self.assertEqual(model["identity"]["parent_run_id"], "parent-incomplete")
            self.assertEqual(model["identity"]["child_run_id"], "child-worker")
            self.assertEqual(model["identity"]["attempt_id"], "attempt-1")
            self.assertEqual(model["identity"]["provider"], "unknown")
            self.assertEqual(model["identity"]["status"], "unknown")
            self.assertEqual(model["result"], "unknown")

    def test_an_uncertain_effect_is_shown_as_pending_reconcile(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run(
                "run-pending-reconcile",
                "worker_diff_run",
                {"prompt": "检查副作用状态"},
                metadata={
                    "parent_run_id": "run-pending-reconcile",
                    "child_run_id": "child-worker",
                    "attempt_id": "attempt-1",
                    "provider_identity": {
                        "provider": "loopback",
                        "model": "fixture-model",
                        "endpoint": "loopback://fixture",
                        "transport": "fixture",
                    },
                },
            )
            owner.start_run("run-pending-reconcile")
            claim = owner.claim_effect(
                "run-pending-reconcile",
                "op-1",
                "write",
                "case-local-fixture",
                "idem-1",
                "idempotent",
            )
            owner.mark_effect_uncertain(claim.effect_id, "worker interrupted")

            model = task_detail_view_model(owner, "run-pending-reconcile")

            self.assertEqual(model["admission"]["status"], "recovering")
            self.assertEqual(model["effect"]["status"], "uncertain")
            self.assertEqual(model["reconcile"]["status"], "pending")
            self.assertEqual(model["result"], "unknown")

    def test_approval_required_effect_shows_the_exact_pending_approval_scope(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-approval", "worker_diff_run", {})
            owner.start_run("run-approval")
            owner.request_approval(
                "run-approval",
                "op-approval",
                "write",
                "case-local-fixture",
                "idem-approval",
                "explicit confirmation required",
            )
            claim = owner.claim_effect(
                "run-approval",
                "op-approval",
                "write",
                "case-local-fixture",
                "idem-approval",
                "approval-required",
            )

            model = task_detail_view_model(owner, "run-approval")

            self.assertEqual(claim.status, "denied")
            self.assertEqual(model["admission"]["status"], "waiting_approval")
            self.assertEqual(model["approval"]["status"], "pending")
            self.assertEqual(model["approval"]["operation_id"], "op-approval")
            self.assertEqual(model["approval"]["action"], "write")
            self.assertEqual(model["approval"]["resource"], "case-local-fixture")
            self.assertEqual(model["approval"]["idempotency_key"], "idem-approval")

    def test_unknown_external_outcome_stays_safe_stopped_in_the_detail_model(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-unknown-outcome", "worker_diff_run", {})
            owner.start_run("run-unknown-outcome")
            claim = owner.claim_effect(
                "run-unknown-outcome",
                "op-unknown",
                "write",
                "case-local-fixture",
                "idem-unknown",
                "idempotent",
            )
            owner.mark_effect_uncertain(claim.effect_id, "worker interrupted")
            owner.reconcile_effect(claim.effect_id, "unknown", {"source": "fixture"})

            model = task_detail_view_model(owner, "run-unknown-outcome")

            self.assertEqual(model["admission"]["status"], "safe-stopped")
            self.assertEqual(model["effect"]["status"], "unknown")
            self.assertEqual(model["reconcile"]["status"], "unknown")
            self.assertEqual(model["result"], "unknown")

    def test_task_detail_keeps_the_owner_event_order_and_source(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-timeline", "local_read_only_run", {})
            owner.start_run("run-timeline")
            owner.record_event("run-timeline", "preflight.passed", {"private": "hidden"})
            owner.record_event("run-timeline", "worker.started", {"private": "hidden"})

            timeline = task_detail_view_model(owner, "run-timeline")["timeline"]

            self.assertEqual(timeline["source"], "CompositionOwner")
            self.assertEqual(
                [event["type"] for event in timeline["events"][-2:]],
                ["preflight.passed", "worker.started"],
            )
            self.assertNotIn("private", json.dumps(timeline, ensure_ascii=False))

    def test_task_detail_shows_owner_recorded_replay_provenance(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-replay-detail", "local_read_only_run", {})
            owner.record_replay_metadata(
                "run-replay-detail",
                "replay-detail-1",
                "recorded_view",
                "event-digest-1",
                "environment-digest-1",
                {"provider": "loopback", "model": "fixture-model"},
                {"cassette": "not-used-by-recorded-view"},
            )

            replay = task_detail_view_model(owner, "run-replay-detail")["replay"]

            self.assertEqual(replay["mode"], "recorded_view")
            self.assertEqual(replay["source_event_digest"], "event-digest-1")
            self.assertEqual(replay["environment_digest"], "environment-digest-1")
            self.assertEqual(replay["provider"], "loopback")
            self.assertEqual(replay["model"], "fixture-model")
            self.assertEqual(replay["source"], "CompositionOwner")

    def test_failed_owner_run_projects_a_redacted_error_instead_of_a_result(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-failed-detail", "local_read_only_run", {})
            owner.start_run("run-failed-detail")
            owner.fail_run(
                "run-failed-detail",
                {"code": "provider_timeout", "message": "fixture provider stopped"},
            )

            model = task_detail_view_model(owner, "run-failed-detail")

            self.assertEqual(model["admission"]["status"], "failed")
            self.assertEqual(model["result"], "unknown")
            self.assertEqual(model["error"]["code"], "provider_timeout")
            self.assertEqual(model["error"]["message"], "fixture provider stopped")
            self.assertEqual(model["error"]["source"], "CompositionOwner")


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

    def test_no_view_model_carries_an_absolute_local_path_out_of_the_owner(self):
        self.owner.create_run(
            "run-path",
            "local_read_only_run",
            {"prompt": "查看记录"},
            metadata={
                "workspace": "/Users/canary/secret-project",
                "workspace_mode": "local_read_only",
            },
        )

        view = home_view_model(self.owner)

        self.assertNotIn("/Users/canary", json.dumps(view, ensure_ascii=False))

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

    def test_the_served_home_page_shows_owner_context_without_the_raw_prompt(self):
        body = self._home()

        self.assertIn("local_read_only_run", body)
        self.assertIn("case-local", body)
        self.assertIn("Owner / recorded input", body)
        self.assertNotIn("summarise the repository", body)

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

    def test_the_served_task_detail_explains_denial_without_python_repr_or_prompt(self):
        owner = CompositionOwner(Path(self.directory.name) / "denied.sqlite3")
        self.addCleanup(owner.close)
        owner.create_run(
            "run-denied-http",
            "local_read_only_run",
            {"prompt": "读取 /Users/canary/private.md 并总结"},
            metadata={
                "preflight": {
                    "status": "deny",
                    "mode": "local_read_only",
                    "allowed": False,
                    "checks": {"workspace_inside_case": False},
                    "violations": [
                        {
                            "code": "workspace_outside_case_root",
                            "message": "workspace must remain inside the case",
                        }
                    ],
                }
            },
        )
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)

        with DIRECT.open(host.base_url + "/task-detail", timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertIn("denied", body)
        self.assertIn("workspace_outside_case_root", body)
        self.assertIn("Owner / recorded preflight", body)
        self.assertNotIn("{'status':", body)
        self.assertNotIn("&#x27;status&#x27;", body)
        self.assertNotIn("/Users/canary", body)

    def test_the_served_task_detail_carries_recorded_replay_provenance(self):
        self.owner.record_replay_metadata(
            "run-alpha",
            "replay-http-1",
            "recorded_view",
            "event-digest-http",
            "environment-digest-http",
            {"provider": "loopback", "model": "fixture-model"},
        )

        with DIRECT.open(self.host.base_url + "/task-detail", timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertIn("recorded_view", body)
        self.assertIn("event-digest-http", body)
        self.assertIn("environment-digest-http", body)
        self.assertIn("fixture-model", body)

    def test_the_served_record_view_projects_the_latest_owner_record(self):
        owner = CompositionOwner(Path(self.directory.name) / "record-view.sqlite3")
        self.addCleanup(owner.close)
        owner.create_run("run-record-http", "local_read_only_run", {})
        owner.record_event(
            "run-record-http",
            "journal.note",
            {"private": "must not project"},
            event_id="event-record-http",
        )
        owner.record_result(
            "run-record-http",
            "semantic",
            {"status": "completed", "private_note": "must not project"},
            source_id="semantic-http",
        )
        owner.record_result(
            "run-record-http",
            "artifact",
            {
                "name": "summary.json",
                "path": "case-local/artifacts/summary.json",
                "digest": "artifact-http",
                "bytes": 16,
            },
            source_id="artifact-http",
        )
        owner.record_replay_metadata(
            "run-record-http",
            "replay-http-record",
            "recorded_view",
            "event-http",
            "environment-http",
            {"provider": "loopback", "model": "fixture-model"},
        )
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)

        with DIRECT.open(host.base_url + "/record-view", timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertIn("run-record-http", body)
        self.assertIn("journal.note", body)
        self.assertIn("artifact-http", body)
        self.assertIn("recorded_view", body)
        self.assertIn("record-view.mode-boundary", body)
        self.assertIn("live replay 默认不可用", body)
        self.assertNotIn("private", body)
        self.assertNotIn("&#x27;status&#x27;", body)

    def test_the_record_view_selects_and_filters_owner_facts_through_read_only_query(self):
        owner = CompositionOwner(Path(self.directory.name) / "record-selection.sqlite3")
        self.addCleanup(owner.close)
        owner.create_run("run-record-one", "local_read_only_run", {})
        owner.record_event("run-record-one", "worker.started", {}, event_id="event-one")
        owner.record_event("run-record-one", "provider.requested", {}, event_id="event-two")
        owner.create_run("run-record-two", "local_read_only_run", {})
        owner.record_event("run-record-two", "worker.completed", {}, event_id="event-three")
        host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(host.close)
        before = owner.state_digest()

        with DIRECT.open(
            host.base_url + "/record-view?run_id=run-record-one&filter=worker", timeout=5
        ) as response:
            body = response.read().decode("utf-8")

        self.assertIn("run-record-one", body)
        self.assertIn("worker.started", body)
        self.assertNotIn("provider.requested", body)
        self.assertNotIn("worker.completed", body)
        self.assertIn('name="run_id"', body)
        self.assertIn('value="run-record-one" selected', body)
        self.assertIn('name="filter"', body)
        self.assertIn('value="worker"', body)
        self.assertEqual(owner.state_digest(), before)

    def test_the_three_views_offer_explicit_read_only_navigation(self):
        for route in ("/home", "/task-detail", "/record-view"):
            with DIRECT.open(self.host.base_url + route, timeout=5) as response:
                body = response.read().decode("utf-8")
            with self.subTest(route=route):
                self.assertIn('href="/home"', body)
                self.assertIn('href="/task-detail"', body)
                self.assertIn('href="/record-view"', body)


class ProjectingRecordViewOwnerStateTests(unittest.TestCase):
    def test_record_view_lists_owner_event_identity_without_event_payload(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-record", "local_read_only_run", {})
            owner.record_event(
                "run-record",
                "journal.note",
                {"message": "visible only in owner", "private": "must not project"},
                event_id="event-journal-1",
            )

            model = record_view_model(owner, "run-record")

            event = next(item for item in model["events"] if item["type"] == "journal.note")
            self.assertEqual(event["event_id"], "event-journal-1")
            self.assertEqual(event["source"], "CompositionOwner")
            self.assertNotIn("private", json.dumps(model, ensure_ascii=False))
            self.assertNotIn("visible only in owner", json.dumps(model, ensure_ascii=False))

    def test_record_view_projects_result_artifact_and_replay_metadata(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-record-metadata", "local_read_only_run", {})
            owner.record_result(
                "run-record-metadata",
                "semantic",
                {
                    "status": "completed",
                    "text": "recorded semantic output",
                    "private_note": "must not project",
                },
                source_id="semantic-1",
            )
            owner.record_result(
                "run-record-metadata",
                "artifact",
                {
                    "name": "summary.json",
                    "path": "case-local/artifacts/summary.json",
                    "digest": "artifact-digest-1",
                    "bytes": 128,
                    "private_note": "must not project",
                },
                source_id="artifact-1",
            )
            owner.record_replay_metadata(
                "run-record-metadata",
                "replay-record-1",
                "recorded_view",
                "event-digest-record",
                "environment-digest-record",
                {"provider": "loopback", "model": "fixture-model"},
            )

            model = record_view_model(owner, "run-record-metadata")

            self.assertEqual(model["result"]["kind"], "semantic")
            self.assertEqual(model["result"]["status"], "completed")
            self.assertEqual(model["result"]["source"], "CompositionOwner")
            self.assertEqual(model["artifact_metadata"][0]["title"], "summary.json")
            self.assertEqual(model["artifact_metadata"][0]["digest"], "artifact-digest-1")
            self.assertEqual(model["replay_metadata"]["mode"], "recorded_view")
            self.assertEqual(model["replay_metadata"]["source_event_digest"], "event-digest-record")
            self.assertEqual(model["replay_metadata"]["provider"], "loopback")
            self.assertNotIn("private_note", json.dumps(model, ensure_ascii=False))
            self.assertNotIn("recorded semantic output", json.dumps(model, ensure_ascii=False))

    def test_record_view_filters_owner_events_without_changing_recorded_order(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            owner.create_run("run-filter", "local_read_only_run", {})
            owner.record_event("run-filter", "worker.started", {})
            owner.record_event("run-filter", "provider.requested", {})
            owner.record_event("run-filter", "worker.completed", {})

            model = record_view_model(owner, "run-filter", filter_text="worker")

            self.assertEqual(model["filter"]["query"], "worker")
            self.assertEqual(model["filter"]["matched"], 2)
            self.assertEqual(
                [event["type"] for event in model["events"]],
                ["worker.started", "worker.completed"],
            )
            self.assertEqual(model["filter"]["source"], "CompositionOwner")

            no_matches = record_view_model(owner, "run-filter", filter_text="missing")
            self.assertEqual(no_matches["state"], "no-filter-results")
            self.assertEqual(no_matches["events"], [])

    def test_record_view_keeps_empty_events_and_missing_metadata_explicit(self):
        with TemporaryDirectory() as directory:
            owner = CompositionOwner(Path(directory) / "owner.sqlite3")
            self.addCleanup(owner.close)
            model = record_view_model(owner, "missing-run")

            self.assertEqual(model["state"], "empty-events")
            self.assertEqual(model["events"], [])
            self.assertEqual(model["detail"], "unknown")
            self.assertEqual(model["artifact_metadata"], "unknown")
            self.assertEqual(model["replay_metadata"], "unknown")
            self.assertEqual(model["mode"], "recorded_view")


class ProjectingDshSessionReferencesSurfaceTests(unittest.TestCase):
    """F14: a named, dsh-web ``/session-references``-aligned read-only surface.

    The surface is derived only from the identity the facade already projected,
    so it proves the alignment claim without adding a runtime dependency (ADR 0007).
    """

    def _owner_with_identity(self, identity, provider_identity=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        owner = CompositionOwner(Path(directory.name) / "owner.sqlite3")
        self.addCleanup(owner.close)
        metadata = {"identity": identity}
        if provider_identity is not None:
            metadata["provider_identity"] = provider_identity
        owner.create_run("run-session", "local_read_only_run", {}, metadata=metadata)
        return owner

    def test_session_references_surface_exposes_dsh_session_and_turn_when_resolved(self):
        owner = self._owner_with_identity(
            {"dsh_session_id": "dsh-sess-1", "dsh_turn_id": "dsh-turn-1"},
            provider_identity={"provider": "loopback", "model": "fixture-model"},
        )

        refs = task_detail_view_model(owner, "run-session")["session_references"]

        self.assertEqual(refs["dsh_session_id"], "dsh-sess-1")
        self.assertEqual(refs["dsh_turn_id"], "dsh-turn-1")
        self.assertEqual(refs["provider"], "loopback")
        self.assertEqual(refs["model"], "fixture-model")
        self.assertEqual(refs["status"], "known")
        self.assertEqual(refs["source"], "CompositionOwner")

    def test_session_references_surface_stays_unknown_without_a_dsh_session(self):
        owner = self._owner_with_identity({"dsh_turn_id": "dsh-turn-1"})

        refs = task_detail_view_model(owner, "run-session")["session_references"]

        self.assertEqual(refs["dsh_session_id"], UNKNOWN)
        self.assertEqual(refs["dsh_turn_id"], "dsh-turn-1")
        self.assertEqual(refs["status"], UNKNOWN)

    def test_session_references_redacts_local_paths_from_the_dsh_session_id(self):
        owner = self._owner_with_identity(
            {"dsh_session_id": "/Users/canary/secret-session", "dsh_turn_id": "dsh-turn-1"}
        )

        refs = task_detail_view_model(owner, "run-session")["session_references"]

        self.assertNotIn("/Users/canary", refs["dsh_session_id"])
        self.assertEqual(refs["dsh_session_id"], "<local path>")
        self.assertEqual(refs["source"], "CompositionOwner")


class UiReferenceCollabProjectionTests(unittest.TestCase):
    """F15 r2 — r2-ui-reference-skills 协同可视化只读投影."""

    def test_home_view_model_carries_the_collab_surface_with_both_skills(self):
        owner = CompositionOwner(Path(TemporaryDirectory().name) / "owner.db")

        collab = home_view_model(owner)["ui_reference_collab"]

        skills = {skill["skill"]: skill for skill in collab["skills"]}
        self.assertIn("ui-reference-protocol", skills)
        self.assertIn("ui-reference-runtime", skills)
        self.assertEqual(collab["source"], "r2-ui-reference-skills (declared snapshot)")

    def test_profile_status_is_implemented_and_runtime_status_is_unknown(self):
        collab = ui_reference_collab_view_model()
        for skill in collab["skills"]:
            self.assertEqual(skill["profile_status"]["status"], "implemented")
            # honest: live runtime evidence is a product-gate concern
            self.assertEqual(skill["runtime_status"]["status"], "unknown")

    def test_unknown_runtime_status_surfaces_uncovered_items_and_next_evidence(self):
        collab = ui_reference_collab_view_model()
        runtime = next(
            s["runtime_status"] for s in collab["skills"] if s["skill"] == "ui-reference-runtime"
        )

        self.assertTrue(runtime["uncovered_items"])
        self.assertTrue(runtime["next_evidence"])
        self.assertIn("ZWorkbench 专属 profile 联调验证", runtime["next_evidence"][0])

    def test_status_catalog_passthrough_matches_the_r2_skill_contract(self):
        collab = ui_reference_collab_view_model()

        for skill in collab["skills"]:
            for dimension in ("profile_status", "runtime_status"):
                self.assertEqual(
                    tuple(skill[dimension]["status_catalog"]),
                    UI_REFERENCE_STATUS_CATALOG,
                )

    def test_collab_projection_redacts_secrets_and_local_paths(self):
        # A leaked credential or local path must not survive into the view model.
        collab = ui_reference_collab_view_model()

        payload = json.dumps(collab)
        self.assertNotIn(LEAKED_SECRET, payload)
        self.assertNotIn("/Users/canary", payload)

    def test_collab_projection_collapses_unknown_status_vocabulary(self):
        # An out-of-catalog status is folded to unknown rather than echoed.
        collab = ui_reference_collab_view_model()

        for skill in collab["skills"]:
            for dimension in ("profile_status", "runtime_status"):
                self.assertIn(skill[dimension]["status"], UI_REFERENCE_STATUS_CATALOG)


if __name__ == "__main__":
    unittest.main()
