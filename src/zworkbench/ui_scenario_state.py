"""F11 scenario-state command seam for the workbench host.

Product gate 1-2-7 (接 issue-1 PRD product gate) turns the scenario-state
stepper's placeholder controls into real triggers. This module is the *write*
half that mirrors ``ui_run`` / ``ui_approval`` / ``ui_reconcile``'s seams:

* ``owner_scenario_source`` adapts an owner into the narrow command facade the
  host accepts. It exposes only two scenario-lifecycle verbs --
  ``request_approval`` (create a pending approval for the latest run) and
  ``request_stop`` (safe-stop the latest run) -- and nothing else. The host
  never receives the owner; it receives this facade, so a request that may
  drive the scenario state machine still cannot widen into arbitrary owner
  access (ADR 0003's read-only host boundary is preserved; the write path is a
  deliberate, named exception, parallel to F10/F12/F13).
* ``scenario_script`` returns the progressive-enhancement handler wired to the
  stepper's buttons. It POSTs the action to the host's scenario-state API and
  then asks the home live poller to refresh immediately (via a named event), so
  the stepper's state surfaces without a full reload. It never builds HTML from
  JSON.

The host serves these only for /home, and only when a command facade was
injected at startup -- a read-only host (the CLI ``ui-host`` command, which
opens no owner database) answers the scenario-state API with 404, so the write
surface can never appear without an explicit, named wiring decision.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Mapping, Optional

#: Where the scenario-state trigger posts. Served by the host only when a
#: scenario command facade is wired; otherwise 404 (read-only host).
SCENARIO_API_ROUTE = "/api/scenario-state"

#: Where the scenario-state trigger handler script is served (progressive
#: enhancement for /home only; parallels the F7 live poller / F10 run-rail /
#: F12 approval / F13 reconcile scoped script exceptions).
SCENARIO_SCRIPT_ROUTE = "/static/scenario-state.js"
SCENARIO_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(SCENARIO_SCRIPT_ROUTE)


class ScenarioStateFacade:
    """The only owner actions the host may invoke for scenario state."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        # Serialise owner writes: the owner is single-process in the first
        # slice and uses a shared connection across the host's request threads.
        self._lock = threading.Lock()

    def request_approval(
        self,
        run_id: str,
        operation_id: str,
        action: str,
        resource: str,
        idempotency_key: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Create a pending approval request for one run (no token in plaintext)."""
        with self._lock:
            row = self._owner.request_approval(
                run_id, operation_id, action, resource, idempotency_key, reason
            )
        # The owner returns only the durable approval envelope (no status
        # string); a successful create is all-or-nothing (otherwise it raised),
        # so surface ``pending`` for the UI.
        view = dict(row)
        view["status"] = view.get("status", "pending")
        return view

    def request_stop(self, run_id: str, reason: str) -> Dict[str, Any]:
        """Make a run terminal without attempting to repair unknown state."""
        with self._lock:
            row = self._owner.safe_stop_run(run_id, reason)
        return dict(row)

    def decide(self, action: str, **fields: Any) -> Dict[str, Any]:
        """Single dispatch point used by the host's POST handler.

        The host forwards the parsed payload (minus ``action``) as ``fields``;
        this method routes to the narrow owner verb. Unknown actions raise so
        the host can turn them into a 4xx rather than a 500.
        """
        if action == "request_approval":
            run_id = fields.get("run_id")
            operation_id = fields.get("operation_id")
            act = fields.get("op_action")
            resource = fields.get("resource")
            idempotency_key = fields.get("idempotency_key")
            reason = fields.get("reason", "")
            if not run_id or not operation_id or not act or not resource or not idempotency_key:
                raise ValueError(
                    "request_approval requires run_id, operation_id, op_action, resource, idempotency_key"
                )
            if not isinstance(reason, str) or not reason:
                reason = "scenario-state request"
            return self.request_approval(
                run_id, operation_id, act, resource, idempotency_key, reason
            )
        if action == "request_stop":
            run_id = fields.get("run_id")
            reason = fields.get("reason", "")
            if not run_id:
                raise ValueError("request_stop requires run_id")
            if not isinstance(reason, str) or not reason:
                reason = "scenario-state stop"
            return self.request_stop(run_id, reason)
        raise ValueError("unknown action: {0}".format(action))


def owner_scenario_source(owner: Any) -> Callable[..., Mapping[str, Any]]:
    """Adapt an owner into the narrow scenario command facade the host expects.

    Parallel to ``owner_command_source`` / ``owner_approval_source`` /
    ``owner_reconcile_source``: the host is handed a facade callable, not the
    owner, so a request that may drive the scenario state machine still cannot
    widen into arbitrary owner access.
    """

    facade = ScenarioStateFacade(owner)

    def decide(action: str, **fields: Any) -> Dict[str, Any]:
        return facade.decide(action, **fields)

    return decide


_SCENARIO_SCRIPT = """\
(() => {
  const refresh = () => window.dispatchEvent(new Event('workbench:scenario-changed'));
  const flash = (el, text) => { if (el) el.textContent = text; };
  // Request-approval button on a live scenario (planning state).
  document.querySelectorAll('[data-scenario-request-approval]').forEach((BTN) => {
    BTN.addEventListener('click', async () => {
      const runId = BTN.getAttribute('data-scenario-run-id');
      if (!runId) return;
      BTN.setAttribute('aria-busy', 'true');
      BTN.disabled = true;
      const original = BTN.textContent;
      try {
        const res = await fetch('/api/scenario-state', {
          method: 'POST',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({
            action: 'request_approval',
            run_id: runId,
            operation_id: runId,
            op_action: 'execute',
            resource: 'scenario',
            idempotency_key: runId,
            reason: 'scenario-state request'
          })
        });
        if (!res.ok) { flash(BTN, '请求审批失败（' + res.status + '）'); return; }
        flash(BTN, '已请求审批');
        refresh();
      } catch (e) {
        flash(BTN, '请求审批失败（网络）');
      } finally {
        BTN.removeAttribute('aria-busy');
        if (BTN.textContent && BTN.textContent.indexOf('已') !== 0) {
          BTN.disabled = false; BTN.textContent = original;
        }
      }
    });
  });
  // Request-stop button on a live scenario (planning / approval state).
  document.querySelectorAll('[data-scenario-request-stop]').forEach((BTN) => {
    BTN.addEventListener('click', async () => {
      const runId = BTN.getAttribute('data-scenario-run-id');
      if (!runId) return;
      BTN.setAttribute('aria-busy', 'true');
      BTN.disabled = true;
      const original = BTN.textContent;
      try {
        const res = await fetch('/api/scenario-state', {
          method: 'POST',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'request_stop', run_id: runId, reason: 'scenario-state stop'})
        });
        if (!res.ok) { flash(BTN, '请求停止失败（' + res.status + '）'); return; }
        flash(BTN, '已请求停止');
        refresh();
      } catch (e) {
        flash(BTN, '请求停止失败（网络）');
      } finally {
        BTN.removeAttribute('aria-busy');
        if (BTN.textContent && BTN.textContent.indexOf('已') !== 0) {
          BTN.disabled = false; BTN.textContent = original;
        }
      }
    });
  });
})();
"""


def scenario_script() -> str:
    """Return the scenario-state handler (served at /static/scenario-state.js)."""
    return _SCENARIO_SCRIPT
