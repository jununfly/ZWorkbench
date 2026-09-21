"""F7 live-values layer for the workbench home inspector.

Product gate 1-2-3 turns the run-facts inspector from a static, server-rendered
shell into a live surface. This module is the *read-only* half: a JSON payload
the host serves, plus the progressive-enhancement poller that consumes it.

The host owns nothing and this layer changes that not one bit. The endpoint only
re-projects the same owner-backed view model the page already renders -- no
business action, no write, no runtime invocation beyond the read-only
projection. The poller updates existing DOM text nodes only; it never builds
HTML from JSON, so there is no client-side injection surface.

This is a deliberate, scoped exception to the "a normal document carries no
script" convention in ui_host/ui_script. That note governed the review layer's
absence in normal mode. A live dashboard needs a client refresh and F7/1-2-3
explicitly authorises this one small script, served only for /home.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

#: Poll interval for the home live updater, in milliseconds.
LIVE_POLL_MS = 2000

#: Status token -> user-facing Chinese label. Mirrors the label table in
#: ui_home._status_chip so the poller can relabel the status chip without the
#: server re-rendering it. Kept in one place; if ui_home's table changes this
#: must change with it.
STATUS_LABELS: Mapping[str, str] = {
    "created": "已创建",
    "running": "进行中",
    "recovering": "恢复中",
    "completed": "已完成",
    "failed": "失败",
    "safe-stopped": "safe-stopped",
    "denied": "已拒绝",
    "unknown": "unknown",
    "ready": "可预检",
    "not-applicable": "不适用",
}


def live_facts_payload(view: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build the JSON payload the live endpoint returns for /home.

    Mirrors the inspector's read-only projection exactly: only scalars the
    page can render textually are surfaced for in-place updates. List- or
    dict-shaped fields (evidence_links, timeline, records) are summarised as a
    count so the poller never has to reconstruct markup from JSON -- keeping
    the script free of any HTML templating and therefore free of an injection
    surface. ``status_label`` lets the poller relabel the status chip from the
    same contract the server uses.
    """
    facts = view.get("run_facts") or {}
    if not isinstance(facts, Mapping):
        facts = {}
    payload: dict = {}
    for key, value in facts.items():
        if isinstance(value, (list, dict, Mapping)):
            continue
        payload[key] = value
    links = facts.get("evidence_links")
    payload["evidence_count"] = len(links) if isinstance(links, list) else 0
    token = payload.get("status")
    if isinstance(token, str):
        payload["status_label"] = STATUS_LABELS.get(token, token)
    return payload


_LIVE_SCRIPT = """\
(() => {
  const ROOT = document.querySelector('[data-ui-ref="home.run-facts"]');
  if (!ROOT) return;
  const POLL_MS = %d;
  const endpoint = '/api/home-facts';
  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }
  function applyStatus(facts) {
    const token = facts.status;
    if (typeof token !== 'string') return;
    const card = ROOT.querySelector('[data-live="status"]');
    if (!card) return;
    const chip = card.querySelector('.status-chip') || card;
    chip.setAttribute('data-status', token);
    const cls = (chip.getAttribute('class') || '').replace(/status-[A-Za-z0-9_-]+/, 'status-' + token);
    chip.setAttribute('class', cls);
    const b = chip.querySelector('b');
    if (b) setText(b, facts.status_label || token);
    const code = chip.querySelector('code');
    if (code) setText(code, token);
  }
  async function refresh() {
    try {
      const res = await fetch(endpoint, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!res.ok) return;
      const facts = await res.json() || {};
      ROOT.querySelectorAll('[data-live]').forEach(node => {
        const key = node.getAttribute('data-live');
        if (key === 'status') return;
        if (!(key in facts)) return;
        const val = facts[key];
        if (typeof val === 'object' && val !== null) return;
        if (key === 'evidence_count') { setText(node, val ? '（' + val + '）' : ''); return; }
        setText(node, val == null ? 'unknown' : String(val));
      });
      applyStatus(facts);
    } catch (e) { /* transient network error; next tick retries */ }
  }
  refresh();
  setInterval(refresh, POLL_MS);
})();
""" % LIVE_POLL_MS


def live_script() -> str:
    """Return the home live-values poller script (served at /static/live.js)."""
    return _LIVE_SCRIPT
