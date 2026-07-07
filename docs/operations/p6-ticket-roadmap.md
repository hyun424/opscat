# OpsCat P6 Ticket Roadmap — Beta-Grade Agentic Ops Loop

Status: planned
Owner: leader + team lanes for connector/platform/agent-safety/UI/eval/docs
Scope boundary: **Do not implement auth/OIDC/SSO/session login in P6**. Keep OpsCat local-first/open-source usable with the existing local-header/demo identity boundary unless the owner explicitly reopens auth.

## P6 objective

P6 turns the P5 OSS-usable product prototype into a beta-grade **agentic operations loop**. The goal is to make OpsCat behave less like a log summarizer and more like a risk-aware operator agent:

1. observe realistic operational signals;
2. correlate them into incidents;
3. produce evidence-backed root-cause candidates;
4. select a runbook;
5. score remediation risk;
6. execute only safe/dry-run actions or request approval;
7. verify recovery;
8. leave an auditable decision trace and evaluation evidence.

P6 must make the agentic claim testable. Every new decision capability needs deterministic policy guards, fixture/eval coverage, and clear evidence trails. LLM-style reasoning may be simulated or provider-abstracted, but safety decisions must not depend on an unverifiable prompt alone.

## P6 definition of done

P6 is complete when:

- a realistic fixture incident can flow through observe → correlate → diagnose → plan → risk-score → act/approval → verify → report;
- at least one connector has a deeper real-provider-shaped implementation path with health, pagination/rate-limit/error handling, and fixture fallback;
- incident correlation and root-cause ranking produce explainable confidence/evidence, not just summaries;
- the runbook planner can select and execute a bounded diagnostic/remediation plan from a registry;
- every remediation is classified as `auto_execute`, `approval_required`, `human_required`, or `blocked` with deterministic policy reasons;
- unsafe or production-like actions are blocked or approval-gated by tests;
- post-action verification records whether the system recovered, stayed degraded, or requires escalation;
- the operator console shows an incident timeline, evidence, risk decision, suggested actions, and verification result;
- an eval suite reports correlation, diagnosis, action-selection, risk-classification, unsafe-blocking, and recovery-verification scores;
- `bash scripts/verify.sh --profile full` passes;
- docs clearly state local/mock/beta boundaries and auth remains deferred.

## Explicit non-goals

P6 does **not** include:

- OIDC/SSO/login/session UI/password auth;
- production customer credential collection;
- unrestricted shell execution;
- unapproved production mutations;
- broad raw-log ingestion without redaction and sampling boundaries;
- real Kubernetes/infra writes by default;
- hosted multi-tenant SaaS operations.

## Ticket dependency graph

```text
P6-001 ─┬─> P6-002 ─┬─> P6-003 ─┬─> P6-004 ─┬─> P6-005 ─┬─> P6-006
        │           │           │           │           └─> P6-007
        │           │           │           └─> P6-008 ───> P6-009
        │           └───────────┴──────────────> P6-010
        └──────────────────────────────────────> P6-011
P6-006 + P6-007 + P6-009 + P6-010 + P6-011 ───> P6-012
P6-012 ───> P6-013
P6-013 ───> P6-014
```

Recommended execution mode: team lanes can run some tickets in parallel after P6-001 lands, but keep P6-002/P6-003/P6-004 sequential because they define the incident decision model used by later tickets.

## Ticket order

### P6-001 — Real-provider-shaped Sentry connector deepening

Goal: make one connector credible enough to represent real beta integration work while preserving fixture/local fallback.

Plan:
1. Deepen `app/connectors/sentry.py` with a provider-shaped client boundary for issue/event fetch, pagination, rate-limit handling, health checks, and normalized errors.
2. Keep default fixture mode and make real API calls opt-in via local secrets only.
3. Record connector call attempts and failures through existing connector/audit/observability paths.
4. Add docs for minimum Sentry permissions, fixture mode, and fail-closed behavior.

Acceptance tests:
- Connector health reports missing secret, invalid config, rate-limited, provider-error, and fixture-ok states distinctly.
- Fixture mode works without credentials and remains the default in quickstart/demo.
- Provider-shaped errors normalize without leaking token/config values.
- Pagination/rate-limit retry behavior is bounded and tested with mocked transport.
- Connector evals include Sentry setup/health/fetch failure cases.

Files likely touched:
- `app/connectors/sentry.py`
- `app/connectors/base.py`
- `app/services/connector_service.py`
- `app/services/secret_service.py`
- `tests/test_connector_contract.py`
- `tests/test_connector_evals.py`
- `scripts/run_connector_evals.py`
- `docs/connector-permissions.md`

### P6-002 — Incident correlation engine

Goal: group multiple normalized signals into one incident with explicit evidence and confidence.

Plan:
1. Add a correlation service that groups signals by workspace, service, environment, fingerprint, time window, deploy marker, severity, and provider references.
2. Persist or derive correlation evidence that can be shown in API/UI/report surfaces.
3. Add deterministic confidence scoring with clear reasons.
4. Ensure duplicate imports are idempotent and cross-workspace signals never merge.

Acceptance tests:
- Sentry-like, Datadog-like, and Loki-like fixture signals for the same outage produce one correlated incident.
- Same fingerprint across different workspaces/environments does not merge.
- Correlation output includes signals, evidence reasons, confidence, and rejected-neighbor explanations.
- Duplicate signal delivery does not inflate confidence or create duplicate incidents.

Files likely touched:
- new `app/services/correlation_service.py`
- `app/services/incident_service.py`
- `app/services/signal_normalizer.py`
- `app/models/incident.py`
- `app/models/evidence.py`
- `tests/test_incident_correlation.py`
- `tests/fixtures/signals/*.json`

### P6-003 — Root-cause candidate generator

Goal: turn correlated incident evidence into ranked root-cause hypotheses with evidence, counter-evidence, and confidence.

Plan:
1. Add a root-cause service that evaluates deploy proximity, error fingerprints, metric/log co-occurrence, recent config changes, and connector evidence.
2. Represent candidates as structured objects: hypothesis, confidence, evidence, counter-evidence, missing evidence, recommended next diagnostic.
3. Keep generation deterministic/provider-abstracted for tests; do not depend on live LLM calls for pass/fail behavior.
4. Redact all evidence snippets before persistence/rendering.

Acceptance tests:
- Recent-deploy regression fixture ranks deploy regression above generic traffic spike.
- Noisy unrelated logs appear as counter-evidence or rejected evidence, not as top causes.
- Candidate confidence is bounded and drops when required evidence is missing.
- Secret-bearing snippets are redacted in candidate evidence.

Files likely touched:
- new `app/services/root_cause_service.py`
- `app/services/correlation_service.py`
- `app/services/redaction.py`
- `app/models/evidence.py`
- `app/schemas/agent.py`
- `tests/test_root_cause_candidates.py`

### P6-004 — Runbook registry and planner

Goal: select a bounded operational runbook and produce a step plan from the incident/root-cause context.

Plan:
1. Add a runbook registry for known incident classes such as recent deploy regression, API 5xx spike, queue backlog, connector outage, and secret/config missing.
2. Add planner logic that maps incident evidence and root-cause candidates to diagnostic and remediation steps.
3. Represent each step with preconditions, required permission, risk hints, dry-run support, rollback expectation, and verification check.
4. Expose selected runbook and plan in API/operator report surfaces.

Acceptance tests:
- Recent-deploy regression selects a deploy/regression runbook.
- Unknown/low-confidence incident selects diagnostic-only runbook and refuses mutation.
- Every runbook action declares permission, risk hint, dry-run support, and verification check.
- Planner output is deterministic for fixture incidents.

Files likely touched:
- new `app/services/runbook_service.py`
- new `app/runbooks/*.yaml` or `app/runbooks/*.py`
- `app/services/root_cause_service.py`
- `app/services/action_service.py`
- `tests/test_runbook_planner.py`
- `docs/runbooks.md`

### P6-005 — Risk scoring engine v2 and action policy DSL

Goal: make automatic vs approval-required vs blocked decisions explainable and enforceable by deterministic policy.

Plan:
1. Extend `app/services/risk_engine.py` and/or `policy_engine.py` with a typed decision model: `auto_execute`, `approval_required`, `human_required`, `blocked`.
2. Add policy inputs for environment, blast radius, reversibility, data-loss risk, secret access, action type, confidence, night-autopilot mode, and prior failures.
3. Add a small local policy DSL or declarative rules table for safe defaults.
4. Ensure high-risk/protected/production-like actions fail closed even if an agent plan recommends them.

Acceptance tests:
- Low-risk fixture diagnostic can be `auto_execute` in local/mock mode.
- Production-like rollback/scale/destructive actions are `approval_required` or `blocked` according to policy.
- Missing confidence/evidence forces `human_required` or `blocked`.
- Policy reasons are human-readable and included in audit/evidence.
- Unsafe action blocking reaches 100% on eval fixtures.

Files likely touched:
- `app/services/risk_engine.py`
- `app/services/policy_engine.py`
- `app/models/policy.py`
- `app/services/action_service.py`
- `tests/test_policy_safety.py`
- `tests/test_risk_engine_v2.py`
- `docs/operations/safety-policy.md`

### P6-006 — Safe action runner with dry-run, rollback metadata, and audit

Goal: execute only approved/safe local actions while producing enough metadata for real operations review.

Plan:
1. Extend action execution attempts to include dry-run payload, preconditions, rollback metadata, post-checks, and policy decision ID.
2. Add action runners for safe local diagnostics and mock remediations: collect context, create issue/report, restart mock worker, rollback mock deploy, disable mock feature flag.
3. Enforce risk decision gates before execution.
4. Make failed actions visible through workflow/dead-letter/metrics paths.

Acceptance tests:
- `auto_execute` local diagnostic action runs and records pre/post evidence.
- `approval_required` action cannot execute without approval.
- `blocked` action never executes even if called directly at service/API level.
- Failed action creates an execution attempt, audit event, metric increment, and actionable error.
- Rollback metadata is present for every remediation-like action.

Files likely touched:
- `app/services/action_service.py`
- `app/services/execution_attempt_service.py`
- `app/tools/mock_actions.py`
- `app/tools/mock_context.py`
- `app/models/action.py`
- `app/models/evidence.py`
- `tests/test_action_execution_attempts.py`
- `tests/test_safe_action_runner.py`

### P6-007 — Post-action verification and recovery-state machine

Goal: verify whether an action improved, resolved, or worsened an incident and escalate when recovery is not proven.

Plan:
1. Add recovery verification checks tied to runbook steps: error-rate down, connector health restored, queue backlog reduced, action dry-run succeeded, or mock metric improved.
2. Extend incident state machine with `verifying`, `resolved`, `degraded`, `escalated`, and `needs_human` transitions where needed.
3. Record verification evidence and morning-report summaries.
4. Fail closed when verification evidence is missing.

Acceptance tests:
- Successful mock remediation transitions incident to resolved with verification evidence.
- Failed/no-evidence remediation transitions to degraded or needs_human and escalates.
- Verification checks are tenant/workspace scoped.
- Morning report includes verification outcomes and follow-ups.

Files likely touched:
- `app/services/state_machine.py`
- `app/services/action_service.py`
- `app/services/report_service.py`
- `app/models/incident.py`
- `app/models/timeline.py`
- `tests/test_post_action_verification.py`
- `tests/test_night_autopilot_policy.py`

### P6-008 — Agent decision trace and audit timeline

Goal: make every agent decision inspectable: what it saw, why it chose a plan, what policy allowed/blocked, and what happened after.

Plan:
1. Add a decision trace service/model or structured evidence conventions for observe/correlate/diagnose/plan/risk/act/verify stages.
2. Link trace entries to incident, actions, connector calls, runbook steps, and audit events.
3. Add redacted JSON and Markdown rendering for reports and operator UI.
4. Add tests that traces contain no secrets and include enough evidence for review.

Acceptance tests:
- A full fixture incident creates trace entries for all seven agentic stages.
- Trace entries include inputs, decision, confidence/reason, policy result, and output reference where relevant.
- Trace rendering redacts secrets and avoids raw log dumps.
- Cross-workspace trace reads are denied or hidden.

Files likely touched:
- new `app/services/decision_trace_service.py`
- `app/models/evidence.py`
- `app/models/timeline.py`
- `app/services/audit_service.py`
- `app/api/incidents.py`
- `tests/test_agent_decision_trace.py`
- `docs/agentic-loop.md`

### P6-009 — Operator console incident timeline and agentic action view

Goal: make the UI/demo visibly show OpsCat acting like an operations agent.

Plan:
1. Extend `/operator` surfaces to show incident timeline, correlated signals, root-cause candidates, selected runbook, risk decision, pending/executed actions, and verification result.
2. Keep browser mutation forms out of scope; use read-only views plus explicit API instructions for approval where needed.
3. Add status/risk badges and evidence links that are deterministic for tests.
4. Add browser-contract tests for the full agentic flow view.

Acceptance tests:
- Operator incident detail shows observe/correlate/diagnose/plan/risk/act/verify timeline.
- Root-cause candidates include confidence and evidence count.
- Risk badge and required approval state match service decision.
- No unsafe browser mutation form is introduced.
- Workspace scoping remains enforced.

Files likely touched:
- `app/api/operator.py`
- `app/api/incidents.py`
- `app/services/decision_trace_service.py`
- `tests/test_operator_dashboard.py`
- `tests/test_operator_dashboard_e2e.py`
- `docs/beta-walkthrough.md`

### P6-010 — Agentic eval suite v1

Goal: prove the agentic loop with repeatable scenario scoring rather than anecdotal demos.

Plan:
1. Add eval fixtures for at least 20 scenarios across deploy regression, traffic spike, connector outage, queue backlog, missing secret/config, noisy logs, duplicate alerts, and dangerous action attempts.
2. Score correlation accuracy, top root-cause match, runbook selection, risk classification, unsafe action blocking, and verification result.
3. Emit JSON/Markdown evidence with pass counts and failure explanations.
4. Include the eval profile in verification without requiring credentials.

Acceptance tests:
- Eval runner reports all required dimensions and exits non-zero on score regression.
- Unsafe action block rate is 100% for dangerous fixtures.
- Correlation/root-cause/runbook/risk thresholds are explicit in docs and tests.
- Eval outputs are generated in temp paths and not committed by default.

Files likely touched:
- `scripts/run_agentic_evals.py`
- `evals/agentic/*.json`
- `tests/test_agentic_eval_runner.py`
- `scripts/verify.sh`
- `docs/eval-report.md`
- `docs/release-evidence.md`

### P6-011 — One-command beta demo of the full agentic loop

Goal: let a reviewer run one command and watch OpsCat complete the observe-to-report loop locally.

Plan:
1. Extend `scripts/demo.py` or add `scripts/demo_agentic_loop.py` to seed a realistic fixture incident and run the P6 loop.
2. Print concise terminal output with incident ID, correlation result, top cause, selected runbook, risk decision, action result, verification result, and operator URL.
3. Keep it local/mock with no credentials.
4. Update README and beta walkthrough.

Acceptance tests:
- Demo command succeeds from a fresh local DB with no secrets.
- Output includes the seven agentic stages and artifact paths/URLs.
- Demo does not perform external calls or require production credentials.
- Demo is included in full verification or a documented beta-demo profile.

Files likely touched:
- `scripts/demo.py`
- new `scripts/demo_agentic_loop.py`
- `tests/test_agentic_demo.py`
- `README.md`
- `docs/beta-walkthrough.md`

### P6-012 — P6 safety/threat-model refresh

Goal: re-review the new agentic capabilities before claiming beta-grade autonomy.

Plan:
1. Update threat model for correlation, diagnosis, runbook planning, risk scoring, action execution, verification, decision traces, and connector deepening.
2. Add explicit abuse cases: prompt/log injection, malicious alert payloads, secret exfiltration via evidence, unsafe auto-remediation, cross-workspace merge, replay attacks, and eval overfitting.
3. Confirm auth remains deferred and document the production gap honestly.
4. Add regression tests for the highest-risk abuse cases if not already covered.

Acceptance tests:
- Security review lists P6 assets, trust boundaries, threats, mitigations, and remaining gaps.
- Tests cover malicious fixture payload redaction and unsafe action blocking.
- Docs do not claim production readiness or unattended production mutation safety.
- Auth remains deferred and explicitly out of scope.

Files likely touched:
- `docs/security-review-p6.md`
- `SECURITY.md`
- `tests/test_p6_security_review_docs.py`
- `tests/test_no_dangerous_production_mutations.py`

### P6-013 — P6 release evidence and roadmap update

Goal: package P6 as a portfolio/beta milestone with clear evidence.

Plan:
1. Update release evidence with P6 eval scores, demo command, verification command, screenshots/URL notes, and remaining gaps.
2. Update `ROADMAP.md` to mark P6 complete when the tickets are done and describe P7 safety/autonomy hardening candidates.
3. Add docs tests for evidence links and no-production-claims boundary.
4. Run full verification and record evidence.

Acceptance tests:
- `docs/release-evidence.md` links P6 eval/demo/security artifacts.
- `ROADMAP.md` points to this P6 roadmap and next P7 candidates.
- Docs tests pass and block claims of production readiness.
- `bash scripts/verify.sh --profile full` passes.

Files likely touched:
- `docs/release-evidence.md`
- `ROADMAP.md`
- `tests/test_p6_release_evidence.py`
- `CHANGELOG.md`

### P6-014 — Portfolio demo polish package

Goal: make the completed agentic loop obvious to recruiters/reviewers in under five minutes.

Plan:
1. Add a concise portfolio section to README: problem, agentic loop, architecture, safety model, eval results, and demo command.
2. Add architecture diagram source or Markdown diagram for observe/correlate/diagnose/plan/risk/act/verify.
3. Add demo transcript or screenshot placeholders that can be regenerated locally.
4. Add a short “Why this is agentic AI” explanation grounded in implemented code/evals.

Acceptance tests:
- README includes the seven-stage agentic loop and links to eval/release evidence.
- Portfolio docs do not overclaim production readiness.
- Demo transcript matches current command output or is marked generated.
- Docs profile passes.

Files likely touched:
- `README.md`
- `docs/agentic-loop.md`
- `docs/portfolio-demo.md`
- `docs/release-evidence.md`
- `tests/test_portfolio_evidence_docs.py`

## Team execution guidance

Recommended lanes once P6-001 is complete:

- **Connector lane**: P6-001 and connector eval updates.
- **Agent core lane**: P6-002 → P6-003 → P6-004 sequentially.
- **Safety/action lane**: P6-005 → P6-006 → P6-007 sequentially after planner contract stabilizes.
- **Evidence/UI lane**: P6-008 → P6-009 after decision trace data shape exists.
- **QA/eval lane**: P6-010 can start fixture design early, then wire assertions after P6-002/P6-005 contracts exist.
- **Docs/release lane**: P6-011/P6-012/P6-013/P6-014 near the end, with docs updated only after behavior is verified.

## Verification plan

Per ticket:

- write or update tests before/with implementation;
- run targeted pytest for changed behavior;
- run `uv run --no-sync --extra dev ruff check app tests scripts` and `uv run --no-sync --extra dev mypy app tests scripts` after non-doc code changes;
- update eval fixtures/reports when decision behavior changes;
- preserve local/mock safety boundaries.

Phase gate:

```bash
bash scripts/verify.sh --profile full
```

P6 is not complete until the full gate passes and release evidence documents the agentic loop end-to-end.
