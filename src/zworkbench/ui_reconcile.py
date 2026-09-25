"""F13 executable-Reconcile command seam for the workbench host.

Product gate 1-2-8 (接 issue-1 PRD product gate) turns the safe-stop banner's
"reconcile" placeholder into a real trigger. This module is the *write* half
that mirrors ``ui_run`` / ``ui_approval``'s seams:

* ``owner_reconcile_source`` adapts an owner into the narrow command facade the
  host accepts. It exposes only ``reconcile`` -- re-run identity reconciliation
  for one run through ``owner.reconcile_identity`` -- and nothing else. The host
  never receives the owner; it receives this facade, so a request that may
  reconcile an identity still cannot widen into arbitrary owner access
  (ADR 0003's read-only host boundary is preserved; the write path is a
  deliberate, named exception, parallel to F10/F12).
* ``reconcile_script`` returns the progressive-enhancement handler wired to the
  safe-stop banner's reconcile button. It POSTs the run_id to the host's
  reconcile API and then asks the home live poller to refresh via a named event,
  so the banner's status surfaces without a full reload. It never builds HTML
  from JSON.

The host serves this only for /home, and only when a reconcile facade was
injected at startup -- a read-only host (the CLI ``ui-host`` command, which
opens no owner database) answers the reconcile API with 404, so the write
surface can never appear without an explicit, named wiring decision.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Mapping, Optional

#: Where the reconcile trigger posts. Served by the host only when a reconcile
#: command facade is wired; otherwise 404 (read-only host).
RECONCILE_API_ROUTE = "/api/reconcile"

#: Where the reconcile trigger handler script is served (progressive enhancement
#: for /home only; parallels the F7 live poller / F10 run-rail / F12 approval
#: scoped script exceptions).
RECONCILE_SCRIPT_ROUTE = "/static/reconcile.js"
RECONCILE_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(RECONCILE_SCRIPT_ROUTE)


class ReconcileFacade:
    """The only owner action the host may invoke: reconcile one run's identity."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        # Serialise owner writes: the owner is single-process in the first
        # slice and uses a shared connection across the host's request threads.
        self._lock = threading.Lock()

    def reconcile(self, run_id: str) -> Dict[str, Any]:
        """Re-run identity reconciliation for one run.

        ``owner.reconcile_identity`` is fail-closed: it re-checks the durable
        identity graph and records the decision durably. A safe-stopped run is
        terminal and is never resurrected (F13/1-2-5 Q2). The owner returns only
        outcome / violations / status -- no credentials -- so the response is
        safe to forward to the browser unchanged.
        """
        with self._lock:
            return self._owner.reconcile_identity(run_id)


def owner_reconcile_source(owner: Any) -> Callable[[str], Mapping[str, Any]]:
    """Adapt an owner into the narrow reconcile command facade the host expects.

    Parallel to ``owner_command_source`` / ``owner_approval_source``: the host is
    handed a facade callable, not the owner, so a request that may reconcile an
    identity still cannot widen into arbitrary owner access.
    """

    facade = ReconcileFacade(owner)

    def reconcile(run_id: str) -> Dict[str, Any]:
        return facade.reconcile(run_id)

    return reconcile


_RECONCILE_SCRIPT = """\
(() => {
  const BTN = document.querySelector('[data-reconcile-button]');
  if (!BTN) return;
  BTN.addEventListener('click', async () => {
    const runId = BTN.getAttribute('data-reconcile-run-id');
    if (!runId) return;
    BTN.setAttribute('aria-busy', 'true');
    BTN.disabled = true;
    const original = BTN.textContent;
    try {
      const res = await fetch('/api/reconcile', {
        method: 'POST',
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
        body: JSON.stringify({run_id: runId})
      });
      if (!res.ok) {
        BTN.textContent = 'reconcile 失败（' + res.status + '）';
        return;
      }
      const data = await res.json() || {};
      // The owner returns only outcome/violations/status -- never credentials.
      // We reflect the honest terminal state via textContent only (no HTML from
      // JSON) and let the live poller refresh the full banner on its next tick.
      const outcome = data.outcome || 'unknown';
      BTN.textContent = outcome === 'resolved' ? '已 reconcile（resolved）' : '仍越界（unknown）';
      window.dispatchEvent(new Event('workbench:reconcile-done'));
    } catch (e) {
      BTN.textContent = 'reconcile 失败（网络）';
    } finally {
      BTN.removeAttribute('aria-busy');
      if (BTN.textContent && BTN.textContent.indexOf('已') !== 0 && BTN.textContent.indexOf('仍') !== 0) {
        BTN.disabled = false;
        BTN.textContent = original;
      }
    }
  });
})();
"""


def reconcile_script() -> str:
    """Return the safe-stop reconcile handler (served at /static/reconcile.js)."""
    return _RECONCILE_SCRIPT
