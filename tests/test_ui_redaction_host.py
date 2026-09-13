"""1-7-2 — pollute the owner, then look for leaks where a reviewer's tools do.

``tests/test_ui_view_model.py`` proves the facade redacts what it projects.
That is one layer. This file assumes the facade could fail and asks a different
question: after a run carrying every forbidden shape is served through the real
host, does anything sensitive survive in the places a leak actually escapes
from — the document, the URL, browser-persisted storage, or the token a
reviewer copies and pastes into a chat?

Storage matters most and is the one only an engine can answer. A page that
wrote a run identifier into ``localStorage`` would leave it on disk after the
host exits, outliving the read-only session entirely.

The pollution is synthetic throughout: these are fabricated strings shaped like
credentials, never real ones.
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
from zworkbench.ui_token import build_deep_link, parse_token
from zworkbench.ui_view_model import owner_view_source

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: Synthetic values shaped like the things that must never escape. Each is
#: distinctive enough that finding it anywhere is unambiguous.
SECRETS = {
    "api-key": "sk-canary000000000000000000000000",
    "bearer": "eyJcanary0000.eyJcanary0000.sigcanary0000",
    "github-token": "ghp_canary0000000000000000000000000",
    "aws-key": "AKIACANARY0000000000",
}

#: Prose a user might type, containing things that are not credential-shaped
#: but still must not reach a token: a prompt, a path, a full run identifier.
PROMPT = "请读取 /Users/canary/secret-project/notes.md 并总结"


def polluted_owner(directory):
    """An owner holding runs whose free text is contaminated.

    The contamination goes into *values*, never into a field named like a
    credential: the owner rejects those on write, and routing around that
    defence would be testing a path the product does not allow. What it cannot
    reject is a secret pasted into prose, which is the case this file exists
    for.
    """
    owner = CompositionOwner(Path(directory) / "owner.sqlite3")
    owner.create_run(
        "run-canary-0001",
        "local_read_only_run",
        {"prompt": PROMPT + " " + SECRETS["api-key"]},
        metadata={"note": SECRETS["bearer"], "comment": SECRETS["github-token"]},
    )
    owner.create_run(
        "run-" + SECRETS["aws-key"],
        "local_read_only_run",
        {"prompt": PROMPT},
    )
    return owner


class ThePollutedPageTests(unittest.TestCase):
    """The document itself, over HTTP, before any engine is involved."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = polluted_owner(directory.name)
        self.addCleanup(self.owner.close)
        self.host = serve_workbench(
            view_source=owner_view_source(self.owner), review=True
        )
        self.addCleanup(self.host.close)

    def _fetch(self, path):
        with DIRECT.open(self.host.base_url + path, timeout=5) as response:
            return response.read().decode("utf-8")

    def test_the_owner_really_holds_the_contamination(self):
        """Otherwise every assertion below passes for the wrong reason.

        An owner that rejected this input would make a clean page prove
        nothing, which is exactly how a redaction test rots into a tautology.
        """
        stored = json.dumps(self.owner.snapshot(), ensure_ascii=False)
        for name, secret in SECRETS.items():
            with self.subTest(secret=name):
                self.assertIn(secret, stored)

    def test_no_served_view_carries_a_credential(self):
        for route in ("/home", "/task-detail", "/record-view"):
            body = self._fetch(route)
            for name, secret in SECRETS.items():
                with self.subTest(route=route, secret=name):
                    self.assertNotIn(secret, body)

    def test_no_served_view_carries_the_recorded_prompt_or_a_local_path(self):
        """Neither is a credential; neither has any reason to be on the page."""
        for route in ("/home", "/task-detail", "/record-view"):
            body = self._fetch(route)
            with self.subTest(route=route):
                self.assertNotIn(PROMPT, body)
                self.assertNotIn("/Users/canary", body)

    def test_the_review_panel_tokens_carry_nothing_from_the_owner(self):
        """The panel embeds a token per entry; each is parsed, not scanned.

        Scanning the markup for secrets would pass on a token that carried an
        extra field nobody thought to search for. Parsing asserts the whitelist
        instead: the token is exactly the fields ui_token allows.
        """
        body = self._fetch("/home")
        tokens = [
            part.split('"')[0]
            for part in body.split('data-ui-panel-token-wide="')[1:]
        ]
        self.assertTrue(tokens)
        for raw in tokens:
            token = raw.replace("&quot;", '"').replace("&amp;", "&")
            with self.subTest(token=token[:40]):
                parsed = parse_token(token)
                self.assertEqual(parsed["outcome"], "valid")
                self.assertNotIn("instance", parsed.get("token", parsed))


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; the storage surface stays unknown",
)
class ThePollutedPageInARealEngineTests(unittest.TestCase):
    """Where a leak would actually outlive the session."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.owner = polluted_owner(directory.name)
        self.addCleanup(self.owner.close)
        self.host = serve_workbench(
            view_source=owner_view_source(self.owner), review=True
        )
        self.addCleanup(self.host.close)

    def _visit(self, path="/home"):
        with browser() as engine:
            engine.open(self.host.base_url + path, viewport=(1280, 900))
            return json.loads(engine.evaluate("""
              JSON.stringify({
                dom: document.documentElement.outerHTML,
                text: document.body.innerText,
                url: location.href,
                cookie: document.cookie,
                local: JSON.stringify(Object.entries(localStorage)),
                session: JSON.stringify(Object.entries(sessionStorage)),
              })
            """))

    def test_the_page_persists_nothing_in_the_browser_at_all(self):
        """Not "nothing sensitive" -- nothing.

        A read-only viewer has no reason to write storage, so an empty store is
        a contract that can be stated exactly. "No secret in storage" would
        pass while the page quietly accumulated state.
        """
        observed = self._visit()
        self.assertEqual(json.loads(observed["local"]), [])
        self.assertEqual(json.loads(observed["session"]), [])
        self.assertEqual(observed["cookie"], "")

    def test_no_credential_reaches_the_rendered_dom_or_its_visible_text(self):
        observed = self._visit()
        for name, secret in SECRETS.items():
            with self.subTest(secret=name):
                self.assertNotIn(secret, observed["dom"])
                self.assertNotIn(secret, observed["text"])

    def test_the_url_carries_nothing_sensitive(self):
        """URLs are pasted, logged and shared more casually than anything else."""
        observed = self._visit()
        for name, secret in SECRETS.items():
            with self.subTest(secret=name):
                self.assertNotIn(secret, observed["url"])
        self.assertNotIn("/Users/canary", observed["url"])

    def test_a_deep_link_to_a_polluted_row_stays_clean(self):
        """The one URL that carries product data is the deep link."""
        link = build_deep_link(home_manifest(), "home.record-list.item")
        observed = self._visit(link)
        for name, secret in SECRETS.items():
            with self.subTest(secret=name):
                self.assertNotIn(secret, observed["url"])
                self.assertNotIn(secret, observed["dom"])

    def test_the_token_a_reviewer_copies_leaks_nothing(self):
        """The end of the path: what actually lands in someone's clipboard."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate("""
              (() => {
                window.__writes = [];
                navigator.clipboard.writeText = text => {
                  window.__writes.push(text);
                  return Promise.resolve();
                };
                return true;
              })()
            """)
            for action in ("select", "copy"):
                where = json.loads(engine.evaluate(
                    "(() => {"
                    "  const node = document.querySelector("
                    "    '[data-ui-panel-action=\\'" + action + "\\']');"
                    "  const box = node.getBoundingClientRect();"
                    "  return JSON.stringify({"
                    "    x: box.left + box.width / 2, y: box.top + box.height / 2});"
                    "})()"
                ))
                engine.click(where["x"], where["y"])
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
        self.assertEqual(len(writes), 1)
        payload = writes[0]
        for name, secret in SECRETS.items():
            with self.subTest(secret=name):
                self.assertNotIn(secret, payload)
        self.assertNotIn(PROMPT, payload)
        self.assertNotIn("/Users/", payload)
        self.assertNotIn("run-canary-0001", payload)
        self.assertEqual(parse_token(payload)["outcome"], "valid")


if __name__ == "__main__":
    unittest.main()
