"""F10 executable-Run command seam for the workbench host.

Product gate 1-2-4 turns the run-rail's "executable Run" placeholder into a
real trigger. This module is the *write* half that mirrors ui_live's read half:

* ``owner_command_source`` adapts an owner into the narrow command facade the
  host accepts. It exposes only ``create_and_start_run`` -- create a durable
  run identity, then move it into execution -- and nothing else. The host never
  receives the owner; it receives this facade, so a request that may start a run
  still cannot widen into arbitrary owner access (ADR 0003's read-only host
  boundary is preserved; the write path is a deliberate, named exception).
* ``run_trigger_script`` returns the progressive-enhancement handler wired to
  the run-rail button. It POSTs to the host's run API and then asks the home
  live poller to refresh immediately (via a named event), so the new run shows
  up without a full reload. It never builds HTML from JSON.

The host serves this only for /home, and only when a command facade was
injected at startup -- a read-only host (the CLI ``ui-host`` command, which
opens no owner database) answers the run API with 404, so the write surface can
never appear without an explicit, named wiring decision.
"""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Dict, Mapping, Optional

#: Where the run trigger posts. Served by the host only when a command facade
#: is wired; otherwise 404 (read-only host).
RUN_API_ROUTE = "/api/runs"

#: Where the run trigger handler script is served (progressive enhancement for
#: /home only; parallels the F7 live poller's scoped script exception).
RUN_SCRIPT_ROUTE = "/static/run.js"
RUN_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(RUN_SCRIPT_ROUTE)

#: Default task type the run-rail button sends. The UI button is a single
#: "create + start a run" action; what a run *means* is decided by the control
#: plane that wired the command facade, not by this script.
DEFAULT_TASK_TYPE = "interactive_run"


class CommandFacade:
    """The only owner action the host may invoke: create + start a run."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        # Serialise owner writes: the owner is single-process in the first
        # slice and uses a shared connection across the host's request threads.
        self._lock = threading.Lock()

    def create_and_start_run(
        self,
        task_type: str,
        input_value: Any,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a durable run and move it straight into execution.

        The run_id is minted here so the UI button need not invent identity.
        Returns a redacted view of the started run; the raw input is not
        echoed back, mirroring the read layer's "never surface input" rule.
        """
        run_id = "run-" + uuid.uuid4().hex[:12]
        with self._lock:
            self._owner.create_run(run_id, task_type, input_value, metadata or {})
            started = self._owner.start_run(run_id)
        return {
            "run_id": started.get("run_id"),
            "status": started.get("status"),
            "task_type": started.get("task_type"),
            "created_at": started.get("created_at"),
        }


def owner_command_source(owner: Any):
    """Adapt an owner into the narrow command facade the host expects.

    Parallel to ``owner_view_source``: the host is handed a facade callable, not
    the owner, so a request that may start a run still cannot widen into
    arbitrary owner access.
    """

    facade = CommandFacade(owner)

    def create_and_start_run(
        task_type: str,
        input_value: Any,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        return facade.create_and_start_run(task_type, input_value, metadata)

    return create_and_start_run


_RUN_SCRIPT = """\
(() => {
  const BTN = document.querySelector('[data-run-trigger]');
  if (!BTN) return;
  BTN.addEventListener('click', async () => {
    BTN.setAttribute('aria-busy', 'true');
    BTN.disabled = true;
    const original = BTN.textContent;
    try {
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
        body: JSON.stringify({
          task_type: BTN.getAttribute('data-task-type') || 'interactive_run',
          input_value: {prompt: 'manual trigger from workbench UI', origin: 'run-rail'},
          metadata: {source: 'workbench-ui', triggered_by: 'run-rail'}
        })
      });
      if (!res.ok) {
        BTN.textContent = '创建失败（' + res.status + '）';
        return;
      }
      const data = await res.json() || {};
      BTN.textContent = '已创建：' + (data.run_id || 'unknown');
      // Ask the home live poller to refresh now; the new run surfaces within
      // the next tick rather than on the next 2s interval. No HTML is built
      // from the JSON response -- the poller owns all DOM updates.
      window.dispatchEvent(new Event('workbench:run-created'));
    } catch (e) {
      BTN.textContent = '创建失败（网络）';
    } finally {
      BTN.removeAttribute('aria-busy');
      if (BTN.textContent && BTN.textContent.indexOf('已创建') !== 0) {
        BTN.disabled = false;
        BTN.textContent = original;
      }
    }
  });
})();
"""


def run_trigger_script() -> str:
    """Return the run-rail trigger handler (served at /static/run.js)."""
    return _RUN_SCRIPT
