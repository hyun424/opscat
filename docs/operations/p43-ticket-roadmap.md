# OpsCat P43 Ticket Roadmap — Opt-in Public Dataset Download & Benchmark Scorecard

P43 executes the P42 opt-in path: download small public dataset samples when explicitly allowed, materialize them into OpsCat raw replay format, and produce a benchmark scorecard. Normal verification remains offline and fixture-backed.

## Tickets

- P43-001 — Public benchmark manifest: define public LogHub/NAB source URLs, label artifacts, expected outcomes, and fallback fixtures.
- P43-002 — Network opt-in downloader: download only when `--allow-network` is passed; enforce max-bytes limits.
- P43-003 — Raw materializer: convert downloaded LogHub raw logs and NAB time series/labels into P41-compatible JSONL/CSV.
- P43-004 — Benchmark scorer: score materialized public samples through P41 raw replay.
- P43-005 — Offline fallback: keep full verification network-free by using repo-local fixtures when downloads are not allowed.
- P43-006 — CLI report: emit public-download, materialization, split, score, and boundary evidence.
- P43-007 — Verification integration: add P43 offline smoke to `scripts/verify.sh`.
- P43-008 — Release evidence: record full verification and any opt-in public download benchmark results without committing downloaded data.

## User journey

As an OpsCat builder, I want an explicit command that can fetch small public LogHub/NAB samples and produce an evidence scorecard, so that I can separate real public dataset benchmark evidence from local fixture-only tests.

## Boundary

Default verification must perform no external downloads, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim. Public downloads require explicit opt-in and write generated artifacts outside the repo by default.
