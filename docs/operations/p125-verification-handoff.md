# P125 Verification Handoff

Schema marker: `p125.verification_handoff.v1`.

Current status: planning complete when this artifact set is accepted;
implementation evidence is pending.

This handoff is the planned evidence template for future P125 verification. It
does not claim source implementation, tests, production SLO compliance,
credentialed access, infrastructure authority, or mutation authority.

## Scope

Verification must prove only the P125 scope:

- long-running local/sandbox/shadow replay;
- restart and recovery behavior;
- data-loss and duplicate-record accounting;
- local cost and resource envelope;
- degradation gates;
- exact-zero authority counters.

## Required Inventory

Future executors must provide changed-file inventory grouped by long-run
manifests, restart harnesses, durability ledgers, cost reports, degradation
gates, docs, tests, and generated verification evidence.

## Required Evidence

The completed handoff must include:

- run duration, event volume, replay source, and input hashes;
- hardware context and resource limits;
- restart matrix results;
- lost and duplicate counts by record type;
- CPU, memory, storage, runtime, and per-event cost;
- judgment-quality degradation checks;
- exact-zero authority counters;
- blocked or pending gates with owners.

## Dependencies

- Depends on P123 replay receipts.
- Depends on P124 quality metrics when degradation is measured.
- Blocks P126 disposable staging-lab remediation planning if restart and
  data-loss evidence is absent.
- Does not unblock live connector, credential, auth, staging, production, or
  mutation authority.

## Stop Conditions

Block verification handoff on missing duration, missing event denominators,
lost records without explanation, duplicate records, corrupt resume,
unbounded resource growth, production SLO claims, or nonzero authority
counters.

