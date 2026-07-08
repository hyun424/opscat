# OpsCat P51 Ticket Roadmap — Operator Judgment Benchmark v2

Goal: measure whether the operator agent is actually good at incident judgment before investing further in UI or live-product integration.

## Tickets

- P51-001 — Benchmark fixture: representative operator incidents with labels for detection, root cause, route, re-ranking, and recovery verification.
- P51-002 — Scoring model: compute detection recall, top-1 hypothesis accuracy, evidence quality, route accuracy, re-ranking success, and recovery verification coverage.
- P51-003 — Failure taxonomy: classify misses into detection, root-cause, evidence, route, re-ranking, and recovery-verification failure buckets.
- P51-004 — Safety metrics: track unsafe auto-execute, production execution, and live-call counts as hard-zero metrics.
- P51-005 — Benchmark report: emit JSON/Markdown with case cards, scorecard, thresholds, and improvement targets.
- P51-006 — CLI runner: produce reproducible `/tmp` benchmark artifacts.
- P51-007 — Verification integration: wire a full-profile smoke and docs contract test.
- P51-008 — Release evidence: document benchmark scope, metrics, verification, and remaining production blockers.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
