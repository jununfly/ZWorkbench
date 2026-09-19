---
doc-kind: reference
authority: supporting
---

# UI Reference skills binding

ZWorkbench keeps the product contract in [R1](../prds/r1-ui-reference-registry.md)
and the extraction decision in [R2](../prds/r2-ui-reference-skills.md). The
reusable packages are separate from both product documents:

- [ui-reference-protocol](../../skills/ui-reference-protocol/SKILL.md)
  designs or audits a project-owned `ui-reference-profile/v1`.
- [ui-reference-runtime](../../skills/ui-reference-runtime/SKILL.md)
  consumes that profile and guides an adapter through the public UI Reference
  Contract.

The profile is the only handoff. A project can install either package without
ZWorkbench source files; the runtime package does not import the protocol
package. The project supplies its own renderer, artifact store, source lookup,
review session, host, and browser adapter.

For case-local lifecycle checks, the
[`run_ui_reference_skill_lifecycle.py`](../../evaluation/runner/run_ui_reference_skill_lifecycle.py)
runner can observe `install`, `upgrade`, `rollback`, and `uninstall` from an
explicit local package directory. It verifies the package's declared-file
digest, writes a redacted receipt, and never uses a registry or remote request.
The runner is evaluation infrastructure: it does not apply generated diffs,
grant approval, or create a project runtime.

For a local check, validate the profile with the protocol package's
`scripts/validate_profile.py`, then feed runtime evidence to
`scripts/runtime_status.py`. Evidence identifies the skill, protocol profile,
runtime adapter, environment, required host capabilities, browser capability,
mapping/build artifact, and source identity. `unknown` remains the result when browser or historical
artifact evidence is absent; `HOLD` is used for a malformed, unsafe, or
contradictory contract.

The runtime package may produce a generated diff for review, but applying it is a
separate project-controlled action requiring the project's policy, approval,
effect receipt, and recoverable rollback path. UI review itself cannot apply a
diff, change an Owner, start a run, or contact a Provider.

Evidence must bind the exact profile bytes and protocol version, identify the
skill/adapter/environment versions and evidence layer, and include the measured
browser and protocol versions when browser evidence is claimed. Its
`evidence_identity` is a digest of the canonical evidence object, so changing a
field without regenerating the identity is `HOLD`. Unsafe or malformed evidence
is `HOLD`; missing evidence remains `unknown`.

The independent portability fixture is
[catalog-html](../../evaluation/fixtures/ui_reference_portability/README.md).
It demonstrates the handoff with `data-ref`, an independent static HTML
renderer, and a real-browser review runtime rather than the R1 renderer
vocabulary. Its checks are evidence for portability only; they do not replace
R1 product acceptance. ZWorkbench-specific profile integration is deferred for
this phase and is not an acceptance prerequisite.
