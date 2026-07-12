# P126 Adversarial Test Specification

This specification is a planning handoff for future P126 implementation.
Implementation is pending. It does not require source-code edits, test edits,
credentials, real staging access, production access, or mutation during this
documentation turn.

## Contract and Authority

- Reject credentials, secrets, real staging targets, production targets,
  shared environments, persistent targets, unlabeled resources, missing TTL,
  missing destruction proof, free-form action prose, LLM command text, and L4+
  action requests.
- Require exact-zero counters for credential authority, real staging mutation,
  production mutation, live customer connector calls, and authority escape.
- Reject claims that disposable lab remediation proves real staging or
  production safety.

## Disposable Lab Isolation

- Detect missing lab label, missing owner, missing TTL, missing isolation
  boundary, overlapping resource name, persistent resource, shared target,
  missing cleanup plan, and missing destruction receipt.
- Require preflight to fail closed before any action when isolation is not
  proven.

## Remediation Execution

- Detect action without simulation, action without approval fixture, action
  outside catalog, rollback missing, validation missing, unbounded blast
  radius, command injection, and target drift between simulation and action.
- Require receipts for simulation, action, validation, rollback, and cleanup.

## Named RED Cases

- `real_staging_target_present`
- `production_target_present`
- `unlabeled_mutable_target`
- `missing_lab_ttl`
- `missing_destruction_receipt`
- `action_without_simulation`
- `action_outside_lab_catalog`
- `rollback_missing`
- `target_drift_after_preflight`
- `nonzero_real_staging_mutation_counter`
- `nonzero_production_mutation_counter`

## Verification Profile

Future implementation must provide targeted P126 verification for lab
isolation, preflight denial, simulation-before-action, catalog enforcement,
validation, rollback, cleanup, destruction proof, and exact-zero non-lab
authority counters. Documentation completion does not require those tests to
exist yet.

