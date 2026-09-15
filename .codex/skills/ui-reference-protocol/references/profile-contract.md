# UI Reference Protocol Profile v1

`ui-reference-profile/v1` is the explicit handoff between protocol design and
runtime implementation. It describes contracts, not a project's live UI or
business records. The canonical validator is
`scripts/validate_profile.py`; a runtime adapter must consume the validated
output rather than infer a contract from rendered markup.

The top-level object has exactly these sections:

| Section | Contract |
| --- | --- |
| `schema` | Fixed to `ui-reference-profile/v1`. |
| `protocol` | Project-neutral protocol name and independently versioned protocol version. |
| `identity` | Reference naming pattern, mapping identity, build identity, and repository-relative source provenance model. |
| `contract` | Semantic coverage scope, separated identity domains, concrete declaration/artifact/token/link/source field mappings, value enums, and explicit lifecycle window. |
| `instances` | `review-session` scope, `random-memory-only` handle, and uncertainty outcomes `ambiguous`, `unavailable`, `expired`. |
| `migration` | `explicit-only` policy and distinguishable `migrated`, `retired`, `incompatible` outcomes. |
| `token` | Positive byte budget and the exact locator/display field whitelist; `instance` is optional. |
| `deep_link` | Locator fields only and `side_effects: false`. |
| `security` | Forbidden data categories, no remote requests, and no persistent storage. |
| `trust` | Locator-only token, project-owned state, ephemeral review state, and no effects. |
| `host` | Required rendered surface, manifest artifact, source provenance, review session, and local navigation capabilities; a missing capability is `unknown`. |
| `review` | Default disabled, explicit enable, pointer passthrough, user-initiated clipboard, and full teardown. |
| `evidence` | Required evidence identities and `preserve-unknown` policy. |
| `acceptance` | Required gates, `all-required` threshold, and `preserve-unknown` policy. |

Lists are non-empty, duplicate-free, and canonicalised in sorted order. The
validator rejects unknown or missing fields, collapsed identity mappings,
contradictory safety constraints, unsupported values, and obvious credential/path
markers. `profile_status.py --mode design --profile PROFILE.json --discovery
DISCOVERY.json` records renderer, host boundary, browser, and local navigation
conventions alongside capabilities, assumptions, unknowns, and profile
identity. `scripts/validate_declarations.py` separately validates a project's
declaration graph, including duplicate references, parent cycles, alias
collisions, and missing or cyclic replacements. Keep project names, views,
routes, framework details, and dynamic data in a separate project profile or
fixture; do not add them to this portable contract.
