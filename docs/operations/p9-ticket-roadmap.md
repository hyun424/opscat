# OpsCat P9 Ticket Roadmap — Autonomous Incident Commander

## Requirements Summary

P9 turns the P8 AI Incident Responder War Room into an **Autonomous Incident Commander**. P8 made incident state, evidence, reliability, runbook critique, questions, and reports visible. P9 should make OpsCat plan and govern a multi-step response loop: observe, diagnose, plan, simulate, gate, act locally/mock when safe, verify recovery, learn, and report.

Boundary remains unchanged unless explicitly reopened by the owner:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, or customer credentials;
- no hosted SaaS claims or unattended production-operation claims;
- automatic actions remain local/mock, allowlisted, policy-gated, simulated, audited, reversible, and test-backed.

## P9 Goal

Build a credible **AI Incident Commander** layer where OpsCat can:

1. construct a multi-step incident response plan;
2. calculate whether the agent is ready for autonomous local/mock execution;
3. connect evidence, hypotheses, runbooks, actions, and verification as an evidence graph;
4. verify recovery after action with stronger post-checks;
5. learn from prior outcomes and human overrides;
6. run replay/chaos tournaments that score commander quality;
7. expose the commander loop in the operator UI and release evidence.

## P9 Tickets

### P9-001 — Incident Commander Loop

**Outcome:** A deterministic service that orchestrates the P9 commander lifecycle without external side effects.

**Acceptance criteria:**

- Commander loop outputs stages: observe, diagnose, plan, simulate, gate, act_or_escalate, verify, learn, report.
- Every stage includes input evidence, output decision, confidence, blockers, and next step.
- Loop is pure/local by default and never calls provider/network/shell surfaces.
- Existing P8 war-room output can embed commander status.

### P9-002 — Multi-step Response Planner

**Outcome:** Generate ordered response plans instead of one-off action recommendations.

**Acceptance criteria:**

- Planner emits steps with type, goal, preconditions, required evidence, risk, expected output, rollback expectation, and verification check.
- Plans can represent diagnostic-only, human-required, and safe local/mock action paths.
- High-risk or unknown-blast-radius plans must stop at human-required gates.

### P9-003 — Autonomy Readiness Score

**Outcome:** Decide if OpsCat is ready to proceed autonomously, needs approval, or must stop.

**Acceptance criteria:**

- Score decomposes evidence sufficiency, confidence, blast radius, reversibility, simulation, policy, memory, and verification readiness.
- Hard safety gates cannot be overridden by high score.
- Output includes blockers, required human answers, and allowed next route.

### P9-004 — Evidence Graph Model

**Outcome:** Build a graph connecting alert signals, evidence, hypotheses, runbooks, actions, simulations, verification, and memory.

**Acceptance criteria:**

- Graph has stable node/edge schema and deterministic ordering.
- Each hypothesis/action has traceable support and counter-evidence.
- War room and commander report can render graph summaries.

### P9-005 — Recovery Verifier v2

**Outcome:** Strengthen post-action verification so resolved means actually recovered under local/mock checks.

**Acceptance criteria:**

- Verifier checks metrics/logs/state/timeline evidence depending on scenario.
- False recovery and partial recovery produce escalated or monitoring states.
- Verification result feeds commander loop, readiness score, report, and memory.

### P9-006 — Learning Loop from Prior Outcomes

**Outcome:** Convert prior outcomes, human overrides, and failed remediations into future decision signals.

**Acceptance criteria:**

- Memory records distinguish success, failed action, rejected action, stale signal, and poisoned/misleading signal.
- Planner and readiness score consume memory warnings.
- Learning remains local/mock and does not mutate external runbooks.

### P9-007 — Chaos Replay Tournament

**Outcome:** Evaluate commander quality across scenario variants, not just fixed fixtures.

**Acceptance criteria:**

- Tournament runner creates deterministic variants from replay fixtures.
- Score includes correct route, unsafe-action blocking, evidence graph completeness, readiness calibration, verification correctness, and report quality.
- Full verify or eval profile includes a bounded P9 tournament smoke.

### P9-008 — Commander UI Panel

**Outcome:** Operator UI shows the commander loop clearly enough for portfolio review.

**Acceptance criteria:**

- Incident detail shows commander stage, response plan, readiness, evidence graph summary, verification state, learning signal, and next action.
- UI copy preserves local/mock and no-unattended-production-operation boundary.
- No browser mutation forms or auth/session work are added.

### P9-009 — Commander Safety Regression Pack

**Outcome:** Add tests that prevent commander logic from becoming overconfident or unsafe.

**Acceptance criteria:**

- Covers prompt/log injection, stale memory, poisoned memory, provider ambiguity, rollback-worsens-impact, verification false positive, high-confidence unsafe action, and missing evidence.
- Tests assert safe blocking and concrete human questions.
- Secret markers are redacted in commander output and reports.

### P9-010 — P9 Release Evidence and Roadmap Closure

**Outcome:** Close P9 with reproducible evidence and reviewer instructions.

**Acceptance criteria:**

- Final summary maps P9-001 through P9-010 to code/tests/docs.
- Release evidence includes commander loop, planner, readiness score, evidence graph, verifier, learning, tournament, UI, safety pack, and full verify.
- `bash scripts/verify.sh --profile full` passes before closure.

## Execution Order

1. P9-001 Incident Commander Loop
2. P9-002 Multi-step Response Planner
3. P9-003 Autonomy Readiness Score
4. P9-004 Evidence Graph Model
5. P9-005 Recovery Verifier v2
6. P9-006 Learning Loop from Prior Outcomes
7. P9-007 Chaos Replay Tournament
8. P9-008 Commander UI Panel
9. P9-009 Commander Safety Regression Pack
10. P9-010 Release Evidence and Roadmap Closure

Reason: build commander state first, then planning/readiness/graph/verifier/learning, then evaluate and expose it.

## Team Implementation Guidance

Recommended execution mode: coordinated `$team`, because P9 touches services, evals, UI, reports, and docs.

Suggested lanes:

- worker-1: P9-001/P9-002 commander loop and response planner.
- worker-2: P9-003/P9-004 readiness score and evidence graph.
- worker-3: P9-005/P9-006 recovery verifier and learning loop.
- worker-4: P9-007/P9-009 chaos tournament and safety regression pack.
- worker-5: P9-008/P9-010 commander UI, docs, release evidence, final verification.

## Final Gate

`bash scripts/verify.sh --profile full` must pass from leader HEAD before P9 closure.
