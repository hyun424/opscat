# P160 Test Spec

- Healthy fresh telemetry remains healthy.
- Fault telemetry opens an incident candidate.
- Stale data is a telemetry failure, not a service diagnosis.
- Connector failure is explicit and fail-closed.
- Duplicate fingerprints are suppressed; changed generations are not.
- Heartbeat and freshness metrics are present in qualification evidence.
