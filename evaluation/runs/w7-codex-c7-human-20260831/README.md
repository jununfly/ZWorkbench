# W7 Codex C7 human upgrade/rollback evidence

- Candidate: Codex Harness
- Operator: single operator
- Environment: temporary C7 npm prefix
- Sequence: `0.138.0 → 0.139.0 → 0.138.0`
- Reported elapsed time: `14.35 seconds` (`0.2392 minutes`)
- Source log: `/var/folders/bk/25klw83n5wn38lj2m3wbr9fc0000gn/T/tmp.VpQ9Wo9uw9/upgrade-rollback.log`
- Source SHA-256: `892bc389c35f63e77f4f734ccc3a8920e2653f1460050279208c2a169603520e`
- Repository copy: `upgrade-rollback.log` is byte-identical to the source log.

The copied log is retained as operator-reported evidence. It establishes the version
sequence and the `app-server --help` output. It does not by itself close C7: backup/restore,
fault diagnosis timing, license/NOTICE/commercial review, and source-to-binary provenance
remain open.
