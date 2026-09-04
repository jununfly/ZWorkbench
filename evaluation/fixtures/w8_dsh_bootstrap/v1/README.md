# W8 DSH bootstrap fixture

This is a deterministic, case-local H1 seam fixture. It emits two JSONL
bootstrap messages and exits; it never reads credentials, calls a Provider, or
uses the network. The executable, dependency lock, build receipt, profile and
manifest are all pinned by SHA-256 values in `manifest.json`.

The fixture proves only the ZWorkbench adapter boundary and owner-backed
failure semantics. It is not a clean ZDSHarness artifact and does not count as
formal DSH source-to-binary provenance or H2-H8 evidence.
