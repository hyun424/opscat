# OpsCat P36 Ticket Roadmap — Approval Control Plane

P36 turns P35 shadow decisions into explicit approval-control-plane routes. It is not auth, not execution, and not production autopilot. It decides whether a proposed operator action would be auto-allowed, approval-required, or blocked under named local profiles.

## Tickets

- P36-001 — Approval profile manifest: define `manual`, `auto_read_only`, and `night_watch` local profiles with allowed auto routes, approval-required routes, blocked reasons, and maximum risk.
- P36-002 — Shadow decision intake: load P35 shadow cases and convert proposed/blocked actions into approval-control-plane requests.
- P36-003 — Route evaluator: emit `auto_allowed`, `approval_required`, or `blocked` with reasons and evidence links for every request.
- P36-004 — Auto-approval boundary: auto-allow only read-only/report/notification-draft actions under compatible profiles; never auto-allow mutation, shell, untrusted evidence, or production actions.
- P36-005 — Night-watch escalation: night profile may auto-allow low-risk evidence/report work but escalates ambiguous or medium/high-risk mitigation.
- P36-006 — Safety scorecard: report auto rate, approval burden, blocked safety count, unsafe auto count, profile coverage, and execution count.
- P36-007 — CLI report: `scripts/run_approval_control_plane.py` writes JSON/Markdown reports for operators.
- P36-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- no auth/session/user management work
- no live API calls
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls
- no unattended production-operation claim

## Acceptance criteria

- At least three approval profiles are evaluated.
- Every P35 shadow decision produces at least one approval-control-plane route.
- Unsafe auto action count is 0.
- Execution count is 0.
- Untrusted or shell-like actions are blocked.
- Read-only/report actions can be auto-allowed only by compatible profiles.
- Full verification profile includes `approval_control_plane_smoke`.
