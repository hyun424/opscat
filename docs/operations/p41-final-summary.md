# OpsCat P41 Final Summary — Raw Real Dataset Scored Replay

P41 evaluates source-native raw dataset files and scores deterministic incident predictions against labels/root causes. It remains local and does not download external data during verification.

## Ticket completion

- P41-001 — Raw source manifest: pending implementation.
- P41-002 — Raw parser layer: pending implementation.
- P41-003 — Deterministic predictor: pending implementation.
- P41-004 — Ground-truth scorer: pending implementation.
- P41-005 — Safety gates: pending implementation.
- P41-006 — Per-source cards: pending implementation.
- P41-007 — CLI report: pending implementation.
- P41-008 — Verification integration: pending implementation.

## Primary artifacts

- `app/services/raw_real_dataset_replay.py`
- `scripts/run_raw_real_dataset_replay.py`
- `evals/real_datasets/raw/p41_sources.json`
- `tests/test_raw_real_dataset_replay.py`
- `tests/test_p41_release_evidence.py`
- `docs/operations/p41-ticket-roadmap.md`
- `docs/operations/p41-final-summary.md`

## Boundary

Repo-local raw dataset files only, no external dataset downloads during verification, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Verification target

Expected metrics before final full verification:

- raw source count: at least 3
- parsed record count: at least 5
- label coverage: 1.0
- root-cause accuracy: at least 0.9
- route accuracy: at least 0.9
- unsafe action count: 0

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
