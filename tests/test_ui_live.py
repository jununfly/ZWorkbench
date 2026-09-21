"""Tests for the F7 live-values layer (product gate 1-2-3).

These cover the read-only JSON payload shape and the inspector DOM hooks the
poller targets. The HTTP contract (endpoint + script resource) is asserted in
test_ui_host; the poller's in-page behaviour is covered by the served-script
assertions there and by manual browser checks.
"""

import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_home import _render_run_facts
from zworkbench.ui_host import LIVE_FACTS_ROUTE
from zworkbench.ui_live import live_facts_payload, live_script


class LiveFactsPayloadTests(unittest.TestCase):
    def test_scalar_fields_pass_through(self):
        facts = {
            "status": "running",
            "run_id": "run-123",
            "mode": "local_read_only_run",
            "workspace": "ws-1",
            "worker": "provider · model",
            "approval": "approved",
            "effect": "applied",
            "source": "CompositionOwner",
        }
        payload = live_facts_payload({"run_facts": facts})
        for key, value in facts.items():
            self.assertEqual(payload[key], value)

    def test_lists_and_dicts_are_excluded_but_summarised(self):
        links = [{"title": "e1"}, {"title": "e2"}]
        facts = {
            "status": "completed",
            "evidence_links": links,
            "evidence": {"mode": "recorded_view"},
        }
        payload = live_facts_payload({"run_facts": facts})
        self.assertNotIn("evidence_links", payload)
        self.assertNotIn("evidence", payload)
        self.assertEqual(payload["evidence_count"], 2)

    def test_missing_run_facts_yields_empty_payload(self):
        self.assertEqual(live_facts_payload({}), {"evidence_count": 0})
        self.assertEqual(
            live_facts_payload({"run_facts": "unknown"}), {"evidence_count": 0}
        )

    def test_status_label_is_derived_from_token(self):
        payload = live_facts_payload({"run_facts": {"status": "running"}})
        self.assertEqual(payload["status_label"], "进行中")
        # Unknown tokens fall back to themselves.
        payload = live_facts_payload({"run_facts": {"status": "weird"}})
        self.assertEqual(payload["status_label"], "weird")


class InspectorDomHookTests(unittest.TestCase):
    def test_inspector_carries_live_hooks(self):
        facts = {
            "status": "running",
            "run_id": "run-1",
            "parent_child": "none",
            "mode": "local_read_only_run",
            "workspace": "ws-1",
            "worker": "p · m",
            "approval": "unknown",
            "effect": "unknown",
            "evidence_links": [{"title": "e1"}],
            "source": "CompositionOwner",
        }
        html = _render_run_facts(facts)
        for key in (
            "run_id",
            "parent_child",
            "mode",
            "workspace",
            "worker",
            "approval",
            "effect",
        ):
            self.assertIn('data-live="{0}"'.format(key), html)
        # Status chip container and evidence count are live targets too.
        self.assertIn('data-live="status"', html)
        self.assertIn('data-live="evidence_count"', html)
        # No executable text is injected by the renderer itself.
        self.assertNotIn("<script", html)


class LiveScriptTests(unittest.TestCase):
    def test_script_points_at_the_live_endpoint_and_polls(self):
        script = live_script()
        self.assertIn(LIVE_FACTS_ROUTE, script)
        self.assertIn("setInterval", script)
        # The poller must update existing nodes, never build HTML from JSON.
        self.assertNotIn("innerHTML", script)
        # It must be syntactically valid JavaScript.
        try:
            import subprocess

            compiled = subprocess.run(
                ["node", "--check", "-"],
                input=script.encode("utf-8"),
                capture_output=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode("utf-8"))
        except FileNotFoundError:
            # Node not on PATH in this environment; skip the syntax gate.
            self.skipTest("node not available for JS syntax check")


if __name__ == "__main__":
    unittest.main()
