# OpsCat P22 Ticket Roadmap — Night-shift Runtime Drill and SLA Scoring

P22 proves the P21 runtime loop can be evaluated like a night-shift incident operator. It runs batches of local/mock incidents through the runtime, scores coverage/SLA/safety/escalation behavior, emits evidence, and keeps all boundaries no-auth/local-mock.

Boundary: no login/session UI, no production credentials, no hosted SaaS operation, no Kubernetes/cloud/database mutation, no unrestricted shell, no default external model/API calls, no remediation execution, and no unattended production-operation claim.

## Tickets

### P22-001 Drill scenario schema
Define a compact drill scenario schema wrapping existing judgment cases with expected runtime status, route class, SLA target, and safety constraints.

Acceptance:
- Scenarios can be loaded from JSON.
- Existing judgment cases can be converted into scenarios.
- Schema redacts user-controlled text in reports.

### P22-002 Night-shift drill runner
Run N scenarios through P21 runtime with deterministic ticks and approval profile selection.

Acceptance:
- Runner produces per-scenario runtime status, final route, attempts, and trace summary.
- Runner records runtime boundary flags.
- Runner never executes remediation.

### P22-003 SLA and safety scoring
Score processed ratio, queue drain ratio, blocked unsafe ratio, approval waiting ratio, unexpected completion count, and SLA pass rate.

Acceptance:
- Safety violations are explicit and fail the score.
- Auto-readonly mode should not complete remediation-like cases.
- Reports are deterministic from fixtures.

### P22-004 Drill report CLI
Add a CLI that runs a drill and writes JSON/Markdown reports.

Acceptance:
- CLI supports cases path, max-cases, approval-mode, max-ticks, output JSON/Markdown.
- Markdown includes score summary, scenarios, and boundary.

### P22-005 Verification integration
Add P22 smoke to `scripts/verify.sh` and docs contract tests.

Acceptance:
- Full verification runs the P22 drill smoke offline.
- Latest report is copied to `/tmp/opscat-night-drill-latest.md`.

### P22-006 Release evidence
Update roadmap/release evidence/final summary with verified outputs.

Acceptance:
- P22 final summary exists.
- `docs/release-evidence.md` includes P22 evidence.
- Roadmap marks P22 implemented after verification.
