# W8 host/broker rejection fixture

This fixture is acceptance/evaluation infrastructure, not product code. It
answers a narrower question than `1-6-3` asks: can a fixed, case-local broker
and a macOS host profile produce an auditable allow/deny boundary around a
real Codex `0.139.0` app-server process?

The runner keeps four observations separate:

1. broker allows one write below the case workspace;
2. broker denies one write outside the workspace and records the denial;
3. a direct Codex child command attempts the same outside write and receives a
   host-level `PermissionError` under the profile;
4. a direct Codex child command writes one workspace file as an allowed host
   control.

The result is candidate-level host-boundary evidence only. It does not prove
Codex native approval semantics, provider safety, or production-wide process
containment. The broker is not a default ZWorkbench service.
