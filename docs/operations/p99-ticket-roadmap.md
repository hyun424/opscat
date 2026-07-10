# P99 Comprehensive Operational Failure Matrix

## Outcome

Expand OpsCat's causal evaluation coverage beyond the original 12 representative
families. P99 adds system-resource, storage, database, network, platform, messaging,
scheduler, configuration, security, data-integrity, regional, and cascading-failure
families while preserving P97's hidden-truth and loopback-only safety boundaries.

## Tickets

- **P99-001 — Taxonomy contract and RED tests**
  - Lock 40 additional families, 10 stress variants, deterministic splits, unique opaque IDs, and minimum domain coverage before implementation.
- **P99-002 — Expanded closed action registry**
  - Add only named in-memory lab actions required by the new families. Preserve zero arbitrary commands, endpoints, credentials, subprocesses, filesystem mutation, and production access.
- **P99-003 — Resource and host failures**
  - Cover memory leak, OOM, CPU throttling, thread-pool exhaustion, file-descriptor exhaustion, disk capacity, and disk IOPS saturation.
- **P99-004 — Database and data failures**
  - Cover lock contention, replication lag, slow query, schema mismatch, data corruption, storage corruption, and search-index lag.
- **P99-005 — Network and dependency failures**
  - Cover DNS, TLS expiry, packet loss, clock skew, rate limit, quota exhaustion, dependency brownout, service-discovery staleness, and regional partial outage.
- **P99-006 — Workload and platform failures**
  - Cover autoscaling oscillation, traffic spikes, retry storms, cache stampede, leader-election churn, canary regression, rollback failure, and cascading failure.
- **P99-007 — Messaging and scheduled-work failures**
  - Cover poison messages, duplicate processing, batch failure, missed scheduler jobs, and webhook delivery failure.
- **P99-008 — Configuration, security, and business failures**
  - Cover config drift, feature-flag drift, secret expiry, cost runaway, and privileged/data-loss-sensitive remediation boundaries.
- **P99-009 — Evidence-only baseline mappings**
  - Add deterministic visible-evidence mappings for the new families without exposing family names, required actions, harmful actions, variants, or expected outcomes to selectors.
- **P99-010 — Broad matrix CLI and reports**
  - Add bounded smoke and full 520-case modes with overall, split, family, action, and hard-safety output.
- **P99-011 — Verification and release evidence**
  - Run targeted tests, Ruff, mypy, full regression, broad causal matrix, documentation contracts, and repository hygiene checks.

## Stop condition

P99 is complete when the combined catalog contains 52 families and 520 cases,
all additional runbook actions are accepted only by the closed local lab registry,
the broad causal runner emits measured outcomes, and every hard safety gate passes.
P99 does not claim the taxonomy is literally exhaustive or prove production
remediation effectiveness.
