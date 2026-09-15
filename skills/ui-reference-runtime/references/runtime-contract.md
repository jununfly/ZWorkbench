# Runtime implementation contract

The runtime skill consumes a validated `ui-reference-profile/v1`; it never
imports another skill's files. A project-specific adapter maps the profile to
its own public UI Reference Contract.

The profile's `contract` section is executable input: adapters use its concrete
field mappings and enums rather than inferring names from rendered markup.

## Vertical slice

The smallest useful slice proves all of the following with public behavior:

1. code declares one semantic static unit and one business action;
2. a deterministic build derives a manifest and build identity;
3. the renderer emits references only for manifest declarations;
4. a review token and local deep link carry only whitelisted locator/display
   data;
5. exact mapping/build identity resolves back to the manifest;
6. repository-relative source provenance resolves only when its content
   identity still matches.

Repeated structures reuse a structural reference. Their random,
memory-only handles belong to the current review session; they are not derived
from business IDs, titles, indexes, hashes, or durable run state.
Mounting and remounting are rejected after session close; close clears the
selection and makes every prior handle `expired`. Unmounting retains only
enough in-memory association to return `unavailable`, while remounting the
same entity in the same open session may restore its handle.

Review mode is default-off and explicitly enabled. Hover/focus previews only;
locking is a panel action. The highlight layer passes pointer events through,
keyboard actions remain reachable, clipboard writes require a user gesture,
copy failure is visible without automatic retry, and disable/unload releases
every overlay, listener, timer, and task.

## Failure contract

Return structured outcomes for `ambiguous`, `unavailable`, `expired`,
`manifest-missing`, `source-mismatch`, and `incompatible`. Reject unknown,
duplicated, malformed, oversized, or wrongly typed token/link fields. A
missing browser, artifact, source, or required host capability is
`unknown`/`HOLD`. Resolution never guesses from layout or silently substitutes
the current artifact for a requested historical identity.
Deep-link parsers accept only local relative entry points; external origins,
unknown parameters, repeated parameters, and missing locator parameters are
rejected before any view lookup.

The skill may produce a reviewable generated diff, but applying it is a
separate project-controlled action. The runtime adapter must stop before an
unauthorised apply and name the policy, approval, effect receipt, and
recoverable rollback path required by the host.

## Evidence input

The portable checker accepts an evidence object with exactly these fields:

```json
{
  "status": "implemented",
  "profile_schema": "ui-reference-profile/v1",
  "profile_identity": "<sha256 of the profile bytes>",
  "protocol_version": "1",
  "skill": "ui-reference-runtime@1",
  "manifest_schema": "ui-ref-manifest/v1",
  "token_schema": "ui-ref/v1",
  "evidence_identity": "<sha256 of canonical evidence excluding this field>",
  "runtime_adapter": "project-ui-reference-contract@1",
  "environment": "portable-fixture@1",
  "host_capabilities": [
    "rendered-surface",
    "manifest-artifact",
    "source-provenance",
    "review-session",
    "local-navigation"
  ],
  "evidence_kind": "outer-composed",
  "browser": "verified",
  "browser_version": "<measured browser version>",
  "browser_protocol_version": "<measured protocol version>",
  "artifact": "exact",
  "mapping_identity": "<sha256>",
  "build_identity": "<sha256>",
  "source_identity": "exact",
  "rendered": {"declared": 2, "undeclared": 0},
  "resolution": {"manifest": "exact", "source": "exact"},
  "scope": "full-runtime",
  "runtime_gates": {
    "dynamic-session": "verified",
    "interaction": "verified",
    "teardown": "verified",
    "coverage-matrix": "verified"
  },
  "side_effects": "none"
}
```

`scope: static-closure` reports the declaration/manifest/DOM/token/source chain
as implemented but sets `complete: false` and names the runtime gates still
uncovered. `scope: full-runtime` can set `complete: true` only when every
runtime gate is verified in addition to the profile, protocol, skill, schema,
artifact, browser, source, resolution, and zero-side-effect checks. Missing
browser, browser-version, source, resolution, historical artifact, or runtime
gate evidence returns `unknown`; malformed, contradictory, unsafe, or untyped
evidence returns `HOLD`. Reports include identity, evidence, uncovered items,
next evidence, owner, and rollback path. Evidence must not include prompts,
business data, credentials, cookies, absolute paths, or event bodies.

`evidence_identity` is the SHA-256 of the complete evidence object after removing
`evidence_identity`, serialized as UTF-8 JSON with sorted keys and compact
separators. Changing any evidence field without regenerating this digest is a
content-integrity failure and returns `HOLD`.
