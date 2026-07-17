# P167 Test Spec

- Auto-approve and execute each fixed action in the process-owned lab.
- Deny low-confidence, weakly cited, stale, kill-switched, and deadman-expired
  requests.
- Verify request idempotency and forged approval rejection.
- Verify pre/post hashes and independent recovery checks.
- Force a harmful action and prove rollback closure.
- Produce P167 evidence chained to canonical P166 evidence.
