"""Behaviour tests for review-mode residue at the host boundary.

The state machine's own start/stop contract is covered in
tests/test_ui_review.py: enabling twice registers one resource set, disabling
releases it, and disabling twice is a no-op. None of that is repeated here.

The risk this file addresses is different and only exists once the host renders
the layer: if the rendering path accumulated state between requests, repeated
review requests would stack overlays or panels, and each request would leave a
ReviewMode behind. Both are observable from outside, so neither needs a look
inside the handler.
"""

import gc
import re
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_host import serve_workbench
from zworkbench.ui_review import ReviewMode

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VIEW_MODEL = {"records": [{"title": "run-one"}, {"title": "run-two"}]}

REQUESTS = 5


def fetch(base, path="/home"):
    with DIRECT.open(base + path, timeout=5) as response:
        return response.read().decode("utf-8")


class RepeatedReviewRequestsTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_each_request_yields_exactly_one_overlay_and_one_panel(self):
        for attempt in range(REQUESTS):
            with self.subTest(attempt=attempt):
                document = fetch(self.host.base_url)
                self.assertEqual(document.count("data-ui-overlay="), 1)
                self.assertEqual(document.count('data-ui-panel="review"'), 1)

    def test_repeated_requests_return_the_same_document(self):
        """Nothing may accumulate across requests.

        The transient marks that tell two identical rows apart are regenerated
        per read by contract, so they are excluded rather than allowed to make
        this assertion vacuous.
        """
        def stable(text):
            return re.sub(r'data-ui-panel-entry="[^"]*"', "", text)

        first = stable(fetch(self.host.base_url))
        for attempt in range(1, REQUESTS):
            with self.subTest(attempt=attempt):
                self.assertEqual(stable(fetch(self.host.base_url)), first)


class NotRetainingReviewStateTests(unittest.TestCase):
    """A per-request ReviewMode must not outlive the response."""

    def setUp(self):
        self.host = serve_workbench(
            view_source=lambda route: VIEW_MODEL, review=True
        )
        self.addCleanup(self.host.close)

    def test_no_review_mode_survives_the_requests_that_created_it(self):
        gc.collect()
        before = sum(1 for obj in gc.get_objects() if isinstance(obj, ReviewMode))
        for _ in range(REQUESTS):
            fetch(self.host.base_url)
        gc.collect()
        after = sum(1 for obj in gc.get_objects() if isinstance(obj, ReviewMode))
        self.assertEqual(after, before)

    def test_a_review_host_still_serves_the_plain_document_elsewhere(self):
        """The stylesheet route must not acquire review state either.

        Static rules that target review-only elements are fine: they match
        nothing in a normal document. What must not happen is per-request
        state -- a token, a handle, a decision a ReviewMode made for one
        response -- leaking into a resource every response shares. So the
        assertion is byte stability across interleaved requests, and no token
        material in the bytes.
        """
        with DIRECT.open(self.host.base_url + "/static/workbench.css", timeout=5) as r:
            first = r.read()
        fetch(self.host.base_url)
        try:
            fetch(self.host.base_url + "?ui_ref=home.record-list&ui_map=" + "0" * 64)
        except urllib.error.URLError:
            pass  # the link is refused; what matters is the stylesheet after it
        with DIRECT.open(self.host.base_url + "/static/workbench.css", timeout=5) as r:
            again = r.read()
        self.assertEqual(again, first)
        self.assertNotIn(b"ui-ref/v1", again)


if __name__ == "__main__":
    unittest.main()
