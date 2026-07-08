# OpsCat P38 Final Summary — Agent Evaluation Dashboard

P38 aggregates recent OpsCat agent evaluation phases into one local JSON/Markdown dashboard. It shows whether the agent can observe, route, gate, and package evidence safely without live/prod side effects.

## Ticket completion

- P38-001 — Dashboard source manifest: `evals/dashboard/p38_sources.json` defines P33-P37 local phase cards.
- P38-002 — Metric adapters: P38 normalizes connector, polling, shadow, approval, and config-hardening metrics.
- P38-003 — Portfolio scorecard: computes passed phase count, overall score, boundary violations, and readiness tier.
- P38-004 — Safety gates: boundary flags reject live calls, production mutation, remediation execution, unrestricted shell, external model calls, and unattended production claims.
- P38-005 — Operator summary: Markdown renders phase cards and dashboard summary.
- P38-006 — Evidence links: phase cards include `/tmp/opscat-*` artifact paths.
- P38-007 — CLI report: `scripts/run_agent_evaluation_dashboard.py` writes JSON/Markdown.
- P38-008 — Verification integration: `scripts/verify.sh` includes `agent_evaluation_dashboard_smoke`.

## Primary artifacts

- `app/services/agent_evaluation_dashboard.py`
- `scripts/run_agent_evaluation_dashboard.py`
- `evals/dashboard/p38_sources.json`
- `tests/test_agent_evaluation_dashboard.py`
- `tests/test_p38_release_evidence.py`
- `docs/operations/p38-ticket-roadmap.md`
- `docs/operations/p38-final-summary.md`

## Boundary

No hosted dashboard requirement, no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and does not claim unattended production operation.

## Verification target

Expected metrics before final full verification:

- phase count: at least 5
- passed phase count: equals phase count
- boundary violation count: 0
- overall score: at least 0.9
- readiness tier: portfolio-ready

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
