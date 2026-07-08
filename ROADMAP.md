# OpsCat Roadmap

OpsCat is moving from a portfolio-grade local/mock agentic on-call MVP toward a beta-grade agentic operations system.

## P4 complete

P4 is complete. It added reproducible evidence for the local/mock operator-replacement claim:

- 23/23 golden incident evals;
- 7/7 connector safety evals;
- dashboard browser-contract E2E;
- eval taxonomy and release evidence index;
- full `bash scripts/verify.sh` release gate.

See `docs/release-evidence.md` and `docs/integration-verification.md`.

## P5 complete

P5 delivered OSS-usable productization without auth: quickstart, contributor docs, issue templates, connector setup/permission preview, secret lifecycle, incident import fixtures, worker CLI, approval console, Night Autopilot evidence, expanded connector evals, self-observability, CI profiles, security policy, and release packaging.

Historical P5 active plan: `docs/operations/p5-ticket-roadmap.md`.

## P6 active

P6 active scope: Beta-grade agentic ops loop without auth.

Primary plan: `docs/operations/p6-ticket-roadmap.md`.

Current priority:

1. Real-provider-shaped Sentry connector deepening.
2. Incident correlation engine.
3. Root-cause candidate generator.
4. Runbook registry and planner.
5. Risk scoring engine v2 and action policy DSL.
6. Safe action runner with dry-run, rollback metadata, and audit.
7. Post-action verification and recovery-state machine.
8. Agent decision trace and audit timeline.
9. Operator console incident timeline and agentic action view.
10. Agentic eval suite v1.
11. One-command beta demo of the full agentic loop.
12. P6 safety/threat-model refresh.
13. P6 release evidence and roadmap update.
14. Portfolio demo polish package.

## Auth deferred

auth deferred means P5 and P6 intentionally do not include OIDC, SSO, login, password auth, session UI, production user provisioning, or CSRF/session-hardening tied to browser mutation forms. The current local-header demo identity remains the local/mock boundary until the owner explicitly reopens auth.

## P6 candidates

P6 candidates have been promoted into the P6 active roadmap. Remaining out-of-scope production candidates for later phases:

- production auth and tenant administration;
- real connector OAuth/secret-manager integration beyond local opt-in secrets;
- customer-side connector agent package;
- hosted workflow workers and queue infrastructure;
- live incident replay from sanitized exports;
- load/soak testing;
- deployment, backup/restore, and OpsCat self-monitoring for real beta environments;
- license decision and public release process.

## P7 active

P7 active scope: Agent Reliability & Safety Lab without auth. P7 focuses on replay-based reliability, adversarial evals, confidence calibration, self-critique, blast-radius analysis, action simulation, incident memory, Night Autopilot v2, failure-mode reporting, reliability dashboard metrics, and release evidence. See `docs/operations/p7-ticket-roadmap.md`. The active boundary is no-auth/local-mock: P7 does not add login/session UI, production credentials, hosted SaaS operations, or unrestricted production mutation.

## P7 candidates

P7 should focus on safety/autonomy hardening after the P6 loop exists:

- action blast-radius calculator;
- rollback guarantee checker;
- adversarial incident/log-injection evals;
- incident memory and similarity search;
- confidence calibration and self-critique before execution;
- production deployment packaging with explicit auth/tenant decision deferred or reopened by the owner.

## P6 — Beta-grade agentic ops loop

Status: implemented as local/mock beta evidence. See `docs/operations/p6-ticket-roadmap.md`, `docs/agentic-loop.md`, and `docs/release-evidence.md`. P7 candidates: hardened auth, stronger tenant isolation, real provider SDK hardening, and production-grade approval workflows.

## P7 — Agent Reliability & Safety Lab

P7 focuses on deterministic replay, adversarial evals, calibrated confidence, self-critique, blast-radius/simulation gates, incident memory, Night Autopilot v2, failure-mode reporting, and reliability dashboard evidence while preserving the no-auth/local-mock boundary.



## P8 implemented

P8 implemented as local/mock AI Incident Responder War Room evidence. P8 covers incident war room read models, operator-facing war room API/UI, agent reliability scoring, runbook critique, human question generation, expanded operator-replacement replay scenarios, war room report export, demo polish, security/threat-model refresh, and release evidence. See `docs/operations/p8-ticket-roadmap.md`, `docs/operations/p8-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P8 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or unattended production-operation claims.


## P9 active

P9 active scope: Autonomous Incident Commander without auth. P9 focuses on the incident commander loop, multi-step response planning, autonomy readiness scoring, evidence graph modeling, recovery verification v2, learning from prior outcomes, chaos replay tournaments, commander UI, safety regression hardening, and release evidence. See `docs/operations/p9-ticket-roadmap.md` and `docs/tickets/p9/README.md`. The boundary remains no-auth/local-mock: P9 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or unattended production-operation claims.

## P9 implemented

P9 implemented as local/mock Autonomous Incident Commander evidence. P9 covers the commander lifecycle, multi-step response planning, autonomy readiness scoring, evidence graph modeling, recovery verification v2, learning from prior outcomes, chaos replay tournaments, commander UI, safety regression hardening, and release evidence. See `docs/operations/p9-ticket-roadmap.md`, `docs/operations/p9-final-summary.md`, `docs/security-review-p9.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P9 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or unattended production-operation claims.

## P10 active

P10 active scope: Incident Judgment Benchmark without auth or external dataset downloads during normal verification. P10 focuses on judgment case schema, LogHub-style and NAB-style adapters, rubric scoring, commander judgment evaluator, dataset conversion CLI, benchmark runner, regression baseline comparison, markdown/JSON reports, seed dataset fixtures, verification integration, and release evidence. See `docs/operations/p10-ticket-roadmap.md` and `docs/tickets/p10/README.md`. The boundary remains no-auth/local-mock: P10 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or unattended production-operation claims.

## P10 implemented

P10 implemented as local/mock Incident Judgment Benchmark evidence. P10 covers judgment case schema, LogHub-style adapter, NAB-style metric adapter, rubric scoring, commander judgment evaluator, dataset conversion CLI, benchmark runner, regression baseline comparison, markdown/JSON reports, seed dataset fixtures, verification integration, and release evidence. See `docs/operations/p10-ticket-roadmap.md`, `docs/operations/p10-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P10 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or unattended production-operation claims.

## P11 active

P11 active scope: Incident Corpus Expansion before LLM judgment. P11 focuses on an incident archetype catalog, deterministic local/mock corpus generation, corpus quality audits, a stable smoke selector, corpus report CLI, expanded fixture pack, verification integration, and release evidence. See `docs/operations/p11-ticket-roadmap.md` and `docs/tickets/p11/README.md`. The boundary remains no-auth/local-mock: P11 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, or unattended production-operation claims.

## P11 implemented

P11 implemented as local/mock Incident Corpus Expansion evidence. P11 covers the incident archetype catalog, deterministic corpus generation, corpus audit metrics, corpus pack writer, benchmark smoke selector, corpus report CLI, expanded fixture pack, verification integration, and release evidence. See `docs/operations/p11-ticket-roadmap.md`, `docs/operations/p11-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P11 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, or unattended production-operation claims.

## P12 active

P12 active scope: Real Dataset Evaluation Harness before LLM judgment. P12 focuses on external dataset source manifests, local-path import contracts, LogHub/NAB/AIOps-shaped adapters, label taxonomy mapping, tiny fixture samples, dataset conversion CLI, real-dataset-shaped evaluation runner, reports/baselines, verification integration, and release evidence. See `docs/operations/p12-ticket-roadmap.md` and `docs/tickets/p12/README.md`. The boundary remains no-auth/local-mock: P12 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, or unattended production-operation claims.

## P12 implemented

P12 implemented as local/mock Real Dataset Evaluation Harness evidence. P12 covers external dataset source manifests, local-path import contracts, LogHub/NAB/AIOps-shaped adapters, label taxonomy mapping, tiny fixture samples, dataset conversion CLI, real-dataset-shaped evaluation runner, reports/baselines, verification integration, and release evidence. See `docs/operations/p12-ticket-roadmap.md`, `docs/operations/p12-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P12 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, model calls, or unattended production-operation claims.

## P13 active

P13 active scope: LLM Context Builder before LLM judgment. P13 focuses on context packet schema, evidence selection, unsafe evidence annotation, timeline building, candidate hypothesis context, runbook context selection, safety constraints, required output schema, context builder CLI, verification integration, and release evidence. See `docs/operations/p13-ticket-roadmap.md` and `docs/tickets/p13/README.md`. The boundary remains no-auth/local-mock: P13 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, model calls, or unattended production-operation claims.


## P13 implemented

P13 implemented as local/mock LLM Context Builder evidence. P13 covers deterministic context packet schema, redacted evidence selection, unsafe evidence annotation, timeline building, candidate hypothesis context, runbook context selection, safety constraints, required output schema, context builder CLI, verification integration, and release evidence. See `docs/operations/p13-ticket-roadmap.md`, `docs/operations/p13-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P13 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, model calls, or unattended production-operation claims.


## P14 active

P14 active scope: LLM Judgment Adapter without auth and without default external model calls. P14 focuses on a provider interface, deterministic mock judgment provider, response schema validation, evidence citation checking, safety gate, judgment runner, CLI/reporting, prompt-injection regression, verification integration, and release evidence. See `docs/operations/p14-ticket-roadmap.md` and `docs/tickets/p14/README.md`. The boundary remains no-auth/local-mock: P14 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, default external model/API calls, action execution, or unattended production-operation claims.


## P14 implemented

P14 implemented as local/mock LLM Judgment Adapter evidence. P14 covers the provider interface, deterministic mock provider, response schema validation, evidence citation checking, safety gate, judgment runner, CLI/reporting, prompt-injection regression, verification integration, and release evidence. See `docs/operations/p14-ticket-roadmap.md`, `docs/operations/p14-final-summary.md`, and `docs/release-evidence.md`. The boundary remains no-auth/local-mock: P14 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, external dataset downloads during normal verification, default external model/API calls, action execution, or unattended production-operation claims.


## P15 active

P15 active scope: NVIDIA LLM Provider Opt-in. P15-mini adds an explicit NVIDIA/OpenAI-compatible provider for `nvidia/nemotron-3-ultra-550b-a55b`, key-gated execution, prompt contract, response parsing, CLI provider selection, offline testability, and release evidence. The boundary remains no-auth/local-mock by default: P15 does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.


## P15 implemented

P15 implemented as opt-in NVIDIA LLM Provider evidence. P15-mini adds `NvidiaLLMJudgmentProvider` for the OpenAI-compatible NVIDIA endpoint, default model `nvidia/nemotron-3-ultra-550b-a55b`, `NVIDIA_API_KEY` key gating, prompt contract, response parsing, CLI `--provider nvidia` selection, offline fake-client tests, and release evidence. The boundary remains no-auth/local-mock by default: normal verification performs no external model/API calls, and live NVIDIA use remains explicit, safety-gated, and action-execution disabled.


## P16 active

P16 active scope: LLM Provider Evaluation Runner. P16 evaluates mock and opt-in NVIDIA judgment providers across existing judgment cases with schema, citation, route, hypothesis, evidence, forbidden-action, and safety scoring. The boundary remains no-auth/local-mock by default: normal verification performs no external model/API calls, no API keys are committed or printed, and no action execution or production mutation is introduced.


## P16 implemented

P16 implemented as LLM Provider Evaluation Runner evidence. P16 scores mock and explicit opt-in NVIDIA provider judgments across incident cases for schema validity, evidence citation accuracy, route judgment, hypothesis coverage, required evidence citation, forbidden-action handling, safety-gate behavior, latency, and failure reasons. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P17 active

P17 active scope: LLM Policy Calibration. P17 adds a deterministic policy calibration layer after LLM provider judgment and safety gating so OpsCat can downgrade over-aggressive LLM routes, remove risky automatic actions, preserve auditability, and score provider evaluations against calibrated decisions. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.

## P17 implemented

P17 implemented as LLM Policy Calibration evidence. P17 adds a deterministic approval-governor layer after LLM provider judgment and safety gating, preserving provider route, safety-gate route, calibrated route, retained actions, removed actions, and calibration reasons. Provider evaluation now scores calibrated decisions, so OpsCat can prove it blocks over-aggressive LLM recommendations such as no-data restarts, deploy rollback automation, and prompt-injection auto-approval. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P18A active

P18A active scope: Realtime Source Reader. P18A adds local/mock source-native incremental ingestion for logs and metrics before model judgment quality evaluation. Runtime reads original files/streams incrementally, keeps bounded rolling windows, detects triggers, and emits JSON evidence snapshots only when judgment/replay/audit requires them. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.

## P18A implemented

P18A implemented as Realtime Source Reader evidence. P18A adds local/mock source-native incremental ingestion for logs and metrics, bounded rolling windows, realtime trigger detection, and JSON evidence snapshot generation for later model-quality evaluation. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P18B active

P18B active scope: Model Judgment Quality Lab. P18B measures raw LLM incident judgment quality separately from P17 policy calibration, including route accuracy, hypothesis quality, citation quality, evidence sufficiency, action proposal quality, safety behavior, failure taxonomy, and calibration delta. P18B uses P18A source-native snapshots plus existing judgment cases. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.

## P18B implemented

P18B implemented as Model Judgment Quality Lab evidence. P18B adds raw-vs-calibrated model scoring, expanded quality dimensions, provider failure taxonomy, P18A snapshot selection, hardened prompt automation preconditions, a mock/offline model quality CLI, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P19 active

P19 active scope: Operator Judgment Improvement Loop. P19 converts P18B raw model-quality failures into prioritized non-mutating improvement recommendations, safe missing-evidence plans, regression packs, before/after trend comparison, CLI reports, verification integration, and release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.

## P19 implemented

P19 implemented as Operator Judgment Improvement Loop evidence. P19 adds failure intake, safety-first prioritization, non-mutating recommendations, read-only missing-evidence planning, regression pack generation, trend comparison, CLI reporting, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P20 active

P20 active scope: Closed-loop Agentic Incident Response. P20 connects observation, initial LLM-shaped judgment, missing-evidence detection, safe read-only local/mock diagnostic tool execution, revised judgment, action proposal, dry-run simulation, final approval/escalation routing, CLI reports, verification integration, and release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims.

## P20 implemented

P20 implemented as Closed-loop Agentic Incident Response evidence. P20 adds an audited local/mock loop for observe, initial_judgment, evidence_gap, evidence_fetch, revised_judgment, action_proposal, simulation, and final_decision. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P21 active

P21 active scope: Runtime Loop Runner and Operator Control Plane. P21 wraps the P20 closed-loop response agent in a local/mock runtime with queue state, deterministic tick processing, operator approval profiles, pause/resume/abort controls, bounded CLI reports, verification integration, and release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P21 implemented

P21 implemented as Runtime Loop Runner and Operator Control Plane evidence. P21 adds queue state, deterministic tick processing, approval profile enforcement, pause/resume/abort controls, runtime CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.
