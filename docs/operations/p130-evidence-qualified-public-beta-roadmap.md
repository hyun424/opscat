# P130 Evidence-Qualified Public Beta Roadmap / PRD

## Objective

P130 plans an evidence-qualified public beta. It defines what must be true
before public beta claims can be made. Implementation is pending.

## Product Claim

P130 may claim only a planned public beta readiness framework for local,
sandbox, replay, and disposable-lab qualified evidence. It may not claim
production autonomy, production remediation, real staging mutation, credentialed
execution, auth completion, or operator replacement.

Required limitation: public beta is evidence-qualified and non-production.
Auth is deferred, credentials are out of scope, production/staging mutation is
forbidden, and all authority counters remain exactly zero.

## Scope

- Beta entry criteria and evidence manifest.
- Public claim ledger and limitations.
- Known-risk register and support boundary.
- Beta feedback intake without credentials or production access.
- Exit, rollback, and claim-withdrawal policy.

## Dependencies

P130 depends on accepted P123-P129 planning and future verified evidence where
implementation is later authorized. It does not itself authorize code changes,
release publication, credentials, live connectors, staging, production, or
mutation.

## Tickets

1. `[planned] P130-001` - beta entry criteria and evidence manifest
2. `[planned] P130-002` - public claim ledger and limitation language
3. `[planned] P130-003` - known-risk register and support boundary
4. `[planned] P130-004` - beta feedback intake and no-credential process
5. `[planned] P130-005` - verification handoff, exit, and rollback gates

## Gates

- Implementation may start only after all P130 planning artifacts and tickets
  are accepted.
- No public beta claim is allowed without evidence, limitation, owner, and
  withdrawal path.
- All production/staging mutation and credential authority counters are zero.

## Executable Contract

- Service: `app/services/p130_public_beta.py`
- Builder: `scripts/build_p130_public_beta.py`
- Validator: `scripts/validate_p130_public_beta.py`
- Tests: `tests/test_p130_public_beta.py`
- Verify profile: `p130-release`
- Inputs: current P123-P129 release evidence and
  `evals/p130/independent-review.json`
- Outputs: `evals/p130/claim-ledger.json`, `evals/p130/risk-register.json`,
  `evals/p130/beta-evidence.json`, and `evals/p130/release-evidence.json`
- Schemas: `p130.claim_ledger.v1`, `p130.risk_register.v1`,
  `p130.beta_evidence.v1`, `p130.release_evidence.v1`

Every claim records owner, status (`supported`, `limited`, or `blocked`),
evidence, test, limitation, scope, review date, and withdrawal path. Every risk
records severity, owner, mitigation, residual risk, review date, and stop or
rollback condition. Gates require current valid P123-P129 evidence, a distinct
reviewer PASS, traceability 1.0, undocumented or untraced claims 0,
high/critical open release blockers 0, auth/live-production/operator-
replacement claims 0, exactly-zero runtime authority, and visible withdrawal.

Verification commands are the targeted pytest file, builder, validator, and
`bash scripts/verify.sh p130-release`.
