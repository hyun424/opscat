# OpsCat P35 Ticket Roadmap — Incident Shadow Mode

P35 adds incident shadow mode: OpsCat observes read-only telemetry and records what it would diagnose, escalate, approve, block, and report without executing remediation. Boundary: no auth feature work, no live API calls by default, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Tickets

- P35-001 — Shadow case manifest: define incidents linked to P34 polling evidence and expected shadow routes.
- P35-002 — Observation snapshot: ingest P34 read-only polling output into each shadow case.
- P35-003 — Shadow decision engine: produce diagnosis, route, proposed actions, and evidence links without execution.
- P35-004 — Safety invariant: execution count must remain 0 and unsafe actions must be blocked in shadow decisions.
- P35-005 — Shadow scorecard: emit expected route match, evidence link rate, shadow coverage, and execution count.
- P35-006 — Operator shadow report: generate handoff-ready JSON/Markdown for review.
- P35-007 — Verification integration: add P35 smoke to `scripts/verify.sh` and docs contract tests.
- P35-008 — Release evidence: record P35 artifacts, metrics, and safety boundary.

## Acceptance criteria

- Evaluates at least four shadow cases.
- Expected route match rate is 1.0.
- Evidence link rate is 1.0.
- Execution count is 0.
- Unsafe shadow action count is 0.
- JSON and Markdown reports are generated.
