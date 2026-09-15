"""Cross-project evidence for the portable UI Reference skills."""

import importlib.util
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from browser import browser, chrome_available
from ui_reference_support import runtime_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "ui_reference_portability" / "v1"
FIXTURE = FIXTURE_ROOT / "catalog_adapter.py"
PROFILE = FIXTURE_ROOT / "profile.json"
PROFILE_VALIDATOR = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-protocol"
    / "scripts"
    / "validate_profile.py"
)
RUNTIME_STATUS = (
    REPO_ROOT
    / ".codex"
    / "skills"
    / "ui-reference-runtime"
    / "scripts"
    / "runtime_status.py"
)


def fixture_module():
    spec = importlib.util.spec_from_file_location("catalog_fixture", str(FIXTURE))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CrossProjectFixtureTests(unittest.TestCase):
    def test_fixture_has_a_semantic_coverage_matrix_independent_of_its_manifest(self):
        matrix = json.loads(
            (FIXTURE_ROOT / "coverage.json").read_text(encoding="utf-8")
        )
        module = fixture_module()

        self.assertEqual(matrix["schema"], "ui-ref-coverage/v1")
        self.assertGreaterEqual(len(matrix["units"]), 3)
        self.assertIn("catalog.item", matrix["units"])
        self.assertIn("pointer-passthrough", matrix["gates"])
        self.assertNotEqual(set(matrix["units"]), {entry["ref"] for entry in module.manifest()["refs"]})
        self.assertIn("dynamic-reorder", matrix["scenarios"])

    def test_the_second_profile_is_accepted_without_zworkbench_facts(self):
        result = subprocess.run(
            [sys.executable, str(PROFILE_VALIDATOR), str(PROFILE)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("zworkbench", result.stdout.lower())

    def test_the_fixture_uses_a_different_renderer_attribute_and_no_product_import(self):
        source = FIXTURE.read_text(encoding="utf-8")
        module = fixture_module()
        current = module.manifest()
        rendered = module.render_catalog([{"label": "Alpha"}], current)

        self.assertNotIn("from zworkbench", source.lower())
        self.assertNotIn("import zworkbench", source.lower())
        self.assertIn('data-ref="catalog.shell"', rendered)
        self.assertNotIn("data-ui-ref", rendered)
        self.assertEqual(len(current["refs"]), 4)

    def test_the_independent_fixture_completes_static_token_link_and_source_resolution(self):
        module = fixture_module()
        current = module.manifest()
        token = module.parse_review_token(
            module.review_token(current, "catalog.add")
        )
        link = module.deep_link(current, "catalog.shell")
        query = parse_qs(urlsplit(link).query, strict_parsing=True)

        self.assertEqual(token["ui_map"], current["ui_map"])
        self.assertEqual(token["build"], current["build"])
        self.assertEqual(query["ui_ref"], ["catalog.shell"])
        self.assertEqual(query["ui_map"], [current["ui_map"]])
        self.assertEqual(module.locate_source(current, "catalog.add")["outcome"], "found")

    def test_sensitive_canaries_stay_out_of_review_surfaces(self):
        module = fixture_module()
        current = module.manifest()
        canaries = (
            "prompt-canary",
            "credential-canary",
            "run-id-canary",
            "/private/absolute/path-canary",
            "event-body-canary",
        )
        item = {
            "label": "Safe label",
            "prompt": canaries[0],
            "credential": canaries[1],
            "run_id": canaries[2],
            "absolute_path": canaries[3],
            "event_body": canaries[4],
        }
        surfaces = (
            module.render_catalog([item], current),
            module.review_overlay(current, "catalog.item"),
            module.review_token(current, "catalog.item"),
            module.deep_link(current, "catalog.item"),
            json.dumps(module.review_log()),
            json.dumps(module.browser_persistence()),
        )

        for surface in surfaces:
            for canary in canaries:
                self.assertNotIn(canary, surface)

    def test_fixture_token_parser_rejects_duplicate_and_wrongly_typed_fields(self):
        module = fixture_module()
        current = module.manifest()
        token = module.review_token(current, "catalog.add")
        duplicate = token.replace(
            '"ref":"catalog.add"',
            '"ref":"catalog.add","ref":"catalog.add"',
        )

        with self.assertRaises(ValueError):
            module.parse_review_token(duplicate)

        typed = json.loads(token)
        typed["ref"] = 123
        with self.assertRaises(ValueError):
            module.parse_review_token(json.dumps(typed))

        with self.assertRaises(ValueError):
            module.parse_review_token("x" * 1025)

    def test_fixture_deep_link_parser_rejects_external_and_unknown_inputs(self):
        module = fixture_module()
        current = module.manifest()
        valid = module.deep_link(current, "catalog.shell")

        self.assertEqual(
            module.parse_deep_link(valid),
            {"ui_ref": "catalog.shell", "ui_map": current["ui_map"]},
        )
        with self.assertRaises(ValueError):
            module.parse_deep_link(valid + "&run_id=secret")
        with self.assertRaises(ValueError):
            module.parse_deep_link(
                "https://external.example/catalog?ui_ref=catalog.shell&ui_map="
                + current["ui_map"]
            )

    def test_fixture_overlay_rejects_an_undeclared_reference(self):
        module = fixture_module()

        with self.assertRaises(ValueError):
            module.review_overlay(module.manifest(), "catalog.unknown")

    def test_the_runtime_checker_preserves_unknown_before_host_evidence_exists(self):
        module = fixture_module()
        current = module.manifest()
        evidence = runtime_evidence(
            PROFILE,
            mapping_identity=current["ui_map"],
            build_identity=current["build"],
            browser="unknown",
            rendered={"declared": 4, "undeclared": 0},
            runtime_adapter="catalog-html@1",
            environment="catalog-html-fixture@1",
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")

    def test_the_runtime_checker_rejects_absolute_path_evidence(self):
        module = fixture_module()
        current = module.manifest()
        evidence = runtime_evidence(
            PROFILE,
            mapping_identity=current["ui_map"],
            build_identity=current["build"],
            environment="/Users/alice/catalog",
            rendered={"declared": 4, "undeclared": 0},
        )
        result = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "HOLD")


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; fixture host evidence stays unknown",
)
class IndependentFixtureHostTests(unittest.TestCase):
    def setUp(self):
        self.module = fixture_module()
        self.current = self.module.manifest()
        body = self.module.render_catalog_page(
            [
                {
                    "label": "Alpha",
                    "credential": "credential-canary",
                    "prompt": "prompt-canary",
                },
                {"label": "Beta"},
            ],
            self.current,
        ).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                if urlsplit(handler.path).path != "/catalog":
                    handler.send_response(404)
                    handler.end_headers()
                    return
                handler.send_response(200)
                handler.send_header("Content-Type", "text/html; charset=utf-8")
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(handler, format, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self.url = "http://127.0.0.1:{0}/catalog".format(self.server.server_port)

    def _rect(self, engine, selector):
        return json.loads(
            engine.evaluate(
                "JSON.stringify((() => { const r = document.querySelector(%r).getBoundingClientRect(); "
                "return {x:r.left+r.width/2,y:r.top+r.height/2}; })())" % selector
            )
        )

    def _click(self, engine, selector):
        point = self._rect(engine, selector)
        engine.click(point["x"], point["y"])

    def _snapshot(self, engine):
        return json.loads(engine.evaluate("JSON.stringify(window.__catalogReview.snapshot())"))

    def test_real_browser_preserves_pointer_passthrough_and_requires_panel_lock(self):
        with browser() as engine:
            engine.open(self.url, viewport=(1280, 900))
            self.assertFalse(self._snapshot(engine)["enabled"])
            self._click(engine, "#review-entry")
            first = self._rect(engine, "[data-ref='catalog.item']")
            engine.move(first["x"], first["y"])
            preview = self._snapshot(engine)
            self.assertTrue(preview["preview"])
            self.assertIsNone(preview["selection"])

            engine.click(first["x"], first["y"])
            self.assertEqual(self._snapshot(engine)["business_clicks"], 1)
            self._click(engine, "#review-entry")
            self._click(engine, "#lock")
            locked = self._snapshot(engine)
            self.assertEqual(locked["selection"], preview["preview"])
            self.assertEqual(locked["business_clicks"], 1)
            self.assertEqual(
                engine.evaluate(
                    "getComputedStyle(document.querySelector('[data-review-overlay]')).pointerEvents"
                ),
                "none",
            )

    def test_real_browser_tracks_dynamic_instances_across_reorder_remount_and_session_close(self):
        with browser() as engine:
            engine.open(self.url, viewport=(1280, 900))
            self._click(engine, "#review-entry")
            before = self._snapshot(engine)
            self.assertEqual(len(before["rows"]), 2)
            handles = {row["label"]: row["instance"] for row in before["rows"]}

            self._click(engine, "#reorder")
            after_reorder = self._snapshot(engine)
            self.assertEqual(
                handles,
                {row["label"]: row["instance"] for row in after_reorder["rows"]},
            )

            self._click(engine, "#unmount-first")
            unavailable = self._snapshot(engine)
            removed = unavailable["unmounted"][0]
            self.assertEqual(
                engine.evaluate("JSON.stringify(window.__catalogReview.resolve(%r))" % removed["instance"]),
                '{"outcome":"unavailable","ref":"catalog.item"}',
            )
            self._click(engine, "#remount-first")
            remounted = self._snapshot(engine)
            restored = next(row for row in remounted["rows"] if row["label"] == removed["label"])
            self.assertEqual(restored["instance"], removed["instance"])
            self._click(engine, "#rerender")
            rerendered = self._snapshot(engine)
            self.assertEqual(
                {row["label"]: row["instance"] for row in rerendered["rows"]},
                {row["label"]: row["instance"] for row in remounted["rows"]},
            )
            remaining = next(row for row in rerendered["rows"] if row["label"] != restored["label"])
            self._click(engine, "#delete-first")
            self.assertEqual(
                engine.evaluate("JSON.stringify(window.__catalogReview.resolve(%r))" % restored["instance"]),
                '{"outcome":"expired"}',
            )

            self._click(engine, "#end-session")
            self.assertEqual(
                engine.evaluate("JSON.stringify(window.__catalogReview.resolve(%r))" % remaining["instance"]),
                '{"outcome":"expired"}',
            )

    def test_real_browser_verifies_viewports_deep_link_keyboard_clipboard_and_teardown(self):
        with browser() as engine:
            engine.open(self.url + "?state=empty", viewport=(600, 900))
            empty = self._snapshot(engine)
            self.assertEqual(empty["viewport"], "compact")
            self.assertEqual(empty["display_state"], "empty")
            self.assertEqual(empty["rows"], [])
            self.assertEqual(empty["remote_requests"], 0)

            engine.open(self.url + "?state=unknown", viewport=(1280, 900))
            self.assertEqual(self._snapshot(engine)["display_state"], "unknown")

            link = self.module.deep_link(self.current, "catalog.add")
            engine.open(self.url + link[link.index("?") :], viewport=(1280, 900))
            self.assertEqual(self._snapshot(engine)["deep_link_target"], "catalog.add")

            self._click(engine, "#review-entry")
            self.assertEqual(self._snapshot(engine)["active_element"], "lock")
            engine.press("Escape")
            closed_by_key = self._snapshot(engine)
            self.assertEqual(closed_by_key["review_escapes"], 1)
            self.assertEqual(closed_by_key["active_element"], "review-entry")
            engine.evaluate("document.getElementById('business-input').focus()")
            engine.press("Escape")
            business_key = self._snapshot(engine)
            self.assertEqual(business_key["business_escapes"], 1)
            self.assertEqual(business_key["review_escapes"], 1)
            self._click(engine, "#review-entry")
            first = self._rect(engine, "[data-ref='catalog.item']")
            engine.move(first["x"], first["y"])
            self._click(engine, "#lock")
            selection = self._snapshot(engine)["selection"]
            self._click(engine, "#copy")
            engine.evaluate("new Promise(resolve => setTimeout(resolve, 100))")
            copied = self._snapshot(engine)
            self.assertEqual(copied["copy_outcome"], "copied")
            self.assertEqual(copied["selection"], selection)

            engine.evaluate("window.__catalogReview.setClipboardFailure(true)")
            self._click(engine, "#copy")
            engine.evaluate("new Promise(resolve => setTimeout(resolve, 100))")
            failed = self._snapshot(engine)
            self.assertEqual(failed["copy_outcome"], "copy-failed")
            self.assertEqual(failed["selection"], selection)
            self.assertEqual(failed["copy_attempts"], 2)

            self._click(engine, "#disable")
            stopped = self._snapshot(engine)
            self.assertEqual(stopped["resources"], 0)
            self.assertFalse(stopped["enabled"])
            self._click(engine, "#review-entry")
            self._click(engine, "#disable")
            stopped = self._snapshot(engine)
            self.assertEqual(stopped["resources"], 0)

            evidence = runtime_evidence(
                PROFILE,
                mapping_identity=self.current["ui_map"],
                build_identity=self.current["build"],
                rendered={"declared": 4, "undeclared": 0},
                runtime_adapter="catalog-html@2",
                environment="catalog-html-fixture@1",
                browser_version="catalog-browser-test",
                scope="full-runtime",
                runtime_gates={
                    "dynamic-session": "verified",
                    "interaction": "verified",
                    "teardown": "verified",
                    "coverage-matrix": "verified",
                },
            )
            checked = subprocess.run(
                [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
                input=json.dumps(evidence),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            report = json.loads(checked.stdout)
            self.assertEqual(report["status"], "implemented")
            self.assertTrue(report["complete"])

    def test_real_browser_unload_releases_review_listeners_and_session_resources(self):
        with browser() as engine:
            engine.open(self.url, viewport=(1280, 900))
            self._click(engine, "#review-entry")
            before = self._snapshot(engine)
            self.assertGreater(before["review_listeners"], 0)
            self.assertGreater(before["resources"], 0)

            engine.evaluate("window.dispatchEvent(new Event('beforeunload'))")
            after = self._snapshot(engine)

            self.assertTrue(after["host_unloaded"])
            self.assertFalse(after["enabled"])
            self.assertEqual(after["review_listeners"], 0)
            self.assertEqual(after["resources"], 0)
            self.assertEqual(after["session_handles"], 0)

    def test_real_browser_sees_the_alternate_attribute_and_no_canary(self):
        with browser() as engine:
            engine.open(self.url, viewport=(1280, 900))
            observed = json.loads(
                engine.evaluate(
                    "JSON.stringify({"
                    "refs: Array.from(document.querySelectorAll('[data-ref]'))"
                    ".map(node => node.getAttribute('data-ref')),"
                    "html: document.documentElement.outerHTML,"
                    "user_agent: navigator.userAgent})"
                )
            )

        self.assertEqual(
            observed["refs"],
            ["catalog.shell", "catalog.add", "catalog.items", "catalog.item", "catalog.item"],
        )
        self.assertNotIn("prompt-canary", observed["html"])
        self.assertNotIn("credential-canary", observed["html"])
        self.assertNotIn("data-ui-ref", observed["html"])

        evidence = runtime_evidence(
            PROFILE,
            mapping_identity=self.current["ui_map"],
            build_identity=self.current["build"],
            rendered={"declared": 4, "undeclared": 0},
            runtime_adapter="catalog-html@1",
            environment="catalog-html-fixture@1",
            browser_version=observed["user_agent"],
        )
        checked = subprocess.run(
            [sys.executable, str(RUNTIME_STATUS), str(PROFILE)],
            input=json.dumps(evidence),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"], "implemented")


if __name__ == "__main__":
    unittest.main()
