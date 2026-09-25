"""Tests for the F7 live-values layer (product gate 1-2-3).

These cover the read-only JSON payload shape and the inspector DOM hooks the
poller targets. The HTTP contract (endpoint + script resource) is asserted in
test_ui_host; the poller's in-page behaviour is covered by the served-script
assertions there and by manual browser checks.
"""

import json
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.composition import CompositionOwner
from zworkbench.ui_home import _render_run_facts
from zworkbench.ui_host import LIVE_FACTS_ROUTE, serve_workbench
from zworkbench.ui_live import live_facts_payload, live_script
from zworkbench.ui_view_model import home_view_model, owner_view_source

#: A loopback host must be reached directly; a machine-wide proxy would answer.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(base, path):
    request = urllib.request.Request(base + path)
    try:
        with _DIRECT.open(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, ""


#: Extracts (key, text) from every ``data-live="key"`` hook in rendered markup.
_LIVE_RE = re.compile(r'data-live="([A-Za-z_]+)"[^>]*>([^<]*)<')


def _extract_live_values(html):
    return _LIVE_RE.findall(html)


#: The F7 inspector field set; every scalar must be owner-backed and live.
_FACT_KEYS = (
    "run_id",
    "parent_child",
    "mode",
    "workspace",
    "worker",
    "approval",
    "effect",
)


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


class RunFactsLiveConsistencyTests(unittest.TestCase):
    """F7/1-2-6 — the inspector shell and the live endpoint share one owner-backed source.

    1-2-3 built the F7 live layer (the ``/api/home-facts`` endpoint re-projects
    the owner-backed ``run_facts`` view on every poll, and the poller refreshes
    the inspector's ``data-live`` hooks in place). This class locks that contract
    so a future drift between the rendered shell and the live payload is caught.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        owner = CompositionOwner(Path(self.directory.name) / "owner.sqlite3")
        self.owner = owner
        owner.create_run("run-1", "interactive_run", {"prompt": "x"}, {})
        owner.start_run("run-1")
        self.host = serve_workbench(view_source=owner_view_source(owner))
        self.addCleanup(self.host.close)
        self.addCleanup(owner.close)
        self.addCleanup(self.directory.cleanup)

    def test_shell_and_endpoint_agree_on_owner_backed_values(self):
        facts = home_view_model(self.owner)["run_facts"]
        html = _render_run_facts(facts)
        rendered = dict(_extract_live_values(html))
        expected = live_facts_payload({"run_facts": facts})
        _, body = _get(self.host.base_url, LIVE_FACTS_ROUTE)
        payload = json.loads(body)
        for key in _FACT_KEYS:
            with self.subTest(field=key):
                self.assertIn(key, expected)
                self.assertIn(key, payload)
                # shell initial value == projection scalar == live payload scalar
                self.assertEqual(payload[key], expected[key])
                self.assertEqual(rendered.get(key, "unknown"), expected[key])

    def test_live_endpoint_reprojects_owner_changes(self):
        # Not a cached snapshot: a new latest run must drive the live payload.
        _, first = _get(self.host.base_url, LIVE_FACTS_ROUTE)
        self.assertEqual(json.loads(first)["run_id"], "run-1")
        self.owner.create_run("run-2", "interactive_run", {"prompt": "y"}, {})
        self.owner.start_run("run-2")
        _, second = _get(self.host.base_url, LIVE_FACTS_ROUTE)
        self.assertEqual(json.loads(second)["run_id"], "run-2")


if __name__ == "__main__":
    unittest.main()
