# OpsCat P29 Ticket Roadmap — Telemetry-grounded Judgment Quality Evaluation

P29 evaluates whether OpsCat judgments improve when grounded in connector telemetry: root-cause candidates, missing-evidence requests, route choice, citation quality, and safety policy adherence.

Boundary: evaluation/local-mock by default, no default external model calls, no remediation execution, no production claims.

## Tickets

### P29-001 Telemetry judgment case schema

Acceptance:
- Combine telemetry snapshots, trend windows, expected risks, and expected routes.
- Cases include normal, degraded, adversarial, and missing-data inputs.

### P29-002 Grounded context builder

Acceptance:
- Build LLM/judgment context from telemetry evidence IDs.
- Redact secrets and mark adversarial event text as untrusted evidence.

### P29-003 Judgment evaluator

Acceptance:
- Score risk identification, route, hypothesis, evidence citation, and unsafe-action behavior.
- Measure delta against non-telemetry baseline.

### P29-004 Scenario expansion

Acceptance:
- Add DB pool, disk full, Sentry spike, queue lag, rate limit, and prompt injection scenarios.
- Include false-positive and insufficient-evidence scenarios.

### P29-005 CLI report

Acceptance:
- Write JSON/Markdown quality reports with score breakdown.
- Expose pass/fail gates for portfolio evidence.

### P29-006 NVIDIA opt-in evaluation hook

Acceptance:
- Keep mock default.
- Allow explicit provider selection without printing or committing keys.

### P29-007 Verification integration

Acceptance:
- Mock evaluation smoke runs in full verification.
- External provider evaluation remains opt-in and outside default CI.

### P29-008 Release evidence

Acceptance:
- Document quality score, limitations, and next improvement targets.
