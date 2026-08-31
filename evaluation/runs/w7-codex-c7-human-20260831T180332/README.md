# W7 Codex C7 human backup/restore evidence

- Candidate: Codex Harness `codex-cli 0.139.0`
- Operator: single operator
- Scenario: owner-backed `backup_restore`, repeat `01`
- Reported stopwatch: `12.38 seconds` (`0.2063 minutes`)
- Threshold: `≤30 minutes` — time item passes
- Provider: loopback-only fake Provider; no real credentials, production data, or external network
- Verification: `status: pass`; all 20 operation checks are `true`
- Machine elapsed: `1.079886 seconds` — informational only, not used as human time
- Evidence: [`operation-result.json`](./cases/backup_restore/repeat-01/operation-result.json)
- Evidence SHA-256: `82da44e18db730b2baac6596ca66d7b5e096e99bfad261cc884e11e1cc5c62c3`

The owner state digest before backup and after restore is
`3aa14261ae00cdde5455075e5406fd2b806e100e220c3ba2721683200e2e4023`.
The backup manifest, backup SQLite database, restored database, before/after state
JSON, adapter event log, and Provider request log are retained under the case directory.

This closes the backup/restore human timing item only. It does not close fault diagnosis
timing, legal/NOTICE/commercial review, remote exit responsibility, independent rebuild,
or Codex native approval.
