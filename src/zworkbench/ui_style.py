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

/* Last, deliberately. These rules have the same specificity as the ones above,
   so ordering is what decides the outcome -- a media query placed earlier is
   silently overridden, which string inspection of the stylesheet cannot show.
   The class is also published as a custom property, so a reviewer and a test
   can read which branch applied rather than infer it from a measurement. */
@media (max-width: __COMPACT_MAX__px) {
  main { --viewport-class: compact; padding: 8px; gap: 8px; }
  main > section { padding: 6px 8px; }
}
"""


#: A plain substitution rather than str.format: CSS is full of braces, and
#: escaping every one of them would make the stylesheet hard to read and easy
#: to break.
STYLESHEET = _TEMPLATE.replace("__COMPACT_MAX__", str(VIEWPORT_BREAKPOINT_PX - 1))


def stylesheet() -> str:
    """Return the workbench stylesheet, pinned to the declared breakpoint."""
    return STYLESHEET
