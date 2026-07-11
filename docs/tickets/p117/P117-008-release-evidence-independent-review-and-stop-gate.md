# P117-008: release evidence, independent review, and stop gate

## Goal

Package hash-bound P117 release evidence and require independent review before
any action-selection readiness claim.

## Contract

- Bind hashes for episode registry, schemas, P114 lattice manifest, P115
  action-pack manifest, P116 outcome import manifest, evidence taxonomy,
  contradiction ledger, utility/calibration config, selector outputs,
  tournament report, frozen unseen split, authority scan, verification profile,
  and independent review.
- Require reviewer identity/context to be distinct from planner and implementer.
- Fail stale hashes, self-review, aggregate-only metrics, missing fallback
  receipts, missing denominators, hidden-label exposure, missing authority scan,
  or any nonzero authority counter.
- Downgrade to `p117_contract_ready` when P116 measured outcomes are absent from
  final utility scoring.

## Acceptance

All P117 roadmap gates pass in one fresh evidence set, independent review finds
no authority or leakage blocker, release hashes match, and auth/credential/
executor/shell/subprocess/Kubernetes/cloud/database/production-adapter/network
mutation/online-policy/production-mutation counters are exactly zero.

## Stop Rules

Stop release if the bundle is self-reviewed, stale, missing P116 final utility
inputs, missing per-family metrics, missing deterministic fallback evidence, or
claiming any execution authority.
