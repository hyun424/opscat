# OpsCat P30 Ticket Roadmap — Controlled Auto-remediation Policy and Simulation

P30 defines the first portfolio-grade auto-remediation boundary: only low-risk, reversible, pre-approved simulated actions can auto-run; all production-changing actions remain approval-required or blocked.

Boundary: simulation/local-mock by default, no production mutation, no auth, no unrestricted shell, no unattended production-operation claim.

## Tickets

### P30-001 Remediation capability taxonomy

Acceptance:
- Classify read-only, notification, reversible maintenance, scaling, rollback, data mutation, shell, and destructive actions.
- Map every capability to auto/approval/blocked defaults.

### P30-002 Pre-approval policy profile

Acceptance:
- Represent user-selected auto-approval profiles without auth.
- Profiles are local config fixtures and default to conservative mode.

### P30-003 Simulation-first executor

Acceptance:
- Every proposed action creates a dry-run/simulation result before final route.
- Simulation cannot mutate production resources.

### P30-004 Auto-action guardrail

Acceptance:
- Auto-run only read-only/report/notification and explicitly safe reversible mock actions.
- Blocked capabilities cannot be downgraded by LLM output.

### P30-005 Incident-to-action drill

Acceptance:
- Run end-to-end telemetry -> judgment -> proposal -> simulation -> final decision drills.
- Score safety, lead time, and approval burden.

### P30-006 Operator control report

Acceptance:
- Show exactly what would be auto-approved, approval-required, and blocked.
- Explain policy reason and evidence for each decision.

### P30-007 Adversarial safety suite

Acceptance:
- Prompt injection, secret leakage, no-data restart, destructive cleanup, and privilege escalation attempts remain blocked.

### P30-008 Release evidence

Acceptance:
- Document that P30 is controlled simulation and not production unattended operation.
