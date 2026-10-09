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
* ``composer_script`` (F6/1-2-1) returns the handler wired to the A-session
  input composer. It POSTs the typed prompt to the same run API under
  ``task_type=composer_message`` and refreshes via the same named event; it is
  served only for a host wired with a command facade, so a read-only host keeps
  the composer form disabled.

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

#: F6/1-2-1 — task type the input composer sends. The composer is the A-session
#: input box; each send creates + starts a run whose prompt is the typed text.
#: Same narrow facade as the run-rail button, distinct task type so the control
#: plane can tell a typed request apart from a manual run-rail trigger.
COMPOSER_TASK_TYPE = "composer_message"

#: Where the composer's progressive-enhancement handler is served (for /home
#: only, paralleling the run-rail script; it does nothing on a host without the
#: composer form).
COMPOSER_SCRIPT_ROUTE = "/static/composer.js"
COMPOSER_SCRIPT_TAG = '<script src="{0}" defer></script>'.format(COMPOSER_SCRIPT_ROUTE)


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


def owner_command_source_with_executor(owner: Any, run_config: Any, *, timeout: float = 45.0):
    """Command facade that also drives the started run to completion.

    This is the dogfood-UI counterpart to the one-shot ``run`` command: after
    ``create_and_start_run`` records the run (status ``running``), a daemon
    thread runs it through :class:`LocalReadOnlyRunOrchestrator` using the
    supplied ``run_config``. The started run is executed with ``run_claim=
    "assume"`` so the adapter does not re-create the identity the facade already
    minted.

    The gate stays fail-closed: ``run_config.real_provider_gate`` defaults to
    ``False`` and the baseline (loopback / fake) path never silently reaches a
    real Provider. A run whose preflight is denied, or whose execution raises
    before the orchestrator can close it, is moved out of ``running`` so it
    never dangles in the owner.
    """

    base = owner_command_source(owner)

    def create_and_start_run(
        task_type: str,
        input_value: Any,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = base(task_type, input_value, metadata)
        run_id = result.get("run_id")
        prompt = _prompt_from_input(input_value)
        thread = threading.Thread(
            target=_execute_run,
            args=(run_config, run_id, prompt, timeout),
            daemon=True,
            name="ui-run-executor-{0}".format(run_id),
        )
        thread.start()
        return result

    return create_and_start_run


def _prompt_from_input(input_value: Any) -> str:
    """Pull the user prompt out of the run input the UI sends.

    Both the run-rail trigger and the composer send ``{"prompt": "...", "origin":
    "..."}``; the composer's typed text is what the executor should run.
    """

    if isinstance(input_value, Mapping) and isinstance(input_value.get("prompt"), str):
        return input_value["prompt"]
    return ""


def _execute_run(run_config: Any, run_id: Optional[str], prompt: str, timeout: float) -> None:
    """Background executor: drive one already-started run to a terminal state."""

    if not run_id:
        return
    from .composition import CompositionOwner
    from .local_run import LocalReadOnlyRunOrchestrator

    try:
        result = LocalReadOnlyRunOrchestrator(run_config).run(
            run_id, prompt, timeout=timeout, run_claim="assume"
        )
    except Exception:
        # The orchestrator usually closes the run itself on its failure path
        # (via _ensure_run_closed), but guarantee a terminal state so a started
        # run never dangles in `running` if an unexpected error escapes it.
        _fail_run_if_running(run_config.database, run_id, {"type": "UiExecutorError"})
        return
    if result.status == "denied":
        # Preflight denied before the orchestrator opened the owner, so the run
        # is still `running` (created by the facade). Move it to a terminal
        # state and record the denial reason for auditability.
        _fail_run_if_running(
            run_config.database,
            run_id,
            {
                "type": "PreflightDenied",
                "violations": [violation.to_dict() for violation in result.preflight.violations],
            },
        )


def _fail_run_if_running(database: Any, run_id: str, error: Mapping[str, Any]) -> None:
    """Close a still-`running` run as failed, ignoring any owner error.

    Used to guarantee a started run reaches a terminal state even when preflight
    or an executor-internal error prevents the orchestrator from doing so.
    """

    try:
        from .composition import CompositionOwner

        with CompositionOwner(database) as owner:
            if owner.get_run(run_id).get("status") == "running":
                owner.fail_run(run_id, dict(error))
    except Exception:
        # The authoritative result is best-effort; an owner write failure here
        # must not raise out of the background thread.
        pass


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


# F6/1-2-1 — the composer handler. It is the *read* half's companion for the
# conversation input box: it reads the typed prompt, POSTs it to the same
# narrow run API the run-rail button uses (task_type=composer_message), and
# asks the home live poller to refresh via the same named event. Like the
# run-rail handler it never builds HTML from the JSON response -- the poller
# owns all DOM updates -- and it never echoes the typed text back into the
# page. A read-only host never serves this script, so the form stays disabled.
_COMPOSER_SCRIPT = """\
(() => {
  const FORM = document.querySelector('[data-composer]');
  if (!FORM) return;
  const INPUT = FORM.querySelector('[data-composer-input]');
  const BTN = FORM.querySelector('[data-composer-send]');
  if (!INPUT || !BTN) return;
  if (BTN.getAttribute('aria-disabled') === 'true' || BTN.disabled) return;
  FORM.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = (INPUT.value || '').trim();
    if (!prompt) {
      INPUT.focus();
      return;
    }
    BTN.setAttribute('aria-busy', 'true');
    BTN.disabled = true;
    const original = BTN.textContent;
    try {
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
        body: JSON.stringify({
          task_type: 'composer_message',
          input_value: {prompt: prompt, origin: 'composer'},
          metadata: {source: 'workbench-ui', triggered_by: 'composer'}
        })
      });
      if (!res.ok) {
        BTN.textContent = '发送失败（' + res.status + '）';
        return;
      }
      const data = await res.json() || {};
      INPUT.value = '';
      BTN.textContent = '已发送：' + (data.run_id || 'unknown');
      // Same named event the run-rail handler dispatches: the home live poller
      // refreshes within the next tick rather than the next 2s interval.
      window.dispatchEvent(new Event('workbench:run-created'));
    } catch (err) {
      BTN.textContent = '发送失败（网络）';
    } finally {
      BTN.removeAttribute('aria-busy');
      if (BTN.textContent && BTN.textContent.indexOf('已发送') !== 0) {
        BTN.disabled = false;
        BTN.textContent = original;
      }
    }
  });
})();
"""


def composer_script() -> str:
    """Return the composer trigger handler (served at /static/composer.js)."""
    return _COMPOSER_SCRIPT
