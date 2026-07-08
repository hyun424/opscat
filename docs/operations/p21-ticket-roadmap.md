# OpsCat P21 Ticket Roadmap — Runtime Loop Runner and Operator Control Plane

## Scope

P21 turns the P20 one-shot closed-loop agent into a local/mock runtime that can keep processing incident candidates from a queue under an explicit operator approval profile. It does not add auth, real production connectors, or real remediation execution.

P21 is the runtime shell around the agent loop: enqueue incidents, process ticks, preserve state, expose pause/resume/abort controls, and enforce approval modes.

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real restart/rollback/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- Runtime may auto-run only read-only evidence collection and simulation; remediation execution remains disabled.
- P21 does not claim unattended production operation.

## Tickets

### P21-001 — Runtime state and queue schema

Define local/mock runtime state for queued, running, completed, paused, aborted, and approval_waiting incidents.

Acceptance:
- JSON-serializable runtime snapshot.
- Deterministic queue ordering.
- State records case ID, status, attempts, final route, and trace summary.

### P21-002 — Operator approval profile

Define explicit approval modes.

Acceptance:
- Supports locked, manual, enter_to_approve, auto_readonly, and auto_safe_mock.
- Each mode declares allowed and denied capabilities.
- Mutating production tools remain denied in all modes.

### P21-003 — Runtime tick processor

Process one queued incident per tick through P20 closed-loop response.

Acceptance:
- Tick is deterministic and side-effect limited to runtime state/output files.
- Closed-loop result is attached to the queue item.
- Approval-required/human-required routes move to approval_waiting unless profile is locked.

### P21-004 — Pause/resume/abort controls

Add local control operations.

Acceptance:
- Pause prevents processing.
- Resume allows processing.
- Abort marks active/pending item aborted with reason.

### P21-005 — Auto-approval policy gate

Apply approval profile to final routes and proposed actions.

Acceptance:
- Read-only evidence and simulation can auto-run.
- report.generate/timeline.add_note may be auto_safe_mock only.
- rollback/restart/shell/database/cloud/Kubernetes remain denied.

### P21-006 — Runtime report CLI

Add CLI to run a bounded number of ticks and write JSON/Markdown runtime reports.

Acceptance:
- Normal verification uses seed cases and mock provider.
- CLI supports --max-ticks, --approval-mode, --pause-after, output JSON/Markdown.
- Outputs stay in `/tmp` or verify temp dir.

### P21-007 — Verification integration

Add bounded runtime smoke to `scripts/verify.sh`.

Acceptance:
- Full verification remains offline/local/mock.
- Smoke proves queue, tick, approval profile, and report output.

### P21-008 — Release evidence

Document P21 and update roadmap/release evidence.

Acceptance:
- Final summary maps P21-001 through P21-008 to artifacts.
- `docs/release-evidence.md` includes P21 evidence and verification commands.
- Full verification passes before closure.

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P21 closure.
