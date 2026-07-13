# P132 Independent Plan Review

## First review: rejected

The independent critic rejected the first draft because five safety-critical
choices were underspecified: post-replace storage-fault semantics, report
ownership validation, lifecycle receipt/status schema, module-vs-console
command allowlists, and exact resource thresholds. It also found P125 planning
text stale relative to implemented P125 evidence.

## Corrections applied

- Pre-replace faults require the old canonical file unchanged. Post-replace
  directory-sync faults may retain a newer hash-valid file and must disclose
  uncertainty plus prove reload/rewrite recovery.
- Report deletion requires exact filename, regular non-symlink type, bounded
  parse, schema, self-hash, runtime ID, and config hash ownership.
- Lifecycle fields, receipt binding, signal-only handler behavior, 3-second exit
  bound, lease-release ordering, stopped-vs-crashed semantics, and restart
  history are fixed.
- Evaluator module invocation and installed supervisor console script are two
  separate closed command forms bound to `app.monitor_cli:main`.
- Endurance, resource, and backoff values are exact and versioned in
  `evals/p132/input/endurance-profile.json`.
- P125 documents identify implemented local deterministic evidence while
  preserving the original review and non-production boundary.

## Current decision

The second review rejected two remaining cross-document contradictions: the
P132-002 post-replace guarantee and stale P125 ticket status. Both were
corrected. The final independent review returned **APPROVE** with no remaining
concrete blocker and confirmed implementation may begin without unresolved
plan ambiguity.
