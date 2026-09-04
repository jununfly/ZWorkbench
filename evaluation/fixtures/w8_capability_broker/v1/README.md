# W8 case-local capability broker

This fixture is acceptance/evaluation infrastructure, not a production
permission service. It exposes one small request interface and one durable
JSONL audit stream for a case-local broker process.

The broker owns the observable policy decision for four capability classes:

- `dns.resolve`: static loopback allowlist; no system resolver is called;
- `network.connect`: loopback endpoint allowlist; this fixture performs no
  network connection;
- `credential.read` and `process.spawn`: denied unless a future policy
  explicitly supplies a safe capability, with no credential or child process
  started by this fixture; and
- `effect.write`: only a file below the case workspace is allowed.

Every request returns `decision`, `reason`, `policy_sha256`, `effect_status`,
`physical_effect_count`, and `external_io_count`. An allowed write records a
durable `decision`/claim before the file operation and a separate completion
receipt after it. Unknown protocol, operation, resource, or target conditions
fail closed. The broker is not connected to the default ZWorkbench runtime.
