# P125 Verification Handoff

Schema marker: `p125.verification_handoff.v1`.

Current status: implemented and promoted for the committed deterministic local
shadow profile.

This handoff remains the evidence contract for P125 verification. Source,
tests, and promoted evidence now exist, but it still does not claim production
SLO compliance, credentialed access, infrastructure authority, or mutation
authority.

## Scope

Verification must prove only the P125 scope:

- long-running local/sandbox/shadow replay;
- restart and recovery behavior;
- data-loss and duplicate-record accounting;
- local cost and resource envelope;
- degradation gates;
- exact-zero authority counters.

## Required Inventory

Verifiers must inspect changed-file inventory grouped by long-run
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
