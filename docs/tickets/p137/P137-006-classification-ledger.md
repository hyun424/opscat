# P137-006 - Classification and investigation ledger

## Scope

Implement terminal classification records and the P137 investigation ledger that
chains incidents, hypotheses, requests, classifications, counters, resources,
and authority evidence.

## Acceptance

- `confirmed_incident`, `insufficient_evidence`, `benign_anomaly`, and
  `aborted_fail_closed` are derived only from durable accepted-incident state and
  exact rules.
- `aborted_fail_closed` is claimed only when the classification record write and
  ledger CAS both succeed. Corrupt state, CAS, lease, signal, or resource
  failures that cannot safely complete both writes return classification `none`
  with exact expected error and termination reason.
- Pre-ingest failures create no classification and report exact errors instead.
- Classification records bind top hypothesis, support summaries,
  contradictions, missing evidence, authority counters, runtime activity,
  resources, and previous classification hash.
- Ledger validation recomputes every sequence, transition, hash link, CAS
  predecessor, attempted request hash, duplicate count, counter, resource value,
  and terminal classification.
- Forged summaries, detached classifications, fabricated counters, and terminal
  state rewrites fail closed.
- Dedicated classification and ledger tests pass.
