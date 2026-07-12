# P127 Verification Handoff

Schema marker: `p127.verification_handoff.v1`.

Current status: planning complete when this artifact set is accepted;
implementation evidence is pending.

This handoff is the planned evidence template for future P127 verification. It
does not claim source implementation, tests, real staging chaos, production
chaos, credentialed access, or production resilience.

## Scope

Verification must prove only the P127 scope:

- local/sandbox/replay/disposable-lab fault injection;
- fail-closed decisions;
- operator-visible reasons;
- containment, rollback, cleanup, and data preservation;
- claim controls;
- exact-zero non-lab authority counters.

## Required Inventory

Future executors must provide changed-file inventory grouped by fault catalog,
injection controls, fail-closed records, containment checks, rollback/cleanup,
data preservation, claim controls, docs, tests, and generated verification
reports.

## Required Evidence

The completed handoff must include:

- fault catalog coverage;
- injection scope evidence;
- fail-closed decision records;
- blocked-action receipts;
- operator-visible reason samples;
- retry and containment results;
- lost-record counts;
- exact-zero authority counters;
- blocked or pending gates with owners.

## Dependencies

- Depends on P126 disposable-lab boundary evidence when lab mutation is used.
- Blocks P128 operator evidence/replay UX if fail-closed reasons are not
  durable and inspectable.
- Does not unblock real staging, production, credential, auth, or non-lab
  mutation authority.

## Stop Conditions

Block verification handoff on fail-open behavior, real staging chaos,
production chaos, missing operator reason, hidden retries, lost fail-closed
audit records, missing replay receipts, production resilience claims, or
nonzero authority counters.

