# W8 local read-only fixture v1

This fixture validates the `LocalReadOnlyRunOrchestrator` seam with the real
local `CompositionOwner`, while keeping the execution deterministic and
case-local.

It has two scenarios:

- `success`: `FixtureSuccessAdapter` creates, starts, and completes one owner
  run with the semantic result `fixture-ok`.
- `unknown_boundary`: `FixtureUnknownBoundaryAdapter` creates and starts the
  owner run, safe-stops it when an unsupported request reaches the seam, and
  raises `FixtureUnknownBoundary`. The runner catches only this expected
  exception and records the scenario as `expected_fail_closed`, not as a
  successful run.

The adapters never start Codex, open a Provider connection, read credentials,
execute a tool, or perform an external side effect. Each runner case owns its
own workspace, SQLite database, CODEX_HOME, event-log location, and executable
placeholder under a separate temporary case root.

Run the fixture from the repository root:

```bash
PYTHONPATH=src python evaluation/runner/run_w8_local_read_only.py
```

The default output is a temporary directory outside the repository. Use
`--output <directory>` when evidence needs to be retained at a chosen path.

Fixture validation is not evidence that Codex native approval, host-level
network isolation, a real Provider, or production deployment is safe.
