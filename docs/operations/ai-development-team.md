# OpsCat AI Development Team

OpsCat is developed by an autonomous AI team with a dedicated planning lane. The goal is to move from a local/mock MVP to a production-grade human-on-exception operations agent.

## Team roles

- **Lead Orchestrator** — integration, prioritization, release gate, final verification.
- **Planning Agent** — PRD, roadmap, acceptance criteria, task graph, replanning.
- **Architect Agent** — production architecture, boundaries, sequencing, ADRs.
- **Backend/Platform Agent** — API, persistence, workflows, connectors, policy/action services.
- **Frontend/Product Agent** — dashboard, approval console, incident timeline, policy UX.
- **Security Agent** — authz, secrets, tenant isolation, redaction, dangerous-action policy.
- **QA/Eval Agent** — regression gates, golden evals, no-silent-failure invariants, e2e/load/soak.
- **Docs/Portfolio Agent** — truthful product docs, onboarding, portfolio narrative.

## Core rule

AI can autonomously plan, implement, test, refactor, document, and commit local changes. Production-impacting real-world actions remain disabled until explicitly authorized and protected by policy, audit, verification, rollback, and tenant/auth/secret gates.

## Operating loop

1. Plan or update task graph.
2. Implement one vertical slice.
3. Add tests/evals for changed behavior.
4. Run release gate.
5. Security-review changed trust boundaries.
6. Update docs and known gaps.
7. Commit with Lore protocol.
8. Replan next highest-leverage slice.

## Current direction

1. **M1 foundation:** release gate, migrations, auth identity, service-layer tenancy, audit log.
2. **M2 connector platform:** typed connectors, capability registry, encrypted secrets, fake connector contract tests, read-only Sentry-style connector.
3. **M3 operator surface:** dashboard, incident inbox, timeline, approval console, policy editor.
4. **M4 reliability:** 50+ evals, confidence scoring, runbook matching, no-silent-failure invariants, connector failure matrix.
5. **M5 paid beta candidate:** low-risk real Slack/GitHub/Sentry paths, background workers, observability, deployment, security review.

Canonical plan: [`production-ai-team-plan.md`](production-ai-team-plan.md).
