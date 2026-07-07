# P10 Tickets — Incident Judgment Benchmark

Source roadmap: `docs/operations/p10-ticket-roadmap.md`.

Execution must follow: plan -> plan review -> RED tests -> implementation -> GREEN verification -> integration verification.

## Ordered Tickets

- [P10-001 — Judgment Dataset Schema](p10-001-judgment-dataset-schema.md)
- [P10-002 — LogHub-style Adapter](p10-002-loghub-style-adapter.md) — depends on P10-001, P10-004
- [P10-003 — NAB-style Metric Adapter](p10-003-nab-style-metric-adapter.md) — depends on P10-001, P10-004
- [P10-004 — Judgment Rubric Format](p10-004-judgment-rubric-format.md) — depends on P10-001
- [P10-005 — Commander Judgment Evaluator](p10-005-commander-judgment-evaluator.md) — depends on P10-001, P10-004
- [P10-006 — Dataset Conversion CLI](p10-006-dataset-conversion-cli.md) — depends on P10-002, P10-003
- [P10-007 — Judgment Benchmark Runner](p10-007-judgment-benchmark-runner.md) — depends on P10-005, P10-006
- [P10-008 — Regression Baseline](p10-008-regression-baseline.md) — depends on P10-007
- [P10-009 — Benchmark Report](p10-009-benchmark-report.md) — depends on P10-007, P10-008
- [P10-010 — Seed Dataset Pack](p10-010-seed-dataset-pack.md) — depends on P10-002, P10-003, P10-004
- [P10-011 — Verification Integration](p10-011-verification-integration.md) — depends on P10-007, P10-009, P10-010
- [P10-012 — P10 Release Evidence](p10-012-release-evidence.md) — depends on P10-001 through P10-011

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P10 closure.
