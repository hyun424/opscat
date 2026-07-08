# OpsCat P40 Ticket Roadmap — Production-readiness Milestone Bundle

P40 packages P33-P39 evidence into one production-readiness milestone bundle. It explicitly separates local portfolio readiness from unattended production-operation readiness.

## Tickets

- P40-001 — Readiness source manifest: define local evidence sources from P33-P39.
- P40-002 — Gate model: define safety, evidence, connector, approval, config, dashboard, learning, and verification gates.
- P40-003 — Readiness evaluator: compute passed gates, boundary violations, production blockers, and readiness decision.
- P40-004 — Production blocker register: document why unattended production operation is not claimed yet.
- P40-005 — Portfolio summary: generate recruiter/portfolio-ready summary grounded in verified local artifacts.
- P40-006 — Evidence bundle: link generated `/tmp/opscat-*` reports and source docs.
- P40-007 — CLI report: `scripts/run_production_readiness_milestone.py` writes JSON/Markdown reports.
- P40-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- does not claim unattended production operation
- does not enable production autopilot
- no auth/session work
- no live API calls
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls

## Acceptance criteria

- At least eight readiness gates are evaluated.
- All gates pass for local/portfolio readiness.
- Boundary violation count is 0.
- Production blocker count is at least 1 and explicitly documented.
- Readiness decision is `local-portfolio-ready`.
- Production autopilot ready is false.
- Full verification profile includes `production_readiness_milestone_smoke`.
