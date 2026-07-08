# OpsCat P41 Ticket Roadmap — Raw Real Dataset Scored Replay

P41 evaluates OpsCat against repo-local source-native dataset files: LogHub-style JSONL logs, NAB-style CSV metrics, and AIOps-style JSONL multi-signal incidents. It scores parser coverage, label coverage, route/root-cause prediction, and safety. It does not download external datasets during verification.

## Tickets

- P41-001 — Raw source manifest: define local source-native files, families, labels, and expected root causes.
- P41-002 — Raw parser layer: parse JSONL log rows, CSV metric rows, and multi-signal JSONL incidents without pre-converting to normalized JSON.
- P41-003 — Deterministic predictor: infer incident class, root cause, severity, and route from raw source signals.
- P41-004 — Ground-truth scorer: compare predictions to labels/root causes and report accuracy, coverage, and misses.
- P41-005 — Safety gates: ensure no live API calls, downloads, production mutation, remediation execution, or unsafe action suggestions.
- P41-006 — Per-source cards: emit source cards with parsed records, incident candidates, labels, and scores.
- P41-007 — CLI report: `scripts/run_raw_real_dataset_replay.py` writes JSON/Markdown reports.
- P41-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- repo-local raw dataset files only
- no external dataset downloads during verification
- no live API calls
- no auth/session work
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls
- no unattended production-operation claim

## Acceptance criteria

- At least three raw sources are evaluated.
- Parsed record count is at least five.
- Label coverage is 1.0.
- Root-cause accuracy is at least 0.9.
- Route accuracy is at least 0.9.
- Unsafe action count is 0.
- Full verification profile includes `raw_real_dataset_replay_smoke`.
