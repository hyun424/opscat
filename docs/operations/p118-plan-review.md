# P118 Independent-Style Plan Review

## Decision: accepted as local/mock/sandbox reactive execution substrate

P118 is accepted only as a local/mock/sandbox reactive execution substrate for
signed, frozen P115 action packs selected by P117. It may define operation
contracts, WAL, CAS, idempotency, leases, deterministic approval, validation,
rollback, crash recovery, replay, frozen evaluation, and release evidence.

P118 is not accepted as production-safe autonomous remediation, live canary
execution, operator replacement, or a credential-bearing execution layer.

This review covers documentation-only planning artifacts. It does not approve
source-code edits, production access, runtime deployment, or live mutation.

## Required Constraints Incorporated

- P115 remains the action-pack boundary. P118 consumes signed action-pack IDs,
  digests, validation metadata, rollback metadata, prerequisites,
  contraindications, and signer receipts.
- P116 remains the lab-control boundary. P118 inherits local rollback, crash,
  idempotency, concurrency, orphan cleanup, reset, and replay expectations.
- P117 remains proposal-only. P118 accepts only frozen P117 selected
  action-pack IDs and rejects free-form action prose or LLM-generated commands.
- Auth is deferred. Human identity/session binding, credentials, secret scopes,
  live connectors, and production adapters are out of scope.
- L3 is the maximum action level. L4+ and broad blast-radius operations fail
  closed.
- Operation state is guarded by append-only WAL receipts, CAS transitions,
  idempotency keys, and single-owner leases.
- Approval is deterministic and can approve only local/mock/sandbox L0-L3
  action packs with valid signatures, digest matches, local fixture targets,
  validation plans, rollback plans, and clean authority counters.
- Validation, rollback, rollback postcheck, crash recovery, terminal replay,
  and frozen evaluation are release gates.
- Auth, credential, executor, shell, subprocess, Kubernetes, cloud, database,
  production-adapter, network, online-policy, and production-mutation counters
  remain exactly zero.

## Adversarial Concerns

- "Reactive execution" can be misread as production remediation. P118 limits
  the claim to local/mock/sandbox substrate readiness and rejects production
  mutation.
- Signed action packs can look executable outside their fixture context. P118
  requires exact P117/P115 ID and digest matching plus local fixture target
  binding before approval.
- Approval policy can become a rubber stamp. P118 requires deterministic
  fail-closed evaluation for stale, unsigned, revoked, contraindicated,
  auth-bearing, production-like, or L4+ packs.
- WAL and CAS can record inconsistent state under concurrency. P118 makes lease
  ownership, CAS conflict rejection, and replay consistency release gates.
- Idempotency can hide duplicate action attempts. P118 requires duplicate
  prevention and exact duplicate-action counters.
- Rollback can be claimed without evidence. P118 requires rollback evidence and
  rollback postcheck evidence before `rolled_back`.
- Crash recovery can re-run effects. P118 requires crash-point tests, orphan
  inventory, terminal replay read-only behavior, and duplicate-action blocking.
- Frozen evaluation can be retuned after failure. P118 consumes the split on
  first score and fails stale hashes, tampering, and self-review.

## Residual Risks

- Local/mock/sandbox fixture behavior may not predict production behavior. P118
  must not claim production safety or production remediation quality.
- Auth deferral means operator identity, credentials, session binding, and
  approval provenance are not production-ready.
- L3 maximum still requires careful fixture definition; hidden production-like
  target strings must be scanned adversarially.
- Crash recovery evidence can be incomplete if future implementation omits
  kill-point coverage around report writes or rollback postchecks.
- Independent review quality depends on reviewer separation and fresh evidence
  hashes.

## Review Verdict

Documentation and future implementation may proceed only inside the P118
planning boundary: local/mock/sandbox operation contracts, signed-pack
verification, deterministic approval, WAL/CAS/idempotency/lease control,
validation, rollback, crash recovery, frozen evaluation, release evidence, and
tests.

Any release or portfolio claim may say "local/mock/sandbox reactive execution
substrate readiness" only after frozen fail-closed evaluation and independent
review pass. It may not say "production-safe autonomous remediation",
"production execution", "live canary authority", "credentialed action
execution", or "operator replacement".

## Stop Conditions

Stop before implementation or release if any requirement pressures P118 to add
auth, credentials, secret scopes, production mutation, live connector calls,
online policy writes, shell/subprocess execution, Kubernetes/cloud/database/
network mutation, L4+ authority, free-form action execution, LLM command
execution, fail-open approval, stale release evidence, self-review, or claims
beyond local/mock/sandbox readiness.
