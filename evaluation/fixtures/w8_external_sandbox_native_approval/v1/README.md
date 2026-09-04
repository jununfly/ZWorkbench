# W8 external-sandbox and native-approval fixture

This fixture is acceptance/evaluation infrastructure only. It runs the fixed
Codex app-server `0.139.0` under a case-local macOS `sandbox-exec` profile and
uses the v2 `turn/start.sandboxPolicy.type=externalSandbox` override. The
profile allows the loopback fake Responses Provider, allows one workspace
control write, and denies a sibling outside-target write.

The direct probe records only case-local process identity, ancestry, target
status, and the error type. It never reads credentials or sends data to a real
Provider. The runner separately records the native command approval request,
the client decision, `serverRequest/resolved`, and the terminal
`commandExecution` item. Missing request or identity evidence remains
`unknown`; this fixture cannot promote a schema/help observation to native
approval or product host-enforcement evidence.

The command uses an absolute path to this pinned probe and a case-local
`ready/release` handshake. The runner observes the live probe ancestry before
release, then requires Codex to emit the terminal command item. This avoids a
timing-only sleep being mistaken for a complete execution receipt.
