"""The style layer, kept deliberately independent of the reference protocol.

Selectors here address elements structurally: by tag, by document position and
by the shape of the markup. None of them mention ``data-ui-ref``.

That restriction is the point of this module rather than a stylistic
preference. A reference carries semantic identity across releases -- the PRD
requires visual rearrangement to leave a ref untouched, and a change in meaning
to mint a new one with an explicit alias or replaced-by. A stylesheet that
selected on ``[data-ui-ref="..."]`` would make refs load-bearing for
appearance, so restyling would start renaming them and the lifecycle contract
would quietly stop holding.

The layout is intentionally minimal. This module exists to prove that a style
layer can coexist with the protocol, not to propose a visual design.
"""

from __future__ import annotations

from .ui_matrix import VIEWPORT_BREAKPOINT_PX

_TEMPLATE = """\
:root { color-scheme: light dark; }

main { --viewport-class: wide; }

body {
  margin: 0;
  font-family: -apple-system, "Helvetica Neue", sans-serif;
  line-height: 1.5;
}

main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

main > section {
  padding: 8px 12px;
  border: 1px solid rgba(128, 128, 128, 0.4);
  border-radius: 6px;
}

main > ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

main > ul > li {
  padding: 6px 12px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.25);
}

main > button {
  align-self: flex-start;
  padding: 8px 16px;
  font: inherit;
  cursor: pointer;
}

/* The review layer covers the viewport. Covering matters: a layer with no
   area intercepts nothing, so passthrough would be vacuously true and the
   hit test in tests/test_ui_overlay.py would prove nothing. pointer-events is
   set inline from the ReviewMode descriptor rather than here, so the contract
   has one source. */
[data-ui-overlay] {
  position: fixed;
  inset: 0;
  display: block;
}

[data-ui-overlay] > span {
  position: absolute;
  top: 0;
  right: 0;
  padding: 4px 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

/* The review panel is a fixed side region, visually above the business page
   but below nothing the page owns: it appears only in review mode, so these
   rules can never reshape the normal document. */
[data-ui-panel] {
  position: fixed;
  top: 0;
  right: 0;
  width: 300px;
  max-height: 100vh;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: Canvas;
  border-left: 2px solid rgba(128, 128, 128, 0.5);
  font-size: 13px;
  z-index: 2;
}

[data-ui-panel-entries] {
  list-style: none;
  margin: 8px 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

[data-ui-panel-entry] {
  padding: 4px 8px;
  border: 1px solid rgba(128, 128, 128, 0.3);
  border-radius: 4px;
}

[data-ui-panel-locked="true"] {
  outline: 2px solid Highlight;
}

[data-ui-panel-action] {
  display: block;
  width: 100%;
  margin: 4px 0;
  padding: 6px 8px;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

/* The panel is docked, not overlaid: the page makes room for it, so it can
   never cover the element a reviewer is pointing at. ``:has`` keeps the
   padding review-only -- this stylesheet is shared with normal mode, whose
   document has no panel to match, and ``:not([hidden])`` hands the space back
   the moment the panel closes. */
body:has([data-ui-panel]:not([hidden])) {
  /* panel width + its padding and border: the page must make room for the
     whole box, or the root unit's edge slides underneath it. */
  padding-right: 332px;
}

/* Declared elements become focusable in review mode; the ring makes the
   focus stop visible, the preview badge names it. The selector keys off the
   behaviour hook the page layer adds, never the reference attribute itself:
   the style layer stays independent of the reference protocol. */
[data-ui-review-focusable]:focus {
  outline: 2px solid Highlight;
  outline-offset: 2px;
}

/* Visible rings for the two ways an element gets pointed at: a deep link
   locating it, and a reviewer locking it from the panel. Same ring, because
   both mean "this is the element under discussion". */
[data-ui-located],
[data-ui-locked-target] {
  outline: 3px solid Highlight;
  outline-offset: 2px;
}

/* The hover preview lives in the overlay: a dashed box matching the hovered
   element, carrying its Chinese semantic name. The overlay is pointer-events
   none, so the preview can never intercept a click. */
[data-ui-preview-box] {
  position: absolute;
  border: 2px dashed Highlight;
  border-radius: 4px;
}

[data-ui-preview-badge] {
  position: absolute;
  top: -1.7em;
  left: 0;
  padding: 2px 6px;
  background: Canvas;
  border: 1px solid rgba(128, 128, 128, 0.5);
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

/* Last, deliberately. These rules have the same specificity as the ones above,
   so ordering is what decides the outcome -- a media query placed earlier is
   silently overridden, which string inspection of the stylesheet cannot show.
   The class is also published as a custom property, so a reviewer and a test
   can read which branch applied rather than infer it from a measurement. */
@media (max-width: __COMPACT_MAX__px) {
  main { --viewport-class: compact; padding: 8px; gap: 8px; }
  main > section { padding: 6px 8px; }
  /* A 300px side panel would leave a compact page 70px wide. Dock it at the
     bottom instead, and let the page make room downwards. */
  [data-ui-panel] {
    top: auto;
    bottom: 0;
    left: 0;
    width: auto;
    max-height: 50vh;
    border-left: none;
    border-top: 2px solid rgba(128, 128, 128, 0.5);
  }
  body:has([data-ui-panel]:not([hidden])) {
    padding-right: 0;
    padding-bottom: 50vh;
  }
}
"""


#: A plain substitution rather than str.format: CSS is full of braces, and
#: escaping every one of them would make the stylesheet hard to read and easy
#: to break.
STYLESHEET = _TEMPLATE.replace("__COMPACT_MAX__", str(VIEWPORT_BREAKPOINT_PX - 1))


def stylesheet() -> str:
    """Return the workbench stylesheet, pinned to the declared breakpoint."""
    return STYLESHEET
