---
name: ui-reference-protocol
description: Design or audit a portable UI Reference Protocol Profile for semantic UI references.
---

# UI Reference Protocol

Use this skill when a project needs a stable, reviewable way to point at UI
semantics across layout, build, and source changes. The deliverable is a
project-owned protocol profile; it is not a component map or a UI runtime.

## Workflow

1. Classify the request as `design`, `audit`, or `missing-profile`.
2. Discover the project's existing naming, rendering, artifact, source,
   host-boundary, browser, and local-navigation conventions before proposing
   new identity fields; record them as structured discovery input.
3. Define semantic identity separately from accessible copy, presentation,
   source provenance, build identity, and ephemeral review-session instances.
4. Specify exact token/deep-link whitelists, migration outcomes, privacy
   boundaries, host capabilities, side-effect boundaries, and evidence gates.
5. Write the profile as the explicit handoff artifact and validate it with
   `python scripts/validate_profile.py PROFILE.json`; validate project
   declaration/lifecycle input with `python scripts/validate_declarations.py
   DECLARATIONS.json`.
6. Report `implemented`, `target`, `unknown`, `HOLD`, `blocked`, `migrated`,
   `retired`, `incompatible`, and `source-mismatch` only when the evidence
   supports each status. Missing host, browser, artifact, or source evidence
   remains `unknown`/`HOLD`.

## Boundaries

The profile contains protocol and approved metadata only. Keep prompts,
business data, credentials, cookies, approval tokens, event bodies, input
contents, absolute paths, and durable run state outside it. A token is a
locator, never authorization or execution. Do not create a second Agent loop,
durable owner, scheduler, or hand-maintained element mapping.

See [profile-contract.md](references/profile-contract.md) for the schema and
[minimal-profile.json](examples/minimal-profile.json) for a project-neutral
fixture. Use `--discovery DISCOVERY.json` with `scripts/profile_status.py
--mode design` when reporting discovered project conventions; without discovery
the result remains `target`, and missing capabilities remain `unknown`.
