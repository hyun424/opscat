# OpsCat P7 Security Review — Agent Reliability & Safety Lab

P7 remains **local/mock** and keeps **auth deferred**. It does not add OIDC, SSO, session login, browser mutation forms, real customer credentials, real provider writes, or unattended production operation claims.

## New P7 safety assets

- Deterministic replay harness and adversarial fixture corpus in `evals/replay/`.
- Confidence calibration buckets and fail-closed auto-action threshold guidance.
- Self-critique gate before action proposal.
- Blast-radius classification for local, service, workspace, tenant, global, unknown, and prohibited scopes.
- Local action simulator for mock report, ticket, rollback-PR, worker-restart, and verification actions.
- In-process incident memory with similar-incident warnings for previously failed remediations.
- Night Autopilot v2 reliability gates: confidence, bounded blast radius, reversibility, simulation pass, and memory warnings.
- Failure-mode report section and reliability dashboard metrics.

## Abuse cases and mitigations

| Abuse case | P7 mitigation |
| --- | --- |
| Poisoned logs or malicious runbook text | Replay/adversarial fixtures include prompt/log injection; unsafe action proposals must be blocked or escalated. |
| Memory poisoning | Incident memory is local/in-process, deterministic, and advisory only; failed-memory warnings can only make policy stricter. |
| Overconfident diagnosis | Calibration flags overconfidence and self-critique requires supporting evidence before auto-action. |
| Unsafe automation | Blast-radius engine blocks unknown/prohibited scopes; simulator must pass before mutation execution. |
| Night Autopilot runaway | V2 gate requires high confidence, low blast radius, rollback availability, simulation pass, no failed-memory warning, and max attempts. |

## Residual gaps

- Auth remains deferred; local header identity is still the demo boundary.
- No production tenant isolation, hosted secrets, real connector OAuth, or external vector memory is implemented in P7.
- Replay evidence is deterministic local/mock evidence, not proof of unattended production safety.
- Human approval remains required for medium/high-risk or ambiguous paths.
