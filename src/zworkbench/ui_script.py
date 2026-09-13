"""The review-mode behaviour layer, served only when review mode is on.

ADR 0005 records why this exists. Two acceptance surfaces — a clipboard write
being refused and the refusal being *visible*, and focus landing somewhere
predictable after the panel closes — happen inside the page. A server-rendered
document can express neither, so without this layer both would stay ``unknown``
permanently: not unverified for now, but unverifiable by construction.

What this layer is allowed to be is deliberately narrow. It mirrors decisions
:class:`~zworkbench.ui_review.ReviewMode` has already made and adds none of its
own: no request, no storage, no telemetry, no business activation, and no token
minted here. Tokens arrive pre-built from the server, one per viewport, because
minting one in the page would move the field whitelist out of
:mod:`zworkbench.ui_token` and into a string no test of the token contract
reads.

The script is inert outside review mode: it is not linked at all in normal
mode, and it returns immediately if it cannot find a review panel.
"""

from __future__ import annotations


#: Served as a separate resource rather than inlined, so the document carries
#: no executable text and a reader can diff the behaviour layer on its own.
_SCRIPT = """\
(() => {
  const panel = document.querySelector('[data-ui-panel="review"]');
  if (!panel) return;

  const status = panel.querySelector('[data-ui-panel-status]');
  const entries = () => Array.from(panel.querySelectorAll('[data-ui-panel-entry]'));
  const entry = () => panel.querySelector('[data-ui-panel-locked="true"]');
  const overlay = document.querySelector('[data-ui-overlay]');

  // Semantic names come from the server-rendered manifest map on the panel
  // -- the state machine's own decisions. The script displays them; it never
  // invents one, and an unmapped ref falls back to naming the ref itself.
  const names = JSON.parse(panel.getAttribute('data-ui-panel-names') || '{}');
  const semanticOf = ref => names[ref] || null;
  const tokens = JSON.parse(panel.getAttribute('data-ui-panel-tokens') || '{}');

  // Tab must reach every declared element, not only natively focusable
  // controls: a keyboard reviewer has no hover, so traversal is their only
  // way to point at a static unit. The tabindex is added here, in the page
  // layer, because the served business markup must stay byte-identical to
  // normal mode -- and in normal mode this script does not exist at all.
  document.querySelectorAll('[data-ui-ref]').forEach(node => {
    if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '0');
    // Style hook, separate from the reference: the style layer may not key
    // off data-ui-ref, so the ring targets this attribute instead.
    node.setAttribute('data-ui-review-focusable', '');
  });

  // Preview: a dashed box with the element's Chinese semantic name, drawn
  // inside the overlay so it can never intercept a click. Hover and focus
  // are both preview gestures in the state machine's contract -- pointing is
  // not selecting -- so both arrive at the same display.
  let previewBox = null;
  const clearPreview = () => {
    if (previewBox) { previewBox.remove(); previewBox = null; }
  };
  const showPreview = node => {
    if (!overlay) return;
    const ref = node.getAttribute('data-ui-ref');
    const rect = node.getBoundingClientRect();
    previewBox = document.createElement('div');
    previewBox.setAttribute('data-ui-preview-box', '');
    previewBox.style.left = rect.left + 'px';
    previewBox.style.top = rect.top + 'px';
    previewBox.style.width = rect.width + 'px';
    previewBox.style.height = rect.height + 'px';
    const badge = document.createElement('span');
    badge.setAttribute('data-ui-preview-badge', '');
    badge.textContent = (semanticOf(ref) || ref);
    // The badge floats above the box; a box that touches the viewport top
    // (the page root always does) would push it off-screen and the preview
    // would read as "nothing happened". Clamp it inside the box instead.
    if (rect.top < 28) badge.style.top = '2px';
    previewBox.appendChild(badge);
    overlay.appendChild(previewBox);
  };
  document.addEventListener('mouseover', event => {
    clearPreview();
    if (panel.contains(event.target)) return;
    const node = event.target.closest && event.target.closest('[data-ui-ref]');
    if (node) showPreview(node);
  });
  document.addEventListener('mouseout', () => clearPreview());

  // Locking in the panel rings the corresponding business element, so "the
  // element under discussion" is visible on the page, not only in the panel.
  // Repeated structural items share one ref; the entry's position among the
  // panel's same-ref entries matches document order, because the server
  // mounts entries in render order.
  const markLockedTarget = () => {
    document.querySelectorAll('[data-ui-locked-target]')
      .forEach(node => node.removeAttribute('data-ui-locked-target'));
    const current = entry();
    if (!current) return;
    const ref = current.getAttribute('data-ui-panel-entry');
    const sameRef = entries().filter(
      node => node.getAttribute('data-ui-panel-entry') === ref);
    const position = sameRef.indexOf(current);
    const candidates = document.querySelectorAll('[data-ui-ref="' + ref + '"]');
    const target = candidates[position] || candidates[0];
    if (target) target.setAttribute('data-ui-locked-target', 'true');
  };

  // The element focus should return to when the panel closes. Only focus
  // landing outside the panel is remembered: otherwise moving between panel
  // controls would overwrite the target the reviewer came from.
  //
  // The body is not a restore target. It is what activeElement reports when
  // nothing is focused -- which is the state a reviewer who opened the panel
  // with the mouse is in, because on macOS clicking a button does not focus
  // it. Restoring "focus" to the body silently leaves a keyboard user at the
  // top of the document, so that case takes the fallback instead.
  let priorFocus = null;
  document.addEventListener('focusin', event => {
    if (!panel.contains(event.target)) priorFocus = event.target;
    clearPreview();
    if (panel.contains(event.target)) return;
    const node = event.target.closest && event.target.closest('[data-ui-ref]');
    if (node) showPreview(node);
  });
  document.addEventListener('focusout', () => clearPreview());

  const reviewEntry = document.querySelector('[data-ui-review-entry]');

  // The entry control and the panel are two faces of the same switch. Closing
  // the panel is not leaving review mode, so the entry must offer the way
  // back -- otherwise close is a one-way door and the focus fallback in
  // close() lands a keyboard user on a control that does nothing.
  const setOpen = open => {
    if (open) panel.removeAttribute('hidden');
    else panel.setAttribute('hidden', '');
    if (reviewEntry) reviewEntry.setAttribute('aria-pressed', open ? 'true' : 'false');
  };

  const report = (outcome, text) => {
    status.setAttribute('data-ui-panel-status', outcome);
    status.textContent = text;
  };

  const viewport = () => getComputedStyle(document.querySelector('main'))
    .getPropertyValue('--viewport-class').trim();

  const lock = item => {
    entries().forEach(other => other.removeAttribute('data-ui-panel-locked'));
    if (item) item.setAttribute('data-ui-panel-locked', 'true');
  };

  // One walk, two doors: the select button (Shift walks backwards, mirroring
  // Shift+Tab) and the ArrowUp/ArrowDown keys ReviewMode's keyboard plan
  // declares. Both step the same ring; a one-way path would force a reviewer
  // past every later entry to reach an earlier one.
  const walk = step => {
    const all = entries();
    if (!all.length) return report('no-target', '没有可选目标');
    const index = all.indexOf(entry());
    lock(all[(index + step + all.length) % all.length]);
    markLockedTarget();
    report('selected', '已选择');
  };

  const actions = {
    select: event => walk(event && event.shiftKey ? -1 : 1),
    lock: () => {
      const current = entry();
      markLockedTarget();
      report(current ? 'locked' : 'no-target', current ? '已锁定' : '没有可选目标');
    },
    clear: () => {
      lock(null);
      markLockedTarget();
      report('cleared', '已清除选择');
    },
    // A copy happens only on a real user gesture, writes once, and is never
    // retried automatically. A rejection keeps the selection so the reviewer
    // can retry deliberately, and the host's own error text is not shown:
    // it can carry detail the reviewer did not choose to surface.
    copy: event => {
      if (!event || !event.isTrusted) return report('refused', '复制需要用户操作');
      const current = entry();
      if (!current) return report('no-target', '没有可复制的目标');
      const token = current.getAttribute('data-ui-panel-token-' + viewport());
      if (!token) return report('no-token', '当前视口没有可用引用');
      report('copying', '正在复制');
      navigator.clipboard.writeText(token).then(
        () => report('copied', '已复制引用'),
        () => report('copy-failed', '复制失败，请重试'),
      );
    },
    // Closing the panel is not leaving review mode. Focus returns to where the
    // reviewer was, and to the review entry when that element is gone, because
    // leaving focus on a hidden element strands a keyboard user at the top of
    // the document.
    close: () => {
      const restored = !!priorFocus && priorFocus.isConnected
        && priorFocus !== document.body && !panel.contains(priorFocus);
      setOpen(false);
      panel.setAttribute('data-ui-panel-closed', restored ? 'restored' : 'fallback');
      const target = restored ? priorFocus : reviewEntry;
      if (target) target.focus();
    },
  };

  panel.addEventListener('click', event => {
    const control = event.target.closest('[data-ui-panel-action]');
    if (!control) return;
    actions[control.getAttribute('data-ui-panel-action')](event);
  });

  // Reopening moves focus into the panel, because that is where a reviewer
  // who just asked for the panel will act next.
  if (reviewEntry) {
    reviewEntry.addEventListener('click', () => {
      if (panel.hasAttribute('hidden')) {
        setOpen(true);
        // The close outcome belongs to the cycle that ended, not to this one.
        panel.removeAttribute('data-ui-panel-closed');
        const first = panel.querySelector('[data-ui-panel-action]');
        if (first) first.focus();
      }
    });
  }

  // Escape clears the selection only while the panel holds focus, mirroring
  // ReviewMode.handle_key: outside the panel the key belongs to the business
  // view and review mode must not consume it.
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (!panel.contains(document.activeElement)) return;
      actions.clear();
      return;
    }
    // Ctrl+C (or Cmd+C) copies the element under discussion. Inside the
    // panel that is the locked selection; on a focused business element it
    // is that element's own token -- Tab traversal is the keyboard way to
    // point, so it must reach the same copy the panel offers. Focused
    // nowhere declared, the chord stays the page's own copy.
    if ((event.key === 'c' || event.key === 'C') && (event.ctrlKey || event.metaKey)) {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        actions.copy(event);
        return;
      }
      const focused = document.activeElement && document.activeElement.closest
        ? document.activeElement.closest('[data-ui-ref]') : null;
      if (!focused) return;
      const ref = focused.getAttribute('data-ui-ref');
      const token = (tokens[ref] || {})[viewport()];
      if (!token) return;
      if (!event.isTrusted) return report('refused', '复制需要用户操作');
      event.preventDefault();
      report('copying', '正在复制');
      navigator.clipboard.writeText(token).then(
        () => report('copied', '已复制引用'),
        () => report('copy-failed', '复制失败，请重试'),
      );
      return;
    }
    // ArrowUp/ArrowDown point at any declared element, from anywhere in the
    // review page: they move focus across every [data-ui-ref] in document
    // order -- the same ring Tab walks. Focus shows the preview, and Ctrl+C
    // copies what is pointed at, so the keyboard path to "this one" needs no
    // panel detour. Review mode is a pointing mode; normal mode has no
    // script at all, so the business page's own use of these keys is only
    // ever borrowed where the reviewer explicitly asked for review.
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const all = Array.from(document.querySelectorAll('[data-ui-ref]'));
    if (!all.length) return;
    const step = event.key === 'ArrowUp' ? -1 : 1;
    const active = document.activeElement;
    // Anchored at the focused business element; from inside the panel, at
    // the element the reviewer was on before the panel (priorFocus).
    const anchor = panel.contains(active)
      ? (priorFocus && priorFocus.closest ? priorFocus.closest('[data-ui-ref]') : null)
      : (active && active.closest ? active.closest('[data-ui-ref]') : null);
    const index = anchor ? all.indexOf(anchor) : (step > 0 ? -1 : 0);
    all[(index + step + all.length) % all.length].focus();
  });
})();
"""


def review_script() -> str:
    """Return the review-mode behaviour layer."""
    return _SCRIPT
