"""1-6-3 — a refused clipboard write is visible, and is never retried.

``tests/test_ui_review.py`` settles what the state machine decides: a copy
needs a gesture, a rejection keeps the selection, the host error text is not
echoed, and nothing retries. None of that reaches a clipboard. The surface this
file covers is the other half: a real ``navigator.clipboard`` write in a secure
context, and what the page shows a reviewer when it is refused.

ADR 0004 records the limit of this evidence. A headless engine does not produce
a spontaneous user denial, so the rejection is injected by replacing
``writeText`` with one that rejects. The conclusion is therefore scoped: *when
a rejection occurs, the failure is visible and nothing retries*. It is not
evidence about how a real user's denial dialog behaves.

Injection also makes the counting possible. The replacement records every call,
so "never retried automatically" is measured as a call count rather than
inferred from the absence of a visible change.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_token import parse_token

VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}

#: Counts writes and keeps the payloads, so both "written once" and "written
#: what" are answerable. Installed before any interaction.
RECORDING_CLIPBOARD = """
(() => {
  window.__writes = [];
  navigator.clipboard.writeText = text => {
    window.__writes.push(text);
    return Promise.resolve();
  };
  return true;
})()
"""

#: The injected denial. ``NotAllowedError`` is the name a real permission
#: refusal carries, and the message is deliberately distinctive so the test can
#: assert it never reaches the page.
REFUSING_CLIPBOARD = """
(() => {
  window.__writes = [];
  navigator.clipboard.writeText = text => {
    window.__writes.push(text);
    const error = new Error('clipboard refused by policy');
    error.name = 'NotAllowedError';
    return Promise.reject(error);
  };
  return true;
})()
"""

STATUS = (
    "(() => {"
    "  const node = document.querySelector('[data-ui-panel-status]');"
    "  return JSON.stringify({"
    "    outcome: node.getAttribute('data-ui-panel-status'),"
    "    text: node.textContent,"
    "    live: node.getAttribute('aria-live'),"
    "  });"
    "})()"
)


@unittest.skipUnless(
    chrome_available(),
    "the verification-stage browser is absent; clipboard-failure-visible stays unknown",
)
class CopyingInARealEngineTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def _click(self, engine, action):
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

    def _copy_with(self, clipboard, *, select=True):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(clipboard)
            if select:
                self._click(engine, "select")
            self._click(engine, "copy")
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
            status = json.loads(engine.evaluate(STATUS))
        return writes, status

    def test_the_page_is_a_secure_context_so_the_clipboard_exists_at_all(self):
        """Without this the whole surface is untestable rather than passing."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            secure = engine.evaluate("window.isSecureContext")
            available = engine.evaluate("typeof navigator.clipboard.writeText")
        self.assertTrue(secure)
        self.assertEqual(available, "function")

    def test_a_successful_copy_writes_one_parseable_token(self):
        writes, status = self._copy_with(RECORDING_CLIPBOARD)
        self.assertEqual(len(writes), 1)
        self.assertEqual(parse_token(writes[0])["outcome"], "valid")
        self.assertEqual(status["outcome"], "copied")

    def test_the_written_token_names_the_viewport_that_was_rendered(self):
        """The token records what the reviewer saw, so it must not be guessed.

        The server cannot know the engine's viewport, so it serves one token
        per class; picking the wrong one would attach a compact observation to
        a wide screenshot.
        """
        writes, _ = self._copy_with(RECORDING_CLIPBOARD)
        self.assertEqual(json.loads(writes[0])["viewport"], "wide")

    def test_a_refused_write_is_reported_as_a_visible_failure(self):
        writes, status = self._copy_with(REFUSING_CLIPBOARD)
        self.assertEqual(len(writes), 1)
        self.assertEqual(status["outcome"], "copy-failed")
        self.assertTrue(status["text"].strip())

    def test_the_failure_is_announced_rather_than_only_shown(self):
        """A reviewer presses copy and looks away; silence reads as success."""
        _, status = self._copy_with(REFUSING_CLIPBOARD)
        self.assertEqual(status["live"], "polite")

    def test_a_refused_write_is_never_retried_automatically(self):
        writes, _ = self._copy_with(REFUSING_CLIPBOARD)
        self.assertEqual(len(writes), 1)

    def test_the_host_error_text_never_reaches_the_page(self):
        """It can carry detail the reviewer did not choose to surface."""
        _, status = self._copy_with(REFUSING_CLIPBOARD)
        self.assertNotIn("clipboard refused by policy", status["text"])
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(REFUSING_CLIPBOARD)
            self._click(engine, "select")
            self._click(engine, "copy")
            body = engine.evaluate("document.body.textContent")
        self.assertNotIn("NotAllowedError", body)

    def test_the_selection_survives_a_refusal_so_a_retry_stays_possible(self):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(REFUSING_CLIPBOARD)
            self._click(engine, "select")
            self._click(engine, "copy")
            locked = engine.evaluate(
                "!!document.querySelector('[data-ui-panel-locked=\\'true\\']')"
            )
        self.assertTrue(locked)

    def test_ctrl_c_inside_the_panel_copies_the_selection(self):
        """The keyboard plan prints `copy · Ctrl+C` on the button; the chord
        must actually do it."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(RECORDING_CLIPBOARD)
            self._click(engine, "select")
            engine.evaluate(
                "document.querySelector('[data-ui-panel-action]').focus()"
            )
            engine.press("CtrlC")
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
            status = json.loads(engine.evaluate(STATUS))
        self.assertEqual(len(writes), 1)
        self.assertEqual(parse_token(writes[0])["outcome"], "valid")
        self.assertEqual(status["outcome"], "copied")

    def test_ctrl_c_on_a_focused_business_element_copies_its_token(self):
        """Tab traversal is the keyboard way to point; what it points at must
        be copyable, or the traversal only ever reaches a dead end."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(RECORDING_CLIPBOARD)
            engine.evaluate(
                "document.querySelector("
                "  '[data-ui-ref=\"home.workspace-context\"]').focus()"
            )
            engine.press("CtrlC")
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
            status = json.loads(engine.evaluate(STATUS))
        self.assertEqual(len(writes), 1)
        token = parse_token(writes[0])
        self.assertEqual(token["outcome"], "valid")
        self.assertEqual(json.loads(writes[0])["ref"], "home.workspace-context")
        self.assertEqual(status["outcome"], "copied")

    def test_ctrl_c_focused_nowhere_declared_is_the_pages_own_copy(self):
        """On the body -- nowhere a reference names -- the chord is not ours."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(RECORDING_CLIPBOARD)
            engine.evaluate(
                "document.activeElement && document.activeElement.blur()"
            )
            engine.press("CtrlC")
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
        self.assertEqual(writes, [])

    def test_copying_without_a_selection_writes_nothing(self):
        writes, status = self._copy_with(RECORDING_CLIPBOARD, select=False)
        self.assertEqual(writes, [])
        self.assertEqual(status["outcome"], "no-target")

    def test_nothing_is_written_before_the_reviewer_asks(self):
        """Opening review mode must not touch the clipboard on its own."""
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=(1280, 900))
            engine.evaluate(RECORDING_CLIPBOARD)
            self._click(engine, "select")
            writes = json.loads(engine.evaluate("JSON.stringify(window.__writes)"))
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
