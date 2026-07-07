# OpsCat P7 Ticket Roadmap — Agent Reliability & Safety Lab

Owner: leader + team lanes for reliability/evals/safety/memory/night-autopilot/docs
Scope boundary: **Do not implement auth/OIDC/SSO/session login in P7 unless explicitly reopened by the owner.** P7 improves agent reliability and safety inside the existing local/mock OSS boundary.

## P7 objective

P7 turns the P6 beta-grade agentic loop into a reliability-focused operator agent. The goal is not monetization or breadth. The goal is trustworthiness:

```text
observe → replay/evaluate → correlate → diagnose → self-critique → simulate → risk/blast-radius → act/approval → verify → remember/report
```

P7 must make these claims testable:

- OpsCat can replay deterministic incident scenarios and measure behavior.
- OpsCat knows when confidence is not calibrated enough to act.
- OpsCat critiques its own diagnosis before proposing action.
- OpsCat calculates blast radius and rollback availability before execution.
- OpsCat simulates actions before execution.
- OpsCat remembers similar incidents and prior outcomes.
- Night Autopilot uses reliability gates, not just a static allowlist.
- Reliability dashboards/reports expose both successes and failure modes.

## P7 definition of done

P7 is complete when:

- replay fixtures cover at least 30 deterministic scenarios, including adversarial/noisy cases;
- confidence calibration produces bucketed reliability metrics and fail-closed thresholds;
- action proposals include self-critique, blast-radius, rollback, and simulation evidence;
- Night Autopilot v2 only auto-executes high-confidence, low-blast-radius, reversible actions;
- incident memory can retrieve similar historical incidents and warn about failed past remediations;
- reliability dashboard/report surfaces accuracy, false-positive, blocked-dangerous-action, escalation, and auto-remediation success metrics;
- `bash scripts/verify.sh --profile full` passes and includes P7 eval checks;
- release evidence and docs clearly state remaining production gaps.

## Non-goals

P7 does **not** include:

- OIDC/SSO/login/session UI/password auth;
- customer billing, plans, or payment;
- unrestricted shell/Kubernetes/cloud/database mutation;
- real customer credential collection;
- hosted multi-tenant SaaS operations;
- claims of unattended production operation.

## Dependency graph

```text
P7-001 ─┬─> P7-002 ─┬─> P7-003 ─┬─> P7-004 ─┬─> P7-005 ─┬─> P7-006
        │           │           │           │           └─> P7-008
        │           │           │           └─> P7-009
        │           └───────────┴──────────────────────> P7-010
        └───────────────────────────────> P7-007 ──────> P7-008
P7-003 + P7-004 + P7-005 + P7-006 + P7-007 + P7-008 ───> P7-011
P7-011 ───> P7-012
```

## Tickets

### P7-001 — Incident Replay Harness

Goal: provide a deterministic replay engine that can run realistic incidents through the agent loop without live provider dependencies.

Requirements:
1. Add replay scenario models/fixtures for incident inputs, expected route, expected action safety, and expected verification outcome.
2. Add a replay runner that executes scenarios against service-layer components without external calls.
3. Record per-scenario evidence: observed signals, diagnosis, policy route, action proposal, verification, and report.
4. Ensure fixture failures are fail-closed and never call real providers.

Acceptance:
- At least 30 replay scenarios can be loaded.
- Replay runner returns structured PASS/FAIL metrics.
- No scenario requires auth, external credentials, or production mutation.

Likely files:
- `app/services/replay_service.py`
- `evals/replay/*.json`
- `scripts/run_replay_evals.py`
- `tests/test_replay_harness.py`

### P7-002 — Adversarial Eval Suite

Goal: test whether OpsCat resists misleading/noisy incidents and dangerous action prompts.

Requirements:
1. Add adversarial scenarios for duplicate alerts, noisy logs, prompt/log injection, ambiguous root causes, stale deploy markers, false-positive metric spikes, connector outage masking, and dangerous action attempts.
2. Score blocked dangerous actions, escalated ambiguity, and false-positive suppression separately.
3. Add eval summary markdown/json outputs.

Acceptance:
- At least 12 adversarial scenarios exist.
- Unsafe/destructive suggestions are blocked 100% in fixture evals.
- Ambiguous scenarios escalate instead of auto-remediating.

Likely files:
- `evals/replay/adversarial/*.json`
- `scripts/run_replay_evals.py`
- `tests/test_adversarial_replay_evals.py`

### P7-003 — Confidence Calibration

Goal: make confidence operationally meaningful rather than decorative.

Requirements:
1. Add bucketed calibration metrics for confidence ranges.
2. Compare predicted confidence with expected replay outcome correctness.
3. Produce thresholds for auto-action eligibility.
4. Fail closed when high confidence is unsupported by evidence count, conflicting signals, or known ambiguity.

Acceptance:
- Calibration report includes bucket accuracy, overconfidence count, underconfidence count, and recommended thresholds.
- Auto-action gate can reject overconfident but weak-evidence scenarios.

Likely files:
- `app/services/confidence_calibration.py`
- `tests/test_confidence_calibration.py`
- `scripts/run_replay_evals.py`

### P7-004 — Self-Critique Gate Before Action

Goal: force the agent to challenge its own diagnosis before proposing action.

Requirements:
1. Add deterministic self-critique service that records missing evidence, alternate causes, contradiction flags, and action-risk objections.
2. Integrate critique between diagnosis and risk/action proposal.
3. Escalate or require approval if critique finds high ambiguity or insufficient evidence.
4. Add decision trace entries for critique.

Acceptance:
- Agent trace contains a `critique` stage before `risk`/`act`.
- Weak evidence or conflicting root causes prevent automatic action.

Likely files:
- `app/services/self_critique_service.py`
- `app/agent/loop.py`
- `app/services/decision_trace_service.py`
- `tests/test_self_critique_gate.py`

### P7-005 — Blast Radius Engine

Goal: classify every action by impact scope, rollback availability, and approval requirements.

Requirements:
1. Add blast-radius model for local, service, workspace, tenant, global, unknown, and prohibited scopes.
2. Map action metadata and payload to blast radius.
3. Block unknown/unbounded blast radius.
4. Expose blast-radius evidence in policy results, action proposals, audit, and decision trace.

Acceptance:
- Unknown shell/cloud/database actions are blocked.
- Low-risk auto actions require local/service-limited blast radius and rollback availability.

Likely files:
- `app/services/blast_radius.py`
- `app/services/policy_engine.py`
- `app/models/action.py`
- `tests/test_blast_radius_engine.py`

### P7-006 — Action Simulator

Goal: simulate an action before it executes and use the result as a safety precondition.

Requirements:
1. Add simulator for mock actions: report generation, ticket creation, rollback PR draft, worker restart, and verification-only actions.
2. Produce predicted touched resources, expected effect, rollback path, precondition gaps, and residual risks.
3. Block or escalate when simulation cannot produce a bounded result.
4. Link simulation output to decision trace and action metadata.

Acceptance:
- Action execution path refuses actions without a successful simulation record unless explicitly read-only.
- Simulation appears in reports/evals.

Likely files:
- `app/services/action_simulator.py`
- `app/services/action_service.py`
- `app/tools/mock_actions.py`
- `tests/test_action_simulator.py`

### P7-007 — Incident Memory and Similarity Search

Goal: make OpsCat learn from previous local/mock incidents without external vector infrastructure.

Requirements:
1. Add deterministic in-process/local incident memory records from resolved/escalated incidents.
2. Implement similarity over service, environment, fingerprint, root cause, runbook, action type, and outcome.
3. Return prior successful and failed remediations.
4. Inject memory evidence into diagnosis/runbook planning and reports.

Acceptance:
- Similar incidents are retrieved with reasons and similarity scores.
- Previously failed actions become warnings in critique/policy.

Likely files:
- `app/services/incident_memory.py`
- `app/models/evidence.py` or existing incident/timeline models
- `tests/test_incident_memory.py`

### P7-008 — Night Autopilot Policy v2

Goal: make quiet-hours automation depend on confidence, blast radius, simulation, and memory, not just allowlisted action type.

Requirements:
1. Add v2 policy gate: high confidence, low blast radius, reversible, simulation pass, no failed-memory warning, allowed service/environment, max attempts.
2. Produce morning reports with action rationale, blocked action rationale, and follow-up queue.
3. Keep production/destructive actions blocked.

Acceptance:
- Night Autopilot auto-executes only low-risk reversible scenarios.
- Ambiguous or failed-simulation scenarios escalate with actionable morning report.

Likely files:
- `app/services/night_autopilot.py`
- `app/api/night_autopilot.py`
- `tests/test_night_autopilot_policy_v2.py`

### P7-009 — Failure Mode Report

Goal: require OpsCat to state what it might be wrong about.

Requirements:
1. Add report section for uncertainty, alternate hypotheses, missing evidence, blocked actions, and escalation reasons.
2. Include failure-mode summary in decision trace and operator console.
3. Ensure no terminal path is silent.

Acceptance:
- Every resolved/escalated/waiting incident report contains failure-mode analysis.
- Tests verify low-confidence and blocked-action cases include human-readable failure modes.

Likely files:
- `app/services/report_service.py`
- `app/services/decision_trace_service.py`
- `app/api/operator.py`
- `tests/test_failure_mode_report.py`

### P7-010 — Reliability Dashboard Metrics

Goal: expose service-quality metrics for agent reliability.

Requirements:
1. Add metrics aggregation over replay/eval outputs and local incident outcomes.
2. Report auto-action success, escalation rate, blocked dangerous actions, false-positive suppression, overconfidence, and verification failure rate.
3. Add read-only operator dashboard section or API endpoint.

Acceptance:
- Dashboard API/read model returns deterministic metrics from fixtures/eval outputs.
- Metrics are linked from release evidence.

Likely files:
- `app/services/reliability_dashboard.py`
- `app/api/operator.py`
- `tests/test_reliability_dashboard.py`

### P7-011 — P7 Safety/Threat-Model Refresh

Goal: document new safety assets and trust boundaries.

Requirements:
1. Update threat model for replay, adversarial evals, calibration, critique, simulation, memory, and night autopilot v2.
2. Document abuse cases: poisoned logs, malicious runbook text, memory poisoning, overconfident diagnosis, and unsafe automation.
3. Keep auth deferred explicitly.

Acceptance:
- Security docs list P7 assets, threats, mitigations, and remaining gaps.

Likely files:
- `docs/security-review-p7.md`
- `docs/threat-model.md`
- `tests/test_p7_security_review_docs.py`

### P7-012 — P7 Release Evidence and Portfolio Update

Goal: close P7 with durable verification evidence.

Requirements:
1. Add final P7 summary with tickets, commits, verification, and remaining gaps.
2. Update release evidence and roadmap.
3. Add reviewer commands for replay/eval/dashboard/demo.

Acceptance:
- `bash scripts/verify.sh --profile full` passes.
- Release docs distinguish local/mock reliability evidence from production unattended-ops claims.

Likely files:
- `docs/operations/p7-final-summary.md`
- `docs/release-evidence.md`
- `ROADMAP.md`
- `tests/test_p7_release_evidence.py`
