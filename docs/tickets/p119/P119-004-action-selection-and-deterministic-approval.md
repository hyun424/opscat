# P119-004: action selection and deterministic approval

## Goal

Select frozen P115 action-pack IDs or first-class non-action labels using a
P117-compatible policy, then approve only local/mock/sandbox P118-compatible
operation envelopes after deterministic fail-closed gates pass.

## Contract

- Accept only P117-compatible selected frozen IDs or `no_action`,
  `investigate_more`, `escalate`, and `abstain` labels.
- Reject invented IDs, free-form action prose, mutable action text, LLM command
  text, and action IDs not found in frozen manifests.
- Verify signed action-pack digest, schema, signature, expiration, revocation,
  validation plan, rollback plan, prerequisites, contraindications, fixture
  target binding, and L3 maximum.
- Produce deterministic approval receipts with selected ID, policy hash,
  target fixture, budget snapshot, authority snapshot, and timeline refs.
- Produce local/mock escalation payloads for blocked, contraindicated,
  permanently human-authorized, or policy-rejected cases.

## Acceptance

Unknown, stale, unsigned, revoked, mismatched, credential-bearing,
production-like, command-bearing, free-form, or L4+ actions fail closed;
approval receipts are deterministic and hash-bound; non-action labels remain
first-class; and every approval path reports exact-zero authority counters.

## Stop Rules

Stop if approval can bypass policy, approve production or staging targets,
approve auth-bearing or credential-bearing actions, accept free-form
remediation, execute LLM-generated commands, exceed L3, omit validation or
rollback plans, or claim production execution readiness.
