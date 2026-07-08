# OpsCat P42 Ticket Roadmap — External Dataset Acquisition & Holdout Evaluation

P42 adds an opt-in external dataset acquisition plan and deterministic holdout evaluation path. Normal verification remains local/reproducible and does not download external datasets.

## Tickets

- P42-001 — External dataset manifest: define official source metadata, licenses/citations, expected formats, destinations, and safety boundaries.
- P42-002 — Acquisition planner: validate manifest and produce a no-network dry-run plan by default.
- P42-003 — Opt-in downloader boundary: require explicit `--allow-network` before any external fetch can be attempted.
- P42-004 — Holdout split builder: create deterministic train/dev/holdout splits from repo-local raw fixtures.
- P42-005 — Holdout scorer: run P41 raw replay scoring on the generated holdout manifest.
- P42-006 — CLI report: emit JSON/Markdown with source readiness, split counts, score, and boundary gates.
- P42-007 — Verification integration: add P42 smoke to `scripts/verify.sh` without live network calls.
- P42-008 — Release evidence: document exact metrics, limits, and remaining production-readiness gaps.

## User journey

As an OpsCat builder, I want a documented, opt-in path to acquire public LogHub/NAB-style datasets and a deterministic holdout scorer, so that portfolio claims can distinguish local fixture readiness from larger external dataset validation.

## Boundary

Default verification must perform no external downloads, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
