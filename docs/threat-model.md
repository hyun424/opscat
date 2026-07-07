# OpsCat Threat Model

## Assets

- Incident data and evidence snippets.
- Integration tokens and credentials.
- Action approval records.
- Customer service topology and runbooks.
- Agent prompts, tool outputs, and audit logs.
- Connector setup metadata and local secret lifecycle records.
- Workflow job, dead-letter, approval console, and self-observability state.

## Primary Risks

1. Agent executes an unsafe action.
2. Cross-tenant data leak.
3. Secret or PII leakage into LLM input, reports, API responses, audit logs, or metrics.
4. Compromised integration token performs unauthorized changes.
5. Prompt injection from logs/runbooks influences tool execution.
6. Duplicate webhook causes repeated action execution.
7. Night Autopilot performs a bad remediation while humans sleep.
8. Connector setup requests broad permissions before a user understands the risk.
9. Secret lifecycle views expose plaintext/ciphertext or encourage users to paste real tokens.
10. Incident import accepts raw provider envelopes without redaction/idempotency.
11. Worker CLI hides stuck/failed jobs instead of surfacing dead-letter operations.
12. Approval console implies safe browser mutation before auth/session work exists.
13. Self-observability leaks raw payloads, customer data, or cross-workspace counters.

## P5 OSS Surfaces

P5 adds or documents these public/local surfaces:

- connector setup and permission preview;
- local secret lifecycle metadata operations;
- incident import for Sentry/Datadog/Loki/generic fixture envelopes;
- worker CLI stats, drain, and dead-letter operations;
- approval console action previews without browser mutation forms;
- Night Autopilot policy and morning report evidence;
- self-observability `/metrics` counters;
- CI verification profiles and release evidence.

## Mitigations

- Deterministic policy engine gates every action.
- Capability grants are scoped by tenant, service, environment, and action.
- Dangerous actions are denied by default.
- Redaction runs before model input and report generation.
- Tool execution uses typed action registry, not arbitrary shell.
- Approval records and action states prevent hidden mutation.
- Post-checks and max-attempt limits bound Night Autopilot.
- Connector catalog exposes required roles, risk, approval, and secret names before setup.
- Secret list/read surfaces return metadata only, never plaintext or ciphertext.
- Incident import normalizes supported fixture providers and fails closed on unknown providers.
- Worker CLI exposes queue stats and dead-letter operations for local jobs.
- Approval console renders read-only previews and API instructions; auth remains deferred.
- Self-observability returns scoped numeric counters only.
- Self-hosted connector keeps raw logs inside customer infrastructure in future production designs.

## MVP Security Boundaries

The MVP is local/mock-only. Auth remains deferred. It must not claim real production safety until production authentication, tenant isolation, external secret management, connector deployment, CI/CD hardening, and operational monitoring are implemented and verified.

## P5 Security Review Link

See `docs/security-review-p5.md` for P5-specific Adversarial checks and Residual gaps across connector setup, secret lifecycle, incident import, worker CLI, approval console, Night Autopilot, and self-observability.

## P7 Reliability & Safety Lab Addendum

P7 adds replay, adversarial evals, confidence calibration, self-critique, blast radius, action simulation, incident memory, Night Autopilot v2, failure-mode reporting, and reliability dashboard metrics inside the local/mock boundary.

Additional threats:

- poisoned logs or runbook text influencing diagnosis;
- memory poisoning or a failed prior remediation being ignored;
- overconfident diagnosis with weak or conflicting evidence;
- action simulation gaps allowing unbounded effects;
- Night Autopilot v2 executing without confidence, rollback, low blast radius, and clean memory evidence.

Mitigations:

- deterministic replay/adversarial fixtures exercise prompt injection, duplicate/noisy alerts, ambiguous roots, stale markers, false positives, connector masking, and dangerous action attempts;
- confidence calibration and self-critique fail closed on sparse evidence, contradiction flags, and alternate hypotheses;
- blast radius and action simulation block unknown, prohibited, production, shell, cloud, database, and secret actions;
- incident memory failed-prior warnings block automation;
- auth remains deferred and P7 continues to avoid real provider mutation, real customer credentials, and unattended production operation claims.

## P8 AI Incident Responder War Room Addendum

P8 adds a war room, agent reliability score, runbook critique, human question generation, and report export evidence while keeping auth remains deferred and the local/mock boundary intact.

Additional threats:

- stale or poisoned incident memory influencing the war room narrative;
- over-trusting an agent reliability score instead of hard policy gates;
- prompt/log injection in war room text or runbook critique fields;
- accidental secret exposure in evidence or report export links;
- unsafe runbook improvement suggestions being mistaken for approved production procedure;
- UI copy implying production autonomy or unattended production operation.

Mitigations:

- `tests/test_p8_demo.py` checks that the operator-facing demo flow repeats the local/mock boundary and avoids mutation forms;
- `tests/test_p8_security_docs.py` locks the threat language, auth deferral, and no-secret-marker contract;
- `tests/test_p8_release_evidence.py` requires release evidence and final summary links before P8 closure;
- hard policy, typed mock actions, redaction, and approval-gated API instructions remain the enforcement layer.
