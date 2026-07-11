# P116-004: paired action/no-action/wrong-action runner

## Goal

Run comparable lab arms that distinguish useful interventions from no-action,
wrong-action, rollback-only, and natural recovery.

## Contract

- For each scoring cell, run matched action, no-action, wrong-action, rollback,
  and natural-recovery arms from the same fixture version, seed, fault receipt,
  and initial-condition fingerprint.
- Randomize arm order using a recorded schedule.
- Seal candidate-visible observations before resolving hidden scorer labels.
- Record raw observations, lab action receipts, rollback receipts, reset
  receipts, and terminal health windows.
- Treat missing, censored, or incomparable controls as `inconclusive` or
  `invalid`.

## Acceptance

The runner never credits natural recovery, no-op, reset, or wrong-action
recovery as intervention success. Paired metrics are computed only from cells
with complete controls and comparable fingerprints.
