# OpsCat P20 Ticket Roadmap — Closed-loop Agentic Incident Response

## Scope

P20 connects the previous pieces into a closed-loop incident response agent. The agent observes a judgment case, runs an initial LLM-shaped judgment, detects weak or missing evidence, executes only safe read-only local/mock diagnostic tools, rebuilds context, re-judges, proposes bounded actions, simulates them, and returns an escalation/approval decision with an auditable trace.

P20 is the first phase where OpsCat behaves like a true incident-response agent loop rather than a sequence of separate evaluators.

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real restart/rollback/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- Read-only diagnostic tools are allowed only through deterministic mock handlers.
- Proposed actions are simulated and policy-routed; they are not executed.
- P20 does not claim unattended production operation.

## Quality Questions

P20 answers:

1. Can the agent notice that the first judgment is under-evidenced?
2. Can it fetch more safe read-only evidence without human intervention?
3. Does the second judgment improve or at least avoid unsafe auto-action?
4. Does it simulate proposed actions before approval/escalation?
5. Does the trace explain every step and safety decision?

## Tickets

### P20-001 — Loop state and trace schema

Define a deterministic response-loop result schema.

Acceptance:
- Trace includes observe, initial_judgment, evidence_gap, evidence_fetch, revised_judgment, action_proposal, simulation, final_decision.
- Result is JSON-serializable and redacted.
- Boundary says no action execution.

### P20-002 — Initial judgment adapter

Run existing P18B/P16 judgment evaluation as the first loop judgment.

Acceptance:
- Uses mock provider by default.
- Preserves raw provider route, calibrated route, scores, and failure taxonomy.
- Does not call external model APIs in normal verification.

### P20-003 — Missing evidence executor

Convert P19 missing-evidence plans into read-only local/mock evidence.

Acceptance:
- Supports mock.search_logs, mock.query_metrics, mock.fetch_trace_context, mock.get_service_health, mock.get_recent_deploys, mock.get_error_context.
- Blocks restart, rollback, shell, database, cloud, Kubernetes, and unknown tools.
- Records why each tool ran.

### P20-004 — Revised judgment pass

Rebuild a case with fetched evidence and re-run judgment.

Acceptance:
- Revised judgment includes fetched evidence IDs.
- Loop records score delta and route delta.
- If evidence remains insufficient, final decision is human_required.

### P20-005 — Action proposal and policy routing

Propose only bounded local/mock actions from the revised route and evidence.

Acceptance:
- Read-only evidence collection never becomes remediation.
- Production restart/rollback/shell/database/cloud/Kubernetes actions remain blocked.
- Approval/human route is preserved for risky or ambiguous incidents.

### P20-006 — Simulation before approval

Dry-run proposed actions through the existing simulator before approval/escalation.

Acceptance:
- Every proposed action has simulation output.
- Simulation failures force human_required or blocked.
- No action execution occurs.

### P20-007 — Loop CLI and verification smoke

Add a CLI that runs the closed loop on a judgment case.

Acceptance:
- CLI writes JSON/Markdown reports.
- Normal verification runs mock/offline smoke.
- Outputs stay in `/tmp` or verify temp dir.

### P20-008 — Release evidence

Document P20 and update roadmap/release evidence.

Acceptance:
- Final summary maps P20-001 through P20-008 to artifacts.
- `docs/release-evidence.md` includes P20 evidence and verification commands.
- Full verification passes before closure.

## Execution Order

1. P20-001 Loop state and trace schema
2. P20-002 Initial judgment adapter
3. P20-003 Missing evidence executor
4. P20-004 Revised judgment pass
5. P20-005 Action proposal and policy routing
6. P20-006 Simulation before approval
7. P20-007 Loop CLI and verification smoke
8. P20-008 Release evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P20 closure.
