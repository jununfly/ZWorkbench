---
name: ui-reference-runtime
description: Implement and verify a project's UI Reference Protocol Profile through its existing UI seams.
---

# UI Reference Runtime

Use this skill after a project has an accepted `ui-reference-profile/v1`.
It guides a Coding Agent through a small, observable runtime adapter; it does
not provide a browser framework or own business state.

## Workflow

1. Read and verify the explicit profile. Missing or contradictory input is
   `HOLD`; do not invent a protocol.
2. Discover the existing declaration, build/artifact, renderer, local
   navigation, source lookup, review-session, host boundary, and browser-test
   seams. Record the required host capabilities in evidence; a declared
   capability without runtime evidence remains `unknown`.
3. Implement one vertical slice: a static unit and business action flow from
   declaration → manifest → rendered reference → token/link → exact manifest
   and source resolution.
4. Derive DOM attributes from the validated manifest. Keep structure separate
   from ephemeral session instances and business identifiers.
5. Exercise mismatched identity, undeclared references, missing artifacts,
   changed source, malformed input, and unavailable host capabilities. Preserve
   `unknown`/`HOLD`; never fall back to CSS, coordinates, DOM order, or the
   current first item.
6. Record evidence with profile/protocol identity, skill and adapter versions,
   evidence layer, artifact/source identity, environment, measured browser and
   protocol versions, and side-effect identity. Run
   `python scripts/runtime_status.py PROFILE.json` with the evidence JSON on
   stdin.

The adapter must use the project's existing facade and UI ownership boundary.
It creates no Agent loop, durable owner, scheduler, Provider call, or business
execution path. Keep a generated diff separate from applying a diff: applying
to a protected workspace requires the project's explicit policy and approval,
and every applied change needs a recoverable rollback path. See
[runtime-contract.md](references/runtime-contract.md).
