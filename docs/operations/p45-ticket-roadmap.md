# OpsCat P45 Ticket Roadmap — Evidence-Grounded Judgment Contract

P45 introduces a mandatory evidence-grounded judgment contract. Every incident judgment must carry support, counter-evidence, missing evidence, calibrated confidence, and an action boundary.

## Tickets

- P45-001 — Judgment contract schema: define claim, supporting evidence, counter evidence, missing evidence, confidence, uncertainty, and action boundary.
- P45-002 — Contract validator: fail judgments missing evidence, confidence, or safe action gates.
- P45-003 — Conservative routing: require approval/blocking when confidence is low or evidence is incomplete.
- P45-004 — Scenario fixture: cover deploy regression, DB saturation, external dependency, traffic spike, and ambiguous cases.
- P45-005 — Scorecard: report valid judgments, grounded ratio, conservative-routing ratio, and violations.
- P45-006 — CLI report: emit JSON/Markdown evidence contract reports.
- P45-007 — Verification integration: add offline smoke to `scripts/verify.sh`.
- P45-008 — Release evidence: document metrics and boundaries.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.
