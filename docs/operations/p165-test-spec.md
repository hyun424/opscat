# P165 Test Spec

- Run multiple loopback observations into a durable ledger.
- Restart the observer and resume exactly once from its checkpoint.
- Reject duplicate cursors and detect a forged ledger link.
- Detect stale telemetry and deadman expiry independently.
- Verify atomic checkpoint state and complete hash-chain recovery.
- Produce P165 evidence chained to canonical P164 evidence.
