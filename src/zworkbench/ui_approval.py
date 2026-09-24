"""F12 approval-execution command seam for the workbench host.

Product gate 1-2-2 turns the approval console's Approve/Deny placeholders and
the effect-receipt affordance into real human decisions. This module is the
*write* half that mirrors ``ui_run``'s run-rail seam:

* ``owner_approval_source`` adapts an owner into the narrow command facade the
  host accepts. It exposes only the human-decidable verbs of the
  Approval/Effect seam -- ``approve``, ``deny`` and ``record_effect`` -- and
  nothing else. The host never receives the owner; it receives this facade, so
  a request that may decide an approval still cannot widen into arbitrary owner
  access (ADR 0003's read-only host boundary is preserved; the write path is a
  deliberate, named exception, parallel to F10/1-2-4).
* ``approval_script`` returns the progressive-enhancement handler wired to the
  console's buttons. It POSTs the decision to the host's approval/effect APIs
  and then asks the home live poller to refresh immediately (via a named
  event), so the decided approval/effect surfaces without a full reload. It
  never builds HTML from JSON.

The host serves these only for /home, and only when a command facade was
injected at startup -- a read-only host (the CLI ``ui-host`` command, which
opens no owner database) answers the approval/effect APIs with 404, so the
write surface can never appear without an explicit, named wiring decision.

Security note: the facade returns a *redacted* view of each decision. The
owner's ``approve`` persists a token hash but never returns the plaintext
token; the UI only needs to record the human decision, and the worker -- via
the control plane -- later retrieves and consumes the token. No token hash is
echoed back to the browser.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Mapping, Optional

#: Where the approval decision handler posts. Served by the host only when an
#: approval command facade is wired; otherwise 404 (read-only host).
APPROVAL_API_ROUTE = "/api/approvals"

#: Where the effect-receipt handler posts (the downstream of an approved,
#: applied effect). Same guarded visibility as the approval route.
EFFECT_API_ROUTE = "/api/effects"

#: Where the console's progressive-enhancement handler is served (for /home
#: only; parallels the F10 run-rail script; it does nothing on a host without
#: the approval console wired).
APPROVAL_SCRIPT_ROUTE = "/static/approvals.js"
APPROVAL_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(APPROVAL_SCRIPT_ROUTE)


def _redact_approval(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a token-free view of an approval decision.

    The owner stores ``token_hash`` but never the plaintext; we keep it out of
    the response entirely so the UI cannot leak a credential it does not need.
    """
    return {
        "approval_id": row.get("approval_id"),
        "status": row.get("status"),
        "operation_id": row.get("operation_id"),
        "action": row.get("action"),
        "resource": row.get("resource"),
        "decision_reason": row.get("decision_reason"),
    }


def _redact_effect(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a receipt view of a completed effect, never the stored plaintext."""
    return {
        "effect_id": row.get("effect_id"),
        "status": row.get("status"),
        "operation_id": row.get("operation_id"),
        "action": row.get("action"),
        "resource": row.get("resource"),
        "physical_effect_count": row.get("physical_effect_count"),
    }


class ApprovalCommandFacade:
    """The only owner actions the host may invoke: decide + record receipt."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        # Serialise owner writes: the owner is single-process in the first
        # slice and uses a shared connection across the host's request threads.
        self._lock = threading.Lock()

    def approve(self, approval_id: str) -> Dict[str, Any]:
        """Approve a pending approval; returns a token-free redacted view."""
        with self._lock:
            row = self._owner.approve(approval_id)
        view = _redact_approval(row)
        # The owner's ``approve`` returns only the token envelope (no status),
        # but a successful approve is all-or-nothing: on success the row is
        # ``approved`` (otherwise it raised). Surface that for the UI.
        view["status"] = "approved"
        return view

    def deny(self, approval_id: str, reason: str = "") -> Dict[str, Any]:
        """Deny a pending approval; a denied request can never be approved later."""
        with self._lock:
            row = self._owner.deny_approval(approval_id, reason or "")
        return _redact_approval(row)

    def record_effect(
        self, effect_id: str, external_receipt: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        """Commit one physical effect and its result exactly once."""
        with self._lock:
            row = self._owner.complete_effect(effect_id, external_receipt or {})
        return _redact_effect(row)

    def decide(self, action: str, **fields: Any) -> Dict[str, Any]:
        """Single dispatch point used by the host's POST handlers.

        The host forwards the parsed payload (minus ``action``) as ``fields``;
        this method routes to the narrow owner verb. Unknown actions raise so
        the host can turn them into a 4xx rather than a 500.
        """
        if action == "approve":
            approval_id = fields.get("approval_id")
            if not approval_id:
                raise ValueError("approve requires approval_id")
            return self.approve(approval_id)
        if action == "deny":
            approval_id = fields.get("approval_id")
            if not approval_id:
                raise ValueError("deny requires approval_id")
            return self.deny(approval_id, fields.get("reason", ""))
        if action == "complete_effect":
            effect_id = fields.get("effect_id")
            if not effect_id:
                raise ValueError("complete_effect requires effect_id")
            return self.record_effect(effect_id, fields.get("external_receipt"))
        raise ValueError("unknown action: {0}".format(action))


def owner_approval_source(owner: Any):
    """Adapt an owner into the narrow approval command facade the host expects.

    Parallel to ``owner_command_source`` / ``owner_view_source``: the host is
    handed a facade callable, not the owner, so a request that may decide an
    approval still cannot widen into arbitrary owner access.
    """

    facade = ApprovalCommandFacade(owner)

    def decide(action: str, **fields: Any) -> Dict[str, Any]:
        return facade.decide(action, **fields)

    return decide


_APPROVAL_SCRIPT = """\
(() => {
  const dispatchRefresh = () => {
    window.dispatchEvent(new Event('workbench:decision-made'));
  };
  const flash = (el, text) => {
    if (!el) return;
    el.textContent = text;
  };
  // Approve / Deny buttons on a pending approval row.
  document.querySelectorAll('[data-approval-approve],[data-approval-deny]').forEach((BTN) => {
    BTN.addEventListener('click', async () => {
      const approvalId = BTN.getAttribute('data-approval-id');
      const action = BTN.getAttribute('data-approval-approve') !== null ? 'approve' : 'deny';
      if (!approvalId) return;
      BTN.setAttribute('aria-busy', 'true');
      BTN.disabled = true;
      const original = BTN.textContent;
      try {
        const res = await fetch('/api/approvals', {
          method: 'POST',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({
            action: action,
            approval_id: approvalId,
            reason: action === 'deny'
              ? (document.querySelector('[data-approval-reason="' + approvalId + '"]') || {}).value || ''
              : ''
          })
        });
        if (!res.ok) {
          flash(BTN, '失败（' + res.status + '）');
          return;
        }
        const data = await res.json() || {};
        flash(BTN, action === 'approve' ? '已批准' : '已拒绝');
        dispatchRefresh();
      } catch (e) {
        flash(BTN, '失败（网络）');
      } finally {
        BTN.removeAttribute('aria-busy');
        if (BTN.textContent && BTN.textContent.indexOf('已') !== 0) {
          BTN.disabled = false;
          BTN.textContent = original;
        }
      }
    });
  });
  // Record-receipt buttons on a claimed effect row.
  document.querySelectorAll('[data-effect-receipt]').forEach((BTN) => {
    BTN.addEventListener('click', async () => {
      const effectId = BTN.getAttribute('data-effect-id');
      if (!effectId) return;
      BTN.setAttribute('aria-busy', 'true');
      BTN.disabled = true;
      const original = BTN.textContent;
      try {
        const res = await fetch('/api/effects', {
          method: 'POST',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
          body: JSON.stringify({
            effect_id: effectId,
            external_receipt: {recorded_by: 'workbench-ui', at: 'client'}
          })
        });
        if (!res.ok) {
          flash(BTN, '失败（' + res.status + '）');
          return;
        }
        flash(BTN, '已记录回执');
        dispatchRefresh();
      } catch (err) {
        flash(BTN, '失败（网络）');
      } finally {
        BTN.removeAttribute('aria-busy');
        if (BTN.textContent && BTN.textContent.indexOf('已') !== 0) {
          BTN.disabled = false;
          BTN.textContent = original;
        }
      }
    });
  });
})();
"""


def approval_script() -> str:
    """Return the approval-console handler (served at /static/approvals.js)."""
    return _APPROVAL_SCRIPT
