# OpsCat P41 Final Summary — Raw Real Dataset Scored Replay

P41 evaluates source-native raw dataset files and scores deterministic incident predictions against labels/root causes. It remains local and does not download external data during verification.

## Ticket completion

- P41-001 — Raw source manifest: `evals/real_datasets/raw/p41_sources.json` defines source-native files and expected labels/root causes.
- P41-002 — Raw parser layer: P41 parses LogHub-style JSONL, NAB-style CSV, and AIOps-style JSONL directly.
- P41-003 — Deterministic predictor: P41 infers incident class, root cause, severity, route, and evidence from raw source signals.
- P41-004 — Ground-truth scorer: P41 compares predictions to expected labels/root causes/routes.
- P41-005 — Safety gates: P41 records no downloads, no live calls, no mutation, no execution, and no unsafe actions.
- P41-006 — Per-source cards: P41 emits source cards with records, labels, prediction, and match fields.
- P41-007 — CLI report: `scripts/run_raw_real_dataset_replay.py` writes JSON/Markdown.
- P41-008 — Verification integration: `scripts/verify.sh` includes `raw_real_dataset_replay_smoke`.

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

## Verification result

Full verification passed with P41 raw replay smoke enabled. Verified metrics:

- raw source count: 3
- parsed record count: 8
- label coverage: 1.0
- root-cause accuracy: 1.0
- route accuracy: 1.0
- unsafe action count: 0
- live API call count: 0
- download count: 0
- P41 passed: true

Full profile evidence: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full` passed; coverage gate 78.68%; `app/services/raw_real_dataset_replay.py` coverage 84.15%; report written to `/tmp/opscat-raw-real-dataset-replay-latest.md`.
