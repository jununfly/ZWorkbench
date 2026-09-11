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

STYLESHEET = """\
:root { color-scheme: light dark; }

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
"""


def stylesheet() -> str:
    """Return the workbench stylesheet."""
    return STYLESHEET
