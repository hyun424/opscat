# OpsCat P8 Ticket Roadmap — AI Incident Responder War Room

## Requirements Summary

P8 turns OpsCat from a safe local/mock agentic loop into a more credible **AI Incident Responder** experience. P7 proved safety gates, replay reliability, confidence calibration, self-critique, blast-radius simulation, incident memory, Night Autopilot v2, and release evidence. P8 should make those capabilities visible and operationally useful through an incident war room, reliability scoring, runbook learning, and richer regression scenarios.

Boundary remains unchanged unless explicitly reopened by the owner:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no real production mutation, Kubernetes/cloud/database execution, or unrestricted shell;
- no customer credentials or hosted SaaS claims;
- all automatic action remains local/mock, allowlisted, policy-gated, simulated, audited, and reversible.

## P8 Goal

Build an **operator-grade incident response surface** where OpsCat can:

1. create an incident war room automatically;
2. explain current state, impact, timeline, evidence, root-cause candidates, missing evidence, and next actions;
3. calculate an agent reliability score from replay, safety, confidence, memory, and action outcomes;
4. critique runbooks using prior outcomes and suggest safer runbook improvements;
5. expand regression/chaos scenarios so every autonomy claim is measurable.

## P8 Tickets

### P8-001 — Incident War Room Read Model

**Outcome:** A deterministic read model that turns an incident into a single operator-facing war room object.

**Likely touchpoints:**

- `app/services/incident_service.py`
- `app/services/decision_trace_service.py`
- `app/services/report_service.py`
- `app/services/incident_memory.py`
- new `app/services/war_room_service.py`
- tests under `tests/test_war_room_*.py`

**Acceptance criteria:**

- War room includes: status, impact, timeline, current hypothesis, top 3 root-cause candidates, evidence, missing evidence, proposed action, policy decision, blast-radius, simulation, memory matches, reliability gates, and human questions.
- Redaction applies to every rendered field.
- Output is deterministic for local fixtures.
- No provider/network/shell calls.

**Verification:**

- Unit tests for read model shape and redaction.
- Integration test from mock alert -> investigated incident -> war room JSON.

---

### P8-002 — War Room API and Operator Console Panel

**Outcome:** Expose the war room through API and operator UI so the portfolio demo shows the AI responder’s reasoning in one place.

**Likely touchpoints:**

- `app/api/incidents.py`
- `app/api/operator.py`
- `tests/test_operator_dashboard.py`
- `tests/test_operator_dashboard_e2e.py`

**Acceptance criteria:**

- `GET /incidents/{id}/war-room` returns scoped, redacted JSON.
- Operator detail page has a War Room section.
- Section shows: summary, impact, evidence, timeline, hypotheses, risk gates, recommended next action, and “why not auto-execute” reason.
- Workspace scope checks remain enforced.

**Verification:**

- API scope tests for alpha/beta workspace separation.
- HTML contract/E2E tests for war room panel.

---

### P8-003 — Agent Reliability Score v1

**Outcome:** A transparent scoring model that says how reliable the agent’s decision is before action.

**Likely touchpoints:**

- `app/services/reliability_dashboard.py`
- `app/services/confidence_calibration.py`
- `app/services/replay_service.py`
- new `app/services/agent_reliability_score.py`

**Score inputs:**

- replay pass rate;
- dangerous action block rate;
- confidence calibration bucket;
- evidence count;
- conflicting/ambiguous signals;
- blast-radius scope;
- simulation status;
- memory prior outcome;
- post-action verification outcome.

**Acceptance criteria:**

- Score is deterministic, explainable, and decomposed by component.
- High score cannot override prohibited/unknown blast-radius policy.
- Score appears in war room and reliability dashboard.
- Low score produces human-on-exception reason.

**Verification:**

- Unit tests for score component weights.
- Regression tests proving dangerous actions remain blocked even with high confidence.

---

### P8-004 — Runbook Critic and Improvement Suggestions

**Outcome:** OpsCat critiques the selected runbook before action and suggests safer improvements based on prior outcomes.

**Likely touchpoints:**

- `app/services/runbook_service.py`
- `app/services/incident_memory.py`
- `app/services/self_critique_service.py`
- new `app/services/runbook_critic.py`

**Acceptance criteria:**

- Critic reports runbook fit: `good_fit`, `weak_fit`, `unsafe`, or `insufficient_evidence`.
- Prior failed remediation reduces fit and blocks auto-action.
- Suggestions are local text artifacts only; no automatic production runbook mutation.
- War room shows runbook critique and suggested improvement.

**Verification:**

- Tests for successful prior, failed prior, missing evidence, protected service, and prohibited action cases.

---

### P8-005 — Human Question Generator

**Outcome:** When evidence is insufficient, OpsCat asks concrete human questions instead of vague “needs review.”

**Example outputs:**

- “Was payment-api deploy v42 safe to roll back?”
- “Is the provider currently degraded outside our system?”
- “Can we restart this staging worker pool now?”

**Likely touchpoints:**

- `app/services/self_critique_service.py`
- `app/services/war_room_service.py`
- `app/services/escalation.py`

**Acceptance criteria:**

- Questions are tied to missing evidence or policy gate failure.
- Questions include why the answer matters.
- Questions never request secrets or credentials.

**Verification:**

- Unit tests for low-confidence, conflicting evidence, protected domain, and failed simulation paths.

---

### P8-006 — Scenario Pack v2: Operator-Replacement Evals

**Outcome:** Expand fixture coverage from safety lab into practical incident responder evaluation.

**New scenario classes:**

- multi-service partial outage;
- repeated alert storm;
- deploy plus provider outage ambiguity;
- stale memory / poisoned memory;
- runbook mismatch;
- rollback would worsen blast radius;
- action simulation passes but post-check fails;
- safe auto-action allowed in staging;
- unsafe high-confidence production mutation blocked;
- missing logs but strong metrics;
- noisy false-positive alert;
- quiet-hours incident with Night Autopilot blocked.

**Likely touchpoints:**

- `evals/replay/**`
- `app/services/replay_service.py`
- `scripts/run_replay_evals.py`
- tests under `tests/test_p8_*eval*.py`

**Acceptance criteria:**

- Add at least 40 P8 scenario fixtures.
- Every scenario records expected route, required blocked/allowed action, missing evidence, expected human question, and reliability score band.
- Replay eval output includes P8 scenario summary.

**Verification:**

- Replay CLI passes locally.
- Full verify includes P8 replay/eval profile.

---

### P8-007 — War Room Report Export

**Outcome:** Generate a Markdown artifact suitable for portfolio/demo review.

**Likely touchpoints:**

- `app/services/report_service.py`
- `app/services/war_room_service.py`
- docs under `docs/operations/`

**Acceptance criteria:**

- Export includes incident summary, timeline, evidence, hypotheses, reliability score, policy gates, human questions, and final decision.
- Redacted by default.
- No generated report artifacts tracked in git.

**Verification:**

- Report tests for redaction and required sections.
- Generated artifact scan remains clean.

---

### P8-008 — Operator Console Demo Polish

**Outcome:** Make the product understandable in a portfolio demo without reading code.

**Likely touchpoints:**

- `app/api/operator.py`
- `docs/demo-script.md` or `docs/operations/p8-demo-script.md`
- existing HTML contract tests

**Acceptance criteria:**

- One demo flow shows: alert -> war room -> score -> runbook critique -> action gate -> report.
- Demo clearly states local/mock boundary.
- UI avoids claiming unattended production operation.

**Verification:**

- Local demo smoke includes P8 war room URL.
- E2E/HTML tests assert key panel sections.

---

### P8-009 — P8 Security and Threat Model Refresh

**Outcome:** Document new risks introduced by war room, scoring, and runbook learning.

**Threats to cover:**

- stale/poisoned incident memory;
- over-trusting reliability score;
- prompt/log injection in war room text;
- accidental secret exposure in evidence/report;
- unsafe runbook improvement suggestions;
- UI implying production autonomy.

**Likely touchpoints:**

- `docs/security-review-p8.md`
- `docs/threat-model.md`
- `docs/release-evidence.md`

**Acceptance criteria:**

- Explicit auth deferral retained.
- Local/mock boundary repeated.
- Mitigations map to tests/evals.

**Verification:**

- Documentation tests assert required phrases and absence of secret markers.

---

### P8-010 — P8 Release Evidence and Roadmap Closure

**Outcome:** Close P8 with reproducible evidence.

**Likely touchpoints:**

- `docs/operations/p8-final-summary.md`
- `docs/release-evidence.md`
- `ROADMAP.md`
- `scripts/verify.sh`

**Acceptance criteria:**

- Final summary maps P8-001 through P8-010 to code/tests/docs.
- `bash scripts/verify.sh --profile full` passes.
- Release evidence points to replay outputs, war room tests, reliability score tests, and demo smoke.

## Execution Order

1. P8-001 War Room Read Model
2. P8-003 Agent Reliability Score v1
3. P8-004 Runbook Critic
4. P8-005 Human Question Generator
5. P8-002 War Room API/UI Panel
6. P8-006 Scenario Pack v2
7. P8-007 War Room Report Export
8. P8-008 Demo Polish
9. P8-009 Security/Threat Model
10. P8-010 Release Evidence and Closure

Reason: build core read models first, then expose UI/API, then scale evals and docs around stable contracts.

## Test Strategy

- Unit: war room assembly, score components, runbook critic, human question generator.
- Integration: mock alert to investigated incident to war room JSON/report.
- API: scoped `GET /incidents/{id}/war-room` and operator page contracts.
- Eval: P8 scenario pack replay with safety invariants.
- Security: redaction, no secret markers, no production mutation, auth deferred docs.
- Release: `bash scripts/verify.sh --profile full`.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| War room becomes just a pretty report | Require actionability: missing evidence, next action, human questions, gates |
| Reliability score overrules hard safety policy | Hard invariant: prohibited/unknown blast radius always blocks |
| Runbook learning implies real mutation | Suggestions are local text only; no automatic runbook write to external systems |
| UI overclaims operator replacement | Copy/docs say local/mock AI incident responder, not unattended production operation |
| Scenario pack becomes brittle/noisy | Deterministic fixture schema and replay CLI included in full verify |

## Team Implementation Guidance

Recommended execution mode: coordinated `$team`, because P8 touches services, API/UI, evals, reports, and docs.

Suggested lanes:

- worker-1: P8-001/P8-003 core read models and score service.
- worker-2: P8-004/P8-005 runbook critic and human questions.
- worker-3: P8-002/P8-007 API, operator panel, report export.
- worker-4: P8-006 scenario pack and replay/eval wiring.
- worker-5: P8-008/P8-009/P8-010 demo polish, docs, release evidence, final verification.

Team verification path:

1. Each lane lands targeted RED/GREEN tests.
2. Each lane reports no-auth/local-mock/no-production-mutation boundary.
3. Leader integrates, resolves cross-lane contracts, then runs:
   - `uv run --extra dev ruff check app tests scripts`
   - `uv run --extra dev mypy app tests scripts`
   - `bash scripts/verify.sh --profile full`
4. Shutdown only after team tasks are terminal and leader HEAD passes full verify.

## Launch Hint

```bash
cd /Users/gimdonghyeon/projects/opscat
omx team 5:executor "Implement OpsCat P8 from docs/operations/p8-ticket-roadmap.md. Preserve no-auth/local-mock boundaries. Follow plan -> plan review -> TDD implementation -> verification. Do not add auth, real production mutation, unrestricted shell, Kubernetes/cloud/database mutation, customer credentials, or hosted SaaS claims."
```
