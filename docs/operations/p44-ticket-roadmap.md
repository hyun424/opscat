# OpsCat P44 Ticket Roadmap — Larger Public Dataset Benchmark Matrix

P44 expands P43 from a single public benchmark scorecard into a multi-source benchmark matrix with source-level and family-level scores. Normal verification remains offline and fixture-backed; public downloads remain explicit opt-in.

## Tickets

- P44-001 — Matrix manifest: define multiple LogHub/NAB public sample sources and fallback fixtures.
- P44-002 — Matrix runner: reuse P43 acquisition/materialization but produce source-level score rows.
- P44-003 — Family aggregation: compute loghub/nab family score summaries, record counts, download counts, and weak spots.
- P44-004 — Error analysis: report false-positive/false-negative proxy counts and worst sources.
- P44-005 — Offline verification path: run full verification with fixture fallback and zero downloads.
- P44-006 — Opt-in public benchmark path: support explicit public download matrix execution into `/tmp` artifacts.
- P44-007 — CLI report: emit JSON/Markdown benchmark matrix.
- P44-008 — Release evidence: record offline full verification and opt-in public matrix evidence without committing downloaded data.

## User journey

As an OpsCat builder, I want a multi-source public benchmark matrix, so that I can show which data families OpsCat handles well and where the incident judgment pipeline is weak.

## Boundary

Default verification must perform no external downloads, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim. Public downloads require explicit opt-in and generated artifacts remain outside the repository.
