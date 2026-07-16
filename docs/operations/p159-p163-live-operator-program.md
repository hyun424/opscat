# P159-P163: Supervised Live Incident-Lab Operator

This program advances OpsCat from recorded operator-replacement evidence to a
real, disposable, numeric-loopback incident lab. It proves the complete local
control loop without expanding authority to customer systems.

| Phase | Capability | Release claim |
| --- | --- | --- |
| P159 | Observable process-owned fault lab | Real loopback observation substrate qualified |
| P160 | Deadman and freshness-aware observation | Continuous local supervision qualified |
| P161 | Blind deterministic/model/hybrid judgment | Recorded blind judgment comparison qualified |
| P162 | Budgeted read-only evidence gathering | Autonomous evidence expansion qualified |
| P163 | Approved action, post-check, rollback | Supervised loopback lab operator qualified |

## Safety invariants

- The server binds only to `127.0.0.1`.
- The client rejects DNS names, non-loopback IPs, redirects, and arbitrary
  action names.
- Canonical qualification never reads an API key and never calls an external
  model.
- Live NVIDIA results are advisory experiment output only.
- Every mutation requires an explicit in-memory approval capability.
- A mutation is not successful until a fresh post-check proves recovery.
- Harmful, stale, or ambiguous post-checks trigger rollback.
- Production and staging mutation counters remain zero.

## Remaining gap after P163

P163 still does not prove customer staging safety, tenant isolation, credential
operations, provider-specific write adapters, or unattended production
authority. Those require a separately governed staging program.
