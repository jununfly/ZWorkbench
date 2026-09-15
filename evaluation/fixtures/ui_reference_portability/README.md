# UI Reference portability fixture

`v1/` is an independent static HTML project profile and runtime adapter. It
uses `data-ref` and a catalog component renderer rather than ZWorkbench's
views, modules, run model, or owner. Its static adapter exposes semantic
references, mapping/build identity, and ephemeral display outcomes.

The fixture is intentionally local-only. `tests/test_ui_reference_portability.py`
serves the generated HTML from loopback when the verification browser is
available, checks the alternate attribute and synthetic canaries, exercises the
dynamic session, pointer/focus/keyboard/clipboard interaction, and verifies
listener/session teardown on both disable and host unload. It records structural
and full-runtime results separately through the runtime skill's evidence checker.
If the browser or a historical artifact is unavailable, the checker still
returns `unknown`; that missing capability is not replaced by static evidence.

`conformance.json` is the shared positive, negative, security, and unknown corpus
used by the independently installed protocol and runtime validators. The fixture
does not use ZWorkbench modules, owner state, remote requests, or real secrets.
