# OpsCat Roadmap

## P132 complete: supervised local runtime qualified

P132 hardens and
qualifies the real P131 local monitor process for graceful signals, bounded
report retention, storage-pressure failure, single-host supervisor manifests,
external-process crash/restart recovery, split-brain lease rejection, and
explicit evaluator-vs-runtime authority accounting. P132 remains no-auth,
credential-free, local JSONL only, and does not claim direct live connectors,
external notification, remediation, 24/7 production availability, production
autonomy, or operator replacement. See
`docs/operations/p132-final-summary.md`.

## P133 complete: local dead-man evidence outbox

P133 converts stopped, stale, missing, and tampered monitor health results into
redacted, durable local incident events. It adds deterministic transition
identity, crash replay, exclusive process leasing, local acknowledgement,
acknowledged-only retention, real CLI subprocess qualification, and parsed
systemd/Compose isolation contracts. It sends no network notification and has
no action authority. The launchd plist remains an explicitly unqualified
structural example.

## P135 complete: credential-free local export attachment qualified

P135 consumes bounded Prometheus, Loki, Grafana, Sentry, and OTLP-shaped local
exports only after revalidating a current P134 `OA1_LOCAL_ARTIFACT` receipt. The
canonical 30-case matrix passes with exact-zero forbidden authority, source-bound
independent review, secure duplicate rereads, and denominator-visible failures.

## P136 complete: incremental local export observation

P136 qualifies cursor-bound, crash-safe incremental observation of rotating
local provider exports without adding credentials, network calls, provider APIs,
delivery, action execution, remediation, or staging/production mutation.

## P137 complete: bounded local investigation and triage

P137 validates P136's fixed handoff bundle and turns promoted local evidence
into durable incidents, closed hypotheses, bounded local evidence selections,
terminal classifications, and a CAS-chained investigation ledger. Its canonical
60-case gate covers handoff tampering, correlation, every request catalog entry,
classification, lease, signals, crash replay, readiness, CAS, and resource
failure. Durable recovery revalidates atom semantics and rederives request
results, while the freeze binds every case's exact effective P137 config and
rebuilds expectations from case-input oracles. A post-release provenance audit
also locks real runtime-counter, evaluator-guard, and crash-recovery boundaries
with explicit spies and rejects matched observed/expected runtime forgery. This
qualifies local evidence triage only; live provider observation,
notifications, action/remediation, production mutation, and operator replacement
remain outside the authority boundary.

## P138: local observation-to-triage supervision

P138 composes P136 observation, the P136-owned publisher, and P137 triage under
a reconciliation-first finite supervisor. The approved contract requires the
exact six-phase path and zero-delta short path, P136 outcome intent -> checkpoint
-> completion recovery, whole-operation publisher leasing and split-commit
recovery, contiguous new-promotion publication, genesis-only bootstrap, the
shared exact 15-key zero-authority tuple, and exactly 30/30 release cases.

Qualification is fail-closed and artifact-driven. The runner/profile, tracked
matrix, freeze manifest, release evidence, independent final implementation
review, and `p138-release` profile must all validate before P138 is described as
`p138_local_observation_to_triage_supervisor_qualified`. The target is a production-shaped
local-only finite supervisor, not unattended production operation; it adds no
auth, credentials, environment discovery, provider/network access,
notification, action/remediation, staging/production mutation, or operator
replacement.

## P139: hardened local triage service host

P139 is qualified at exact 32/32. It hosts P138 behind explicit local bundle
and base paths, a whole-service lease, recoverable restart-control rollover,
hash-chained exit receipts, deterministic status, safe signals, and
network-disabled least-privilege deployment examples. The final evidence is
source-bound and preserves exact-zero shared runtime authority.

## P140: P139-to-P133 local dead-man adapter

P140 is implemented as a credential-free, network-free adapter that evaluates
P139 through its public status contract and delegates event durability to the
existing P133 writer. It preserves P133 event identity, crash replay,
deduplication, reminders, acknowledgement, recovery, and retention while
binding every result to P139 bundle and P133 config hashes. A stable P140
projection excludes observation timestamps so repeated checks do not create
false updates.

External notification requires a later reviewed notification-only authority,
and remediation remains blocked behind separate observation, identity,
approval, and action-authority qualification.

OpsCat is moving from a portfolio-grade local/mock agentic on-call MVP toward a beta-grade agentic operations system.

## P131 complete: credential-free always-on local monitoring

P131 adds a standalone, supervisor-friendly monitor process with monotonic
cadence, bounded local JSONL ingestion, atomic hash-verified checkpoints,
rotation/deduplication recovery, exclusive leasing, source freshness, synthetic
canary, daily summaries, independent watchdog, HTTP liveness/readiness, and a
deterministic release profile. Direct Prometheus polling is deferred because the
current P121 contract counts every live connector call as non-zero authority.
No auth, credentials, network calls, subprocesses, remediation, staging mutation,
or production mutation are enabled.

Next production-hardening candidates are a separately reviewed read-only
observation-authority contract, real multi-hour soak evidence, supervisor crash
recovery tests, and external notification delivery that cannot execute actions.

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

## P20 implemented

P20 implemented as Closed-loop Agentic Incident Response evidence. P20 adds an audited local/mock loop for observe, initial_judgment, evidence_gap, evidence_fetch, revised_judgment, action_proposal, simulation, and final_decision. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or action execution.

## P21 active

P21 active scope: Runtime Loop Runner and Operator Control Plane. P21 wraps the P20 closed-loop response agent in a local/mock runtime with queue state, deterministic tick processing, operator approval profiles, pause/resume/abort controls, bounded CLI reports, verification integration, and release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P21 implemented

P21 implemented as Runtime Loop Runner and Operator Control Plane evidence. P21 adds queue state, deterministic tick processing, approval profile enforcement, pause/resume/abort controls, runtime CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.

## P22 active

P22 active scope: Night-shift Runtime Drill and SLA Scoring. P22 evaluates the P21 runtime loop as a local/mock night-shift operator by running batches of incidents, scoring SLA/safety/escalation behavior, emitting reports, integrating verification, and preserving release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P22 implemented

P22 implemented as Night-shift Runtime Drill and SLA Scoring evidence. P22 adds drill scenario wrapping, deterministic runtime batch evaluation, SLA and safety scoring, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.

## P23 active

P23 active scope: Incident Scenario Corpus Expansion. P23 expands the local/mock incident judgment and drill corpus to at least 60 scenarios with broad taxonomy coverage, focused DB connection-pool cases, safety/adversarial cases, evidence integrity contracts, drill compatibility, verification integration, and release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P23 implemented

P23 implemented as Incident Scenario Corpus Expansion evidence. P23 expands the local/mock judgment and night-shift drill corpus to 60 scenarios with broad taxonomy coverage, focused DB connection-pool cases, safety/adversarial cases, evidence integrity tests, drill compatibility, verification integration, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.

## P24 active

P24 active scope: Proactive Risk Sentinel. P24 detects incident precursors before full outages, forecasts likely risk with ETA/confidence/evidence, plans safe preventive actions, adds proactive fixtures, exposes CLI reports, integrates verification, and preserves release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P24 implemented

P24 implemented as Proactive Risk Sentinel evidence. P24 adds local/mock pre-incident trend windows, risk signals, ETA/confidence forecasts, preventive action planning, proactive fixtures, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.

## P25 active

P25 active scope: Proactive Signal Corpus Expansion and Calibration. P25 expands proactive pre-incident fixtures to at least 100 local/mock windows, adds expected outcome metadata, evaluates ETA/route/confidence/action-safety calibration, reports risk-type coverage, integrates verification, and preserves release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P25 implemented

P25 implemented as Proactive Signal Corpus Expansion and Calibration evidence. P25 expands proactive pre-incident fixtures to 120 local/mock windows across 42 risk types, adds expected outcome metadata, ETA/route/confidence/action-safety calibration, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls or remediation execution.

## P26 active

P26 active scope: Real Telemetry Adapter Contract. P26 creates fixture/read-only adapters for Prometheus/Grafana, Datadog, and Sentry shaped payloads, normalizes telemetry series/events/snapshots, converts compatible metrics to proactive TrendWindows, adds CLI reports, integrates verification, and preserves release evidence. The boundary remains no-auth/local-mock by default: no login/session UI, production credentials, live observability API calls, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims.

## P26 implemented

P26 implemented as Real Telemetry Adapter Contract evidence. P26 adds read-only fixture adapters for Prometheus/Grafana, Datadog, and Sentry shaped payloads, normalizes telemetry snapshots, converts compatible signals to proactive trend windows, exposes a CLI report, integrates verification, and preserves release evidence. Normal verification remains no-auth/local-mock by default and performs no live observability API calls, external model/API calls, or remediation execution.

## P27 active

P27 active scope: Connector Readiness and Permission Contract. P27 defines safe read-only connector readiness before any live polling: declared capabilities, required permissions, credential references, health states, rate-limit/backoff policy, read-only enforcement, CLI reports, verification, and release evidence. The boundary remains no-auth/local-mock by default: no production credentials, live writes, production mutation, remediation execution, default external model/API calls, or unattended production-operation claims.

## P29 planned

P29 planned scope: Telemetry-grounded Judgment Quality Evaluation. P29 will evaluate whether OpsCat judgments improve when grounded in connector telemetry, including route choice, root-cause candidates, evidence citation, missing-evidence requests, and safety behavior.

## P30 planned

P30 planned scope: Controlled Auto-remediation Policy and Simulation. P30 will define conservative auto-remediation policy and simulation: only low-risk, reversible, pre-approved local/mock actions can auto-run; production-changing actions remain approval-required or blocked.


## P27 implemented

P27 implemented as Connector Readiness and Permission Contract evidence. P27 adds read-only connector manifest evaluation, credential-reference safety, connector health states, bounded retry/backoff, mutation-capability blocking, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no live writes, external model/API calls, production mutation, or remediation execution.

## P28 implemented

P28 implemented as Read-only Polling Runtime evidence. P28 adds bounded fixture/local polling jobs, P27 readiness gating, timeout/backoff/failure handling, P26 adapter integration, proactive trend-window output, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no live API calls, live writes, production mutation, or remediation execution.

## P29 implemented

P29 implemented as Telemetry-grounded Judgment Quality Evaluation evidence. P29 adds telemetry judgment cases, deterministic baseline-vs-grounded scoring, evidence citation checks, missing-evidence behavior, prompt-injection-safe telemetry handling, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no external model/API calls, production mutation, or remediation execution.

## P30 implemented

P30 implemented as Controlled Auto-remediation Policy and Simulation evidence. P30 adds capability taxonomy, conservative pre-approval policy, simulation-first action routing, auto/approval/blocked reports, adversarial safety drills, verification smoke, and release evidence. Normal verification remains simulation/local-mock by default and performs no production mutation, shell execution, external model/API calls, or remediation execution.

## P31 active

P31 active scope: End-to-End Operator Replacement Drill. P31 connects P27 readiness, P28 read-only polling, P29 telemetry-grounded judgment quality, and P30 controlled remediation simulation into one deterministic local/mock operator replacement drill with scoring, batch reports, verification, and release evidence. The boundary remains no-auth/local-mock by default: no live API calls, production mutation, remediation execution, unrestricted shell, or unattended production-operation claims.


## P31 implemented

P31 implemented as End-to-End Operator Replacement Drill evidence. P31 composes connector readiness, read-only polling, telemetry-grounded judgment quality, and controlled remediation simulation into one local/mock operator-replacement score and morning operator report. Normal verification remains no-auth/local-mock by default and performs no live API calls, production mutation, remediation execution, unrestricted shell execution, or unattended production-operation claim.

## P32 active

P32 active scope: Real Telemetry Replay Benchmark. P32 replays local Prometheus/Grafana, Datadog, and Sentry shaped telemetry fixtures through adapter normalization, trend-window detection, telemetry-grounded judgment scoring, and controlled remediation simulation. The boundary remains no-auth/local-mock by default: no live API calls, production mutation, remediation execution, unrestricted shell, default external model/API calls, or unattended production-operation claims.

## P32 implemented

P32 implemented as Real Telemetry Replay Benchmark evidence. P32 replays local Prometheus/Grafana, Datadog, and Sentry shaped fixtures through telemetry adapters, trend-window detection, telemetry-grounded judgment, and controlled remediation simulation. Normal verification remains no-auth/local-mock by default and performs no live API calls, production mutation, remediation execution, unrestricted shell execution, external model/API calls, or unattended production-operation claim.

## P33 active

P33 active scope: Live Connector Dry-run Harness. P33 validates connector configuration, permission posture, mock transport health, schema drift, and connector readiness score before any live polling. The boundary remains no-auth/local-mock by default: no live API calls, production mutation, remediation execution, unrestricted shell, default external model/API calls, or unattended production-operation claims.

## P33 implemented

P33 implemented as Live Connector Dry-run Harness evidence. P33 validates connector manifests, read-only permission posture, mock transport health, schema drift, connector readiness score, CLI reports, verification smoke, and release evidence. Normal verification remains no-auth/local-mock by default and performs no live API calls, production mutation, remediation execution, unrestricted shell execution, external model/API calls, or unattended production-operation claim.

## P34 active

P34 active scope: Live Read-only Polling Runtime v2. P34 uses P33 dry-run readiness to gate local read-only polling jobs, normalize fixture payloads, emit telemetry snapshots/trend windows, and score polling safety. The boundary remains no-auth/local-mock by default: no live API calls, production mutation, remediation execution, unrestricted shell, default external model/API calls, or unattended production-operation claims.

## P34 implemented

P34 implemented as Live Read-only Polling Runtime v2 evidence. P34 gates local read-only polling through P33 dry-run readiness, blocks write/mutation jobs, skips degraded/blocked connectors, adapts fixture telemetry, emits trend windows, and records CLI/release evidence. Normal verification remains no-auth/local-mock by default and performs no live API calls, production mutation, remediation execution, unrestricted shell execution, external model/API calls, or unattended production-operation claim.

## P35 active

P35 active scope: Incident Shadow Mode. P35 records diagnoses, routes, proposed actions, evidence links, and operator handoff output from read-only polling evidence without executing remediation. The boundary remains no-auth/local-mock by default: no live API calls, production mutation, remediation execution, unrestricted shell, default external model/API calls, or unattended production-operation claims.

## P35 implemented

P35 implemented as Incident Shadow Mode evidence. P35 records what OpsCat would diagnose, route, propose, block, and report from read-only evidence without executing remediation, and preserves CLI/release evidence. Normal verification remains no-auth/local-mock by default and performs no live API calls, production mutation, remediation execution, unrestricted shell execution, external model/API calls, or unattended production-operation claim.

## P36 active

P36 active scope: Approval Control Plane. P36 routes P35 shadow decisions through named local approval profiles (`manual`, `auto_read_only`, `night_watch`) and records auto-allowed, approval-required, or blocked decisions without auth/session work, live API calls, production mutation, remediation execution, unrestricted shell, default external model/API calls, or unattended production-operation claims.


## P36 implemented

P36 implemented as Approval Control Plane evidence. P36 routes P35 shadow decisions through local profiles, records auto-allowed, approval-required, and blocked routes, blocks untrusted/shell-like actions, preserves execution_count=0, integrates CLI/full verification smoke, and does not add auth/session work, live API calls, production mutation, remediation execution, unrestricted shell, external model/API calls, or unattended production-operation claims.

## P37 active

P37 active scope: Open-source Config Hardening. P37 validates OSS/local templates and examples for placeholders, safe defaults, no real-looking secrets, disabled live/prod mutation, disabled remediation execution, and verification evidence. Auth remains out of scope.


## P37 implemented

P37 implemented as Open-source Config Hardening evidence. P37 validates committed OSS/local templates and examples, checks placeholders, credential references, secret-marker absence, and safe disabled defaults, integrates CLI/full verification smoke, and never reads real `.env` values or enables auth, live calls, production mutation, remediation execution, unrestricted shell, external model/API calls, or unattended production-operation claims.

## P38 active

P38 active scope: Agent Evaluation Dashboard. P38 aggregates P33-P37 local evidence into a JSON/Markdown scorecard with phase cards, readiness tier, boundary gates, and artifact links. It remains local-only with no hosted UI, auth, live calls, production mutation, remediation execution, external model/API calls, or unattended production-operation claims.


## P38 implemented

P38 implemented as Agent Evaluation Dashboard evidence. P38 aggregates P33-P37 local scorecards into JSON/Markdown phase cards, computes overall score, readiness tier, and boundary violations, integrates CLI/full verification smoke, and remains local-only with no hosted UI, auth, live calls, production mutation, remediation execution, unrestricted shell, external model/API calls, or unattended production-operation claims.

## P39 active

P39 active scope: Runbook Learning Loop. P39 converts local blocked/degraded/approval-heavy evaluation signals into runbook improvement recommendations and regression cases without automatically editing production runbooks, adding auth, calling live APIs, mutating production, executing remediation, using external models, or claiming unattended production operation.


## P39 implemented

P39 implemented as Runbook Learning Loop evidence. P39 converts local blocked/degraded/approval/config/dashboard signals into reviewable runbook recommendations and regression cases, redacts unsafe command text, integrates CLI/full verification smoke, and does not automatically edit production runbooks, add auth, call live APIs, mutate production, execute remediation, use external models, or claim unattended production operation.

## P40 active

P40 active scope: Production-readiness Milestone Bundle. P40 packages P33-P39 verified local evidence into a readiness bundle, declares local portfolio readiness, and explicitly marks production autopilot/unattended operation as not ready until auth, live connector validation, production-safe execution controls, and operational SLOs exist.


## P40 implemented

P40 implemented as Production-readiness Milestone Bundle evidence. P40 packages P33-P39 local evidence into readiness gates, blocker register, portfolio summary, and evidence bundle; declares local-portfolio-ready; keeps production_autopilot_ready=false; documents auth, live connector validation, and production execution-control blockers; integrates CLI/full verification smoke; and does not claim unattended production operation.

## P41 active

P41 active scope: Raw Real Dataset Scored Replay. P41 evaluates source-native repo-local LogHub-style JSONL, NAB-style CSV, and AIOps-style JSONL files, scores root-cause/route predictions against labels, and preserves the local/no-download/no-live/no-execution boundary.

## P41 implemented

P41 implemented as Raw Real Dataset Scored Replay evidence. P41 reads repo-local source-native LogHub-style JSONL, NAB-style CSV, and AIOps-style JSONL fixture files directly, scores labels/root-cause/route against expected outcomes, emits per-source cards and CLI reports, integrates full verification smoke, and preserves the no-download/no-live/no-auth/no-mutation/no-remediation-execution/no-unattended-production-operation boundary.

## P42 active

P42 active scope: External Dataset Acquisition & Holdout Evaluation. P42 adds an opt-in public dataset acquisition manifest, no-network default acquisition planner, deterministic holdout split, and holdout scoring over raw dataset replay evidence while preserving the no-download/no-live/no-auth/no-mutation/no-remediation-execution/no-unattended-production-operation boundary during normal verification.

## P42 implemented

P42 implemented as External Dataset Acquisition & Holdout Evaluation evidence. P42 defines public LogHub/NAB source metadata, keeps normal verification in no-network dry-run mode, exposes an explicit `--allow-network` acquisition boundary, builds deterministic train/dev/holdout splits from repo-local raw fixtures, scores holdout sources through the P41 raw replay harness, integrates full verification smoke, and preserves the no-download/no-live/no-auth/no-mutation/no-remediation-execution/no-unattended-production-operation boundary by default.

## P43 active

P43 active scope: Opt-in Public Dataset Download & Benchmark Scorecard. P43 executes the P42 acquisition boundary by downloading small public LogHub/NAB samples only with explicit opt-in, materializing downloaded raw data into P41-compatible replay files, scoring the benchmark, and keeping normal verification offline/fixture-backed.

## P43 implemented

P43 implemented as Opt-in Public Dataset Download & Benchmark Scorecard evidence. P43 keeps full verification offline/fixture-backed, adds explicit network-gated downloads for public LogHub/NAB samples, materializes downloaded raw logs and NAB labels into P41-compatible files under `/tmp`, scores 4,000 downloaded public records in the opt-in benchmark, records scorecards, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no committed generated artifacts, no default external model calls, and no unattended production-operation claim.

## P44 active

P44 active scope: Larger Public Dataset Benchmark Matrix. P44 expands P43 into a multi-source public benchmark matrix across LogHub and NAB families, reports source-level/family-level scores, tracks weak spots, and keeps normal verification offline/fixture-backed while public downloads remain explicit opt-in.

## P44 implemented

P44 implemented as Larger Public Dataset Benchmark Matrix evidence. P44 keeps full verification offline/fixture-backed, adds a five-source LogHub/NAB public matrix manifest, produces source-level and family-level score rows, records weak-spot proxy counts, executes an explicit network-gated public matrix with 10,000 parsed records across two families, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no committed generated artifacts, no default external model calls, and no unattended production-operation claim.

## P45 active

P45 active scope: Evidence-Grounded Judgment Contract. P45 requires every incident judgment to include supporting evidence, counter-evidence, missing evidence, confidence, uncertainty, and action boundaries before any route or remediation recommendation is trusted.

## P46 active

P46 active scope: Investigator Loop. P46 observes multi-source signals, generates ranked hypotheses, binds support/counter/missing evidence, proposes read-only next investigations, and gates unsafe actions conservatively.

## P47 active

P47 active scope: Tool Selection Planner. P47 maps each investigation need to safe read-only observability tools, preserves evidence references, and blocks mutation, shell, rollback, restart, and delete actions.

## P48 active

P48 active scope: Hypothesis Re-ranking. P48 incorporates read-only investigation results, demotes hypotheses contradicted by counter-evidence, promotes better-supported hypotheses, and keeps actions gated when evidence conflicts.


## P48 implemented

P48 implemented as Hypothesis Re-ranking evidence. P48 incorporates read-only investigation observations, updates confidence with support/counter deltas, records anti-anchoring demotions when the initial top hypothesis is contradicted, keeps auto-execution disabled, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P49 active

P49 active scope: Remediation Verification Loop. P49 turns proposed remediations into pre-check, mock/draft execution boundary, post-check, and recovery-or-escalation evidence while keeping production execution disabled.


## P49 implemented

P49 implemented as Remediation Verification Loop evidence. P49 verifies proposed remediations through pre-checks, mock/draft execution boundaries, post-check recovery criteria, and escalation on failed verification while keeping production execution disabled and preserving no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P50 active

P50 active scope: Night Operator Drill v2. P50 chains P45-P49 local evidence into an operator-like night drill, marks local night watch ready, and keeps unattended production readiness false until auth, live connector validation, and production execution controls exist.


## P50 implemented

P50 implemented as Night Operator Drill v2 evidence. P50 chains P45-P49 local evidence into an operator-like night drill, marks local_night_watch_ready=true, keeps unattended_production_ready=false, records blockers for production autonomy, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P51 active

P51 active scope: Operator Judgment Benchmark v2. P51 scores detection recall, top-1 hypothesis accuracy, evidence quality, route accuracy, re-ranking success, recovery verification coverage, and hard-zero safety metrics before further UI/live-product integration.


## P51 implemented

P51 implemented as Operator Judgment Benchmark v2 evidence. P51 scores detection recall, top-1 hypothesis accuracy, evidence quality, route accuracy, re-ranking success, recovery verification coverage, and hard-zero safety metrics before further UI/live-product integration, while preserving no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P52 active

P52 active scope: Failure Mining Loop. P52 converts P51 benchmark failure taxonomy into prioritized improvement tickets and deterministic regression cases so judgment quality improves from measured weaknesses before UI/live-product expansion.


## P52 implemented

P52 implemented as Failure Mining Loop evidence. P52 converts P51 benchmark failures into clustered improvement tickets and deterministic regression cases, prioritizes evidence and recovery-verification gaps, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P53 active

P53 active scope: Failure-Driven Improvement Pack. P53 turns P52 mined evidence and recovery-verification gaps into concrete evidence probes, recovery checks, regression cases, and validation commands before more UI/live-product work.


## P53 implemented

P53 implemented as Failure-Driven Improvement Pack evidence. P53 converts P52 mined evidence and recovery-verification gaps into concrete evidence probes, recovery checks, regression cases, validation commands, and projected gap reduction while preserving no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.


## P54 active

P54 active scope: Failure-Driven Benchmark Improvement. P54 applies P53 probes and recovery checks to a derived P51 benchmark view, proves evidence/recovery gaps close, and preserves the original benchmark fixture for regression comparability.


## P54 implemented

P54 implemented as Failure-Driven Benchmark Improvement evidence. P54 applies P53 probes and recovery checks to a derived P51 benchmark view, proves evidence and recovery-verification gaps close, preserves the original fixture for regression comparability, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## P55 active

P55 active scope: Candidate Benchmark Promotion Gate. P55 promotes the P54 improved derived benchmark view into a versioned candidate benchmark pack while preserving the P51 fixture as the immutable regression baseline.

## P55 implemented

P55 implemented as Candidate Benchmark Promotion Gate evidence. P55 emits a versioned candidate benchmark pack, locks the source baseline with stable SHA-256 fingerprinting, gates promotion on gap closure, score deltas, baseline preservation, and hard-zero safety counters, while preserving no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## P56 active

P56 active scope: Candidate Benchmark Regression Runner. P56 repeats the P55 promotion gate to prove the candidate benchmark is stable, non-regressing, and safe across repeated local runs.

## P56 implemented

P56 implemented as Candidate Benchmark Regression Runner evidence. P56 repeats the P55 promotion gate, verifies stable source and candidate fingerprints, proves mined gaps remain closed, keeps score deltas non-negative, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## P57 active

P57 active scope: Real Dataset Candidate Regression Bridge. P57 links P56 candidate benchmark regression stability with the P44 offline public real-dataset matrix.

## P57 implemented

P57 implemented as Real Dataset Candidate Regression Bridge evidence. P57 links P56 repeat-run candidate stability with P44 public dataset matrix fixture coverage, requires dataset coverage and accuracy gates, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## P58 active

P58 active scope: LLM Judgment Candidate Harness. P58 evaluates the local/mock LLM judgment lane behind P57 bridge gates.

## P58 implemented

P58 implemented as LLM Judgment Candidate Harness evidence. P58 evaluates the local/mock LLM lane behind P57 candidate and real-dataset gates, requires schema/citation validity, pass-rate, score, and safety gates, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P59 active

P59 active scope: Hybrid Commander Comparator. P59 compares deterministic candidate gates, local/mock LLM judgment, and a guarded hybrid commander lane.

## P59 implemented

P59 implemented as Hybrid Commander Comparator evidence. P59 compares deterministic candidate gates, mock LLM judgment, and a guarded hybrid commander lane, recommends hybrid_guarded only under deterministic safety boundaries, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P60 active

P60 active scope: Operator Replacement Readiness Gate v2. P60 aggregates P56-P59 evidence into local/shadow operator replacement readiness while explicitly blocking unattended production autonomy.

## P60 implemented

P60 implemented as Operator Replacement Readiness Gate v2 evidence. P60 marks local/shadow operator replacement ready from P56-P59 gates, keeps unattended production readiness false with explicit blockers, and preserves no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P61 active

P61 active scope: Local Shadow Connector Validation. P61 validates a live-shaped local observability source through a read-only connector before any real server or staging connector is used.

## P61 implemented

P61 implemented as Local Shadow Connector Validation evidence. P61 reads a live-shaped local source through fetch-only connector methods, normalizes metrics/logs/errors/deployments into evidence, produces a shadow deploy-regression judgment, links to P60 readiness, and preserves no real server connection, no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P62 active

P62 active scope: Staging Read-only Connector Contract. P62 validates provider-shaped Grafana, Sentry, and Datadog staging connector contracts before real staging credentials or APIs are attached.

## P62 implemented

P62 implemented as Staging Read-only Connector Contract evidence. P62 validates provider-specific schema, read-only scopes, safe query budgets, staging-only environment boundaries, redacted credential references, and operator handoff while preserving no real server connection, no auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P63 active

P63 active scope: Staging Live Read-only Preflight Runner. P63 gates any staging observability API contact behind no-live defaults, explicit live staging flags, manual approval, allowlisted hosts, GET-only checks, P62 readiness, and safe timeout budgets.

## P63 implemented

P63 implemented as Staging Live Read-only Preflight evidence. P63 evaluates staging preflight eligibility without live calls by default, verifies live-path behavior through mock transport only, blocks unsafe production/admin/non-GET/disallowed-host checks, and preserves no real server connection in normal verification, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P64 active

P64 active scope: Audited Staging Credential + Transport Gate. P64 gates any staging transport attempt behind injected credential resolution, manual approval, audit logging, allowlisted HTTPS GET checks, P63 readiness, and safe timeouts.

## P64 implemented

P64 implemented as Audited Staging Credential + Transport Gate evidence. P64 records audit decisions without transport calls by default, verifies live-path behavior through mock transport only, blocks missing approval, raw credential values, unsafe methods, disallowed hosts, production/admin checks, and unsafe timeouts, while preserving no `.env` reads, no real credentials, no real server connection in normal verification, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P65 active

P65 active scope: Real Staging Read-only Dry Attach. P65 creates a real-staging-shaped dry attach plan that requires explicit secret-provider refs, allowlisted HTTPS staging endpoints, P64 audit handoff, safe detach plans, and zero network calls.

## P65 implemented

P65 implemented as Real Staging Read-only Dry Attach evidence. P65 marks Grafana, Sentry, and Datadog dry attachments attach-ready, blocks unsafe production/raw-token attach, emits safe detach plans, and preserves no `.env` reads, no real credential reads, no real server connection, no network calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P66 active

P66 active scope: Autonomous Day Loop Backlog. P66 gathers the next large operator-replacement roadmap into a 24-hour dry-run loop plan that only schedules safe-local work and keeps live/action/production work gated.

## P66 implemented

P66 implemented as Autonomous Day Loop Backlog evidence. P66 schedules P66-P92 into safe-local execution batches with hard-zero side-effect counters, checkpoint commands, gated live/action work retention, and blocked production autonomy while preserving no credential reads, no network calls, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P67 active

P67 active scope: Autonomous Loop Executor. P67 turns the P66 backlog into a resumable safe-local execution controller for one-shot or all-day autonomous development loops.

## P67 implemented

P67 implemented as Autonomous Loop Executor evidence. P67 selects currently runnable safe-local tickets, emits delegation prompts, records checkpoints, computes resume state, blocks gated live/action/production work, and preserves no credential reads, no network calls, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P68 active

P68 active scope: Autonomous Agent Dispatcher. P68 converts safe-local loop work into packet-only dispatch artifacts for external implementation agents.

## P68 implemented

P68 implemented as Autonomous Agent Dispatcher evidence. P68 emits per-ticket prompt and JSON dispatch packets, records blocked gated work, preserves max-parallel policy, computes next runnable state, and preserves no process spawning, no credential reads, no network calls, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P69 active

P69 active scope: Autonomous Worker Runner. P69 consumes dispatch packets, records worker run outcomes, retry queues, and resumable state through a recording transport.

## P69 implemented

P69 implemented as Autonomous Worker Runner evidence. P69 claims P68 packets, plans Codex worker commands through a recording transport, writes resumable state, records retry queues for failures, and preserves no process spawning, no credential reads, no network calls, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P70 active

P70 active scope: Gated Worker Process Runner. P70 validates planned worker commands against strict allowlists and dispatch-directory confinement before real process execution can be enabled.

## P70 implemented

P70 implemented as Gated Worker Process Runner evidence. P70 validates `codex exec` command shape, required safety flags, prompt path confinement, blocked unsafe commands, and preserves no process spawning, no credential reads, no network calls, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P71 active

P71 active scope: Supervised Worker Execution Harness. P71 executes P70 process-capable commands through an explicitly enabled supervised transport, captures stdout/stderr artifacts, persists state, and records retry outcomes.

## P71 implemented

P71 implemented as Supervised Worker Execution Harness evidence. P71 runs process-capable commands through simulated supervised transport in repository verification, supports opt-in real subprocess transport behind explicit enablement, writes per-ticket artifacts and resumable state, records retry queue entries, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P72 active

P72 active scope: Stateful All-Day Loop Orchestrator. P72 advances the P71 supervised harness across repeated cycles while accumulating completed state, retry queues, cycle checkpoints, and resume handoff.

## P72 implemented

P72 implemented as Stateful All-Day Loop Orchestrator evidence. P72 runs multiple simulated supervised cycles, persists orchestrator state after each cycle, stops on retry queues or missing process enablement, produces resume-completed handoff, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P73 active

P73 active scope: Long-Run Loop Controller. P73 repeats P72 windows under explicit duration, max-window, retry, and enablement guards so autonomous work can run for hours without becoming an unsafe infinite loop.

## P73 implemented

P73 implemented as Long-Run Loop Controller evidence. P73 repeats P72 windows, accumulates resume state, tracks virtual elapsed time and planned sleeps, stops on duration/max-window/retry/enablement guards, writes controller checkpoints, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no actual sleep in verification, no default external model/API calls, no action execution, no raw infinite loop, and no unattended production-operation claim.

## P74 active

P74 active scope: Real Subprocess Execution Dry-Run Gate. P74 verifies whether P70 process-capable commands are safe to hand to a future real subprocess transport without spawning anything.

## P74 implemented

P74 implemented as Real Subprocess Execution Dry-Run Gate evidence. P74 consumes P70 validation, requires explicit real-subprocess enablement, blocks dirty worktrees, enforces max-process budgets, preserves command-gate blocks, writes dry-run artifact placeholders and state handoff, and preserves no real subprocess spawning, no shell command execution, no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no default external model/API calls, no action execution, and no unattended production-operation claim.

## P75 active

P75 active scope: Local Safe Subprocess Runner. P75 consumes P74 dry-run-ready commands and runs them through an explicit local-safe subprocess runner while repository verification remains simulated and keeps actual subprocess spawning at zero.

## P75 implemented

P75 implemented as Local Safe Subprocess Runner evidence. P75 consumes P74 dry-run-ready plans, requires explicit local-subprocess enablement, writes stdout/stderr artifacts, persists completed/blocked/failed/retry state, exposes CLI JSON/Markdown reports, keeps normal verification on simulated local transport, and preserves no shell command execution, no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no default external model/API calls, no action execution, no actual subprocess spawning in verification, and no unattended production-operation claim.

## P76 active

P76 active scope: Evidence Sufficiency Gate v2. P76 upgrades P45 evidence-grounded judgments into a stricter gate that scores support strength, source diversity, counter-evidence visibility, missing evidence, and unsafe auto-execute before a judgment can proceed.

## P76 implemented

P76 implemented as Evidence Sufficiency Gate v2 evidence. P76 consumes P45 judgments, scores evidence sufficiency, classifies cases as approval-ready or human-required, emits required next evidence and rationale, blocks unsafe auto-execute requests, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P77 active

P77 active scope: Recovery Proof Engine. P77 upgrades remediation verification into explicit proof bundles that prove or reject recovery claims before an incident can be treated as recovered.

## P77 implemented

P77 implemented as Recovery Proof Engine evidence. P77 consumes P49 verification output, builds pass/fail proof bundles, scores recovery proof, classifies proven/not-proven/unsafe cases, emits operator next steps, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P78 active

P78 active scope: Runbook Simulation Tournament. P78 ranks multiple local/mock runbook candidates across safety, evidence sufficiency, recovery proof, blast radius, reversibility, and approval boundary before treating a runbook as release evidence.

## P78 implemented

P78 implemented as Runbook Simulation Tournament evidence. P78 parses local fixture candidates, scores six tournament dimensions, ranks the safest evidence-backed candidate, blocks production/action-execution proposals, emits CLI JSON/Markdown reports, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no action execution, no P78A/autonomous supervisor changes, and no unattended production-operation claim.

## P79 active

P79 active scope: Action Sandbox Hardening. P79 evaluates proposed actions against allowlists, blast radius, reversibility, approval state, dry-run capability, credential/network boundaries, production mutation boundaries, and shell boundaries before any action can leave local/mock evaluation.

## P79 implemented

P79 implemented as Action Sandbox Hardening evidence. P79 parses local proposed-action fixtures, returns allow, approval-required, mock-only, or block decisions, blocks prohibited external boundaries, emits CLI JSON/Markdown reports, and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P80 active

P80 active scope: Approval Automation Policy Lab. P80 evaluates when local/mock incident actions can be auto-approved, must require a human, should remain mock-only, or must be blocked by combining P79 sandbox decisions, evidence sufficiency, recovery proof, blast radius, reversibility, action class, historical safety, role/policy constraints, maintenance windows, and sleep-mode policy.

## P80 implemented

P80 implemented as Approval Automation Policy Lab evidence. P80 parses local fixture scenarios for restart worker, scale read replica, clear local cache, rotate credential, disable auth, run migration, rollback deploy draft, kill process, and increase rate limit; emits structured reasons, missing evidence, guardrails, audit records, and max execution modes; blocks sensitive/destructive auto-approval; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P81 active

P81 active scope: Rollback PR Draft Automation. P81 drafts safe rollback PR artifacts after P80 determines real execution is not allowed or needs human review, while keeping all outputs local/mock, draft-only, and approval-gated.

## P81 implemented

P81 implemented as Rollback PR Draft Automation evidence. P81 parses local fixture scenarios for safe config rollback, deploy revert draft, migration rollback review, credential/auth rollback block, and insufficient evidence rejection; emits structured draft artifacts with proposed file-change or command-plan text, risk, evidence references, human approval, verification checklist, rollback/abort plan, and audit metadata; downgrades P80 auto-approval to draft-only; and preserves no live GitHub API calls, no credential reads, no network calls, no branch creation, no git push, no production mutation, no remediation execution, no shell command execution, no rollback command execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P82 active

P82 active scope: Slack and Ticket Draft Automation. P82 generates safe, evidence-grounded Slack/status-update drafts and ticket drafts after incident triage or rollback planning while keeping all outputs local/mock, draft-only, and approval-gated.

## P82 implemented

P82 implemented as Slack and Ticket Draft Automation evidence. P82 parses local fixture scenarios for confirmed deploy regression, suspected DB saturation requiring human confirmation, rollback draft ready, blocked credential/auth issue, and insufficient-evidence noisy alert; emits structured Slack incident update, escalation DM, status update, ticket title/body/labels/priority, evidence links, uncertainty, next actions, approval requirement, and audit metadata; preserves P76 evidence sufficiency, P80 approval, and P81 rollback draft status; and preserves no live Slack/Jira/GitHub/Linear API calls, no credential reads, no network calls, no message sending, no ticket creation, no production mutation, no remediation execution, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P83 active

P83 active scope: Post-Action Outcome Monitor. P83 judges whether local/mock post-action evidence shows an action resolved, improved, failed to change, worsened, lacks enough evidence, or is unsafe to continue.

## P83 implemented

P83 implemented as Post-Action Outcome Monitor evidence. P83 parses local fixture scenarios for worker restart improvement, mock rollback resolution, unchanged DB saturation, worsened mitigation, noisy incomplete telemetry, and unsafe blocked action; emits structured outcome decisions, confidence, evidence references, metric/log deltas, missing evidence, next recommended step, communication draft update guidance, rollback draft human-review promotion guidance, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no rollback execution, no message sending, no ticket creation, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P84 active

P84 active scope: Outcome-Driven Next Action Planner. P84 converts P83 post-action outcomes plus P76/P77/P80/P81/P82 safety and evidence state into the next safest local/mock operator plan.

## P84 implemented

P84 implemented as Outcome-Driven Next Action Planner evidence. P84 parses local fixture scenarios for resolved, improving, unchanged DB saturation, worsened mitigation, noisy incomplete telemetry, and unsafe blocked action; emits structured next-action plans with selected next action, rationale, required evidence, human approval requirement, communication update requirement, rollback promotion flag, wait/recheck window, guardrails, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no rollback execution, no message sending, no ticket creation, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P85 active

P85 active scope: Local Autonomous Supervisor Loop. P85 models a resumable local/mock supervisor over candidate work that selects only safe modeled local checks, persists checkpoints, and stops on budget, human-review, no-safe-work, or failed-guardrail conditions.

## P85 implemented

P85 implemented as Local Autonomous Supervisor Loop evidence. P85 parses local fixture scenarios for safe two-item batches, approval-blocked work, failure streaks, budget exhaustion, worsened outcome rollback/escalation review, and checkpoint resume; emits run IDs, selected and skipped item IDs, completed mock steps, wakeup recommendations, checkpoint records, audit metadata, resumable cursors, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no process spawning, no agent spawning, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P86 active

P86 active scope: Resumable Local Supervisor Runner. P86 makes the P85 local supervisor contract operational as a resumable local/mock runner that can continue from persisted fixture state, record atomic checkpoint write plans, and stop deterministically on safe stop reasons.

## P86 implemented

P86 implemented as Resumable Local Supervisor Runner evidence. P86 parses local fixture scenarios for fresh two-item completion, interrupted resume without duplicate completed items, max-iteration resumable stop, human-review blocking, guardrail failure streaks, and terminal completed-all behavior; emits run IDs, cursors, completed and skipped item IDs, iteration counts, failure streaks, checkpoint write-plan metadata, wakeup recommendations, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no process spawning, no agent spawning, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P87 active

P87 active scope: Supervisor Run Report Artifact. P87 turns P86-style local/mock supervisor run state into a structured JSON and Markdown report that shows what happened, why it stopped, what remains, terminal versus resumable classification, safety gates hit, next action, wakeup guidance, and human decision requirements.

## P87 implemented

P87 implemented as Supervisor Run Report Artifact evidence. P87 parses local fixture scenarios for completed_all, max_iteration, needs_human, failed_guardrail, no_safe_work, and resumed-run reports; emits completed, skipped, blocked, and resumable item summaries, checkpoint timelines, safety gates, next recommended actions, human decision sections, audit metadata, claim boundary, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no process spawning, no agent spawning, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P88 active

P88 active scope: Bounded Local Supervisor Scheduler Contract. P88 models bounded local scheduler cycles over P86 runner state and P87 report status, with safe wakeup windows, modeled wall-clock budgets, backoff, checkpoint write-plan metadata, and deterministic stop conditions.

## P88 implemented

P88 implemented as Bounded Local Supervisor Scheduler Contract evidence. P88 parses local fixture scenarios for completed work before max cycles, resumable work until max_cycles, immediate human handoff, guardrail failure backoff, no-safe-work budget exhaustion, and resumed scheduler duplicate protection; emits scheduler IDs, current cycle indexes, max cycles, modeled wall-clock budgets, selected run state IDs, terminal/resumable classification, stop reasons, next wakeup metadata, backoff policy, checkpoint write-plan metadata, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no sleeping, no process spawning, no agent spawning, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P89 active

P89 active scope: Safe Local Auto-Run Entrypoint. P89 provides one operator-facing local/mock command and report contract that composes P85 supervisor, P86 runner, P87 reporting, and P88 scheduler ideas into bounded modeled cycles with resume/report write plans.

## P89 implemented

P89 implemented as Safe Local Auto-Run Entrypoint evidence. P89 parses local fixture scenarios for dry-run completion, checkpoint resume without duplicate cycle IDs, human handoff, guardrail failure, max-cycles resumability, and no-safe-work recheck; emits config summaries, scheduled cycle metadata, resume state and report write-plan metadata, terminal status, stop reason, next recommended command text, handoff/failure summaries, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no sleeping, no process spawning, no agent spawning, no action execution, no default external model/API calls, and no unattended production-operation claim.

## P90 active

P90 active scope: Safe Auto-Run Readiness Gate. P90 evaluates whether P89-style safe local auto-run output and prior P76/P79/P80/P83/P84/P87/P88 safety evidence are sufficient for longer local dry-run, supervised shadow, or human-gated staging dry-run operation.

## P90 implemented

P90 implemented as Safe Auto-Run Readiness Gate evidence. P90 parses local fixture scenarios for clean local dry-run, resumable incomplete work, needs-human handoff, failed guardrail, missing report/evidence, and nonzero side-effect counters; emits readiness levels, numeric scores, component scores, pass/fail gates, blockers, warnings, required next capabilities, allowed operating modes, forbidden claims, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no sleeping, no process spawning, no agent spawning, no action execution, no default external model/API calls, no production unattended approval, and no operator replacement approval.

## P91 active

P91 active scope: Readiness Gap Remediation Planner. P91 turns P90 readiness blockers into a prioritized, evidence-grounded remediation backlog with required tests, owner lanes, stop conditions, forbidden claims, and next safe operating modes.

## P91 implemented

P91 implemented as Readiness Gap Remediation Planner evidence. P91 parses local fixture scenarios for local-ready minor warnings, missing evidence/reportability, side-effect counter detection, failed guardrail, high-severity human handoff, and clean ready state; emits plan IDs, source readiness IDs, prioritized remediation items with severity, expected readiness lift, required evidence/tests, owner lane, dependencies, risk, stop condition, next safe operating mode, claims that remain forbidden, blocked/human-gated items, audit metadata, and zero-side-effect counters; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no sleeping, no process spawning, no agent spawning, no action execution, no default external model/API calls, no production autonomy, and no unattended production approval.

## P92 active

P92 active scope: Operator Replacement Acceptance Drill v3 / Product Quality Evidence Pack. P92 packages P80-P91 local/mock evidence into deterministic acceptance levels, end-to-end stage evidence, safety boundary checks, readiness scores, blockers, roadmap items, portfolio/demo summaries, and forbidden claims.

## P92 implemented

P92 implemented as Operator Replacement Acceptance Drill v3 evidence. P92 parses local fixture scenarios for clean local dry-run acceptance, supervised shadow with minor warnings, human-gated approval need, failed guardrail/side-effect block, missing evidence/report block, and resumed auto-run with gap plan; emits drill IDs, scenario IDs, operator replacement levels, end-to-end stages with evidence refs, safety boundary checks, zero-side-effect counters, final readiness scores, top blockers, next roadmap items, portfolio/demo Markdown summaries, audit metadata, and forbidden claims; and preserves no live API calls, no credential reads, no network calls, no production mutation, no remediation execution, no shell command execution, no sleeping, no process spawning, no agent spawning, no action execution, no default external model/API calls, no production autonomy, no production operator replacement approval, and no unattended production approval.

## P93 active

P93 active scope: Portfolio Demo Narrative & Operator Walkthrough Evidence. P93 packages P92 and selected prior local/mock evidence into a deterministic portfolio demo pack, operator walkthrough, README polish, architecture narrative, release evidence, and docs-profile verification for an agentic AI incident-response/operator-replacement portfolio story.

## P93 implemented

P93 implemented as Portfolio Demo Narrative evidence. P93 emits a deterministic structured artifact with demo_id, title, portfolio_pitch, target_role_signals, architecture_sections, operator_walkthrough_steps, proof_points, safety_boundaries, forbidden_claims, demo_commands, expected_outputs, readiness_status, remaining_gaps, zero-side-effect counters, JSON/Markdown outputs, and count-style CLI smoke; and preserves no auth work, no live APIs, no credentials, no network, no production mutation, no real remediation/action execution, no external model/API calls, no production autonomy, no production operator replacement approval, and no unattended production approval.

## P94 active

P94 active scope: Operator Transcript Demo / Human-like Incident Response Walkthrough. P94 adds a deterministic local/mock transcript that shows experienced incident-response reasoning across evidence, hypotheses, tool choices, safe decisions, handoffs, verification, reports, and improvement gaps.

## P94 implemented

P94 implemented as Operator Transcript Demo evidence. P94 emits four deterministic transcripts for payment deploy regression, DB connection pool saturation, noisy metric spike with missing evidence, and prompt-injection-like log content; each transcript includes transcript_id, scenario_id, title, operator_goal, at least ten transcript steps, at least three hypotheses, selected and skipped tools, read-only tool plan, safe decision, verification, report summary, safety boundaries, forbidden claims, zero-side-effect counters, JSON/Markdown outputs, and count-style CLI smoke; and preserves no auth work, no live APIs, no credentials, no network, no production mutation, no real remediation/action execution, no external model/API calls, no production autonomy, no production operator replacement approval, and no unattended production approval.

## P95 active

P95 active scope: Clean-Clone Reproducibility Gate. P95 proves a reviewer can clone OpsCat from the private GitHub repository into a fresh directory, confirm local-only state is absent before setup, run the documented no-auth local/mock quickstart, and run the full verification profile without production credentials or hidden maintainer-machine state.

## P95 implemented

P95 implemented as Clean-Clone Reproducibility evidence. P95 cloned `https://github.com/hyun424/opscat` into `/private/tmp/opscat-clean-clone-p95-fixed.wX7zoU/opscat`, verified HEAD `c5a187d7ef2b13e9ada0b336b8bdf6d38ed700e3`, confirmed `.env`, `.DS_Store`, `.venv`, and `opscat.db` were absent before setup, ran `cp .env.example .env`, `make install`, `make quickstart`, and `bash scripts/verify.sh --profile full`, fixed the discovered `OPSCAT_MODE=local-mock` / `LocalEncryptedSecretProvider` quickstart mismatch, and recorded coverage `80.71% >= 60.00%`; it preserves no auth feature work, no live provider APIs, no production credential reads, no customer-log ingestion, no production mutation, no real remediation/action execution, no production autonomy, and no unattended production approval.

## P96 active

P96 active scope: Real Prometheus Read-only Shadow Connector. P96 replaces the first connector-shaped simulation with a bounded real Prometheus HTTP read path that normalizes metrics into scoped incident evidence while preserving fixture-default operation and zero action authority.

## P96 implemented

P96 implemented `prometheus.readonly` with `health.check`, `query.instant`, and `query.range`; trusted configured endpoints; exact host allowlisting; loopback-only HTTP; GET-only transport; timeout, response, series, duration, and point budgets; normalized/redacted provider failures; incident evidence and timeline persistence; operator CLI; catalog/config documentation; and executable security contracts. Fixture mode remains the default and network-free. Real mode is explicit opt-in. P96 adds no auth feature, provider writes, remediation execution, production mutation, LLM action authority, production autonomy, or unattended production approval.

## P97 implemented

P97 implements a causal remediation benchmark that compares `no_action`, `human_runbook`, and `opscat` from identical resettable states. A disposable loopback HTTP fault lab supplies measured pre/post/durability observations while a closed in-memory action registry prevents arbitrary commands, endpoints, credentials, filesystem changes, subprocesses, external network, and production mutation. The catalog contains 120 cases across 12 operational families, 10 variants, and development/validation/blind splits. The full matrix ran 1,080 trials and 64,800 loopback requests. It is synthetic-lab evidence and does not claim production remediation effectiveness.

## P98 implemented

P98 adds an evidence-only selector comparison harness over P97. It compares `rule_based`, `observation_only`, and `mock_llm` selectors on identical case/seed states, reports overall and blind causal recovery, utility lift, harmful actions, unverified outcomes, escalation correctness, and human-runbook regret, and fails closed on malformed or unsafe model output. The explicit NVIDIA provider is key-gated and advisory-only. The full matrix produced 3 selectors × 120 cases × 3 seeds, with every hard safety gate passing; rule and mock LLM both recovered 44.17% overall and 12.50% on blind cases, while observation-only recovered 16.67% overall. P98 is comparative synthetic-lab evidence and does not claim production effectiveness.

## P99 implemented

P99 expands the causal catalog from 12 families/120 cases to 52 families/520 cases across resource, storage, database, network, dependency, platform, messaging, scheduler, configuration, security, data-integrity, regional, and cost failures. The full three-seed matrix ran 4,680 arms and 140,400 loopback HTTP observations. OpsCat recovered 34.55%, the curated human runbook recovered 89.87% after the P100 catalog-consistency correction, no-action recovered 11.47%, escalation correctness/precision were both 100%, harmful actions were 0%, and every hard safety gate passed. P99 remains a broad synthetic taxonomy, not a literally exhaustive incident set or proof of production effectiveness.

## P100 implemented

P100 replaces one-shot selection with a bounded stateful incident investigator. It receives only public evidence and sanitized measured history, chooses one closed-registry action per step, re-observes the service, falls back after ineffective actions, completes partial/compound remediation, confirms natural recovery without mutation, and escalates privileged or ambiguous cases. The full 52-family/520-case, three-seed, four-arm matrix ran 6,240 trials and 183,990 loopback requests. Stateful recovery was 56.47% versus one-shot 34.55%; blind recovery was 39.42% versus 2.88%; expected escalation recall/precision were 100%; collateral regressions were zero; and every hard safety gate passed. P100 remains synthetic-lab evidence and does not authorize unattended production remediation.

## P101 implemented

P101 adds a runtime tool-using hypothesis investigator. Initial evidence is hidden; the agent ranks diagnostic surfaces from symptoms, executes closed read-only tools, demotes failed hypotheses, incorporates evidence, and only then delegates to the P100 stateful action policy. The full 520-case, three-seed, three-arm matrix ran 4,680 trials and 118,580 loopback requests. Relevant-tool discovery and recovery retention were 100%, Top-1 tool accuracy was 94.23%, tool-investigator recovery was 56.54%, fixed-tool recovery was 1.35%, and every hard safety gate passed. P101 does not prove unseen-language, hidden-topology, or production generalization.

## P102 implemented

P102 adds a provider-neutral LLM diagnostic tool planner with an exact JSON output
contract, a closed 17-tool read-only registry, fail-closed parsing, and four language,
topology, distractor, and injection perturbations per case. Default fixture evaluation
is deterministic and network-free; the NVIDIA provider is explicit opt-in and remains
advisory-only. P102 records exact-tool accuracy and schema failures without executing
tools or actions and does not convert benchmark output into production authority.

## P103 implemented

P103 connects the strict P102 provider contract to P101's bounded investigation
loop. Negative read-only results become sanitized history, attempted tools disappear
from the next catalog, correlated evidence stops model tool selection, and P100's
deterministic policy retains all action authority. The full offline 520-case run
retained 100% of heuristic recovery. The 52-family NVIDIA sample made 67 model
decisions, improved relevant-tool discovery from 76.92% Top-1 accuracy to 98.08%,
replanned 12 episodes, and retained the heuristic's 76.92% recovery rate with all
hard safety gates passing. P103 remains synthetic-lab evidence, not production
autonomy or operator-replacement approval.

## P104 implemented

P104 adds an Evidence Gap Investigator between the P103 diagnostic loop and P100's
deterministic action boundary. It requires fresh critical evidence, explicit
citations, no unresolved contradiction, adequate telemetry, and no unavailable
critical capability before any policy handoff. The full committed 10-case fixture
benchmark ran 150 equal-state rows across P104, P103, P101, fixed-tool, and
control arms with default network calls 0, default model calls 0, provider action
execution count 0, production mutation count 0, scorer leakage count 0, and
repeated tool count 0. P104 remains no-auth, local/mock, advisory for optional
provider use, and not production autonomy or unattended-operation approval.

## P105 active

P105 active scope: Calibrated Failure Forecast Engine with release-hardening
before any P106 action planning. P105 predicts failure family, mode, calibrated
probability, lead-time interval, impact, evidence IDs, and abstention reason
while preserving P24/P25 compatibility as legacy advisory output only.

The final-review amendment adds a concrete release-hardening tranche:
`smoke_only` and tiny-N runs can never unlock P106; `release_qualified` requires
per-supported-family held-out floors (`evaluated >= 30`, `non_abstained >= 24`,
`actual_positive >= 6`, `incident_group_count >= 4`, `service_days >= 2.0`) and
real-derived floors (`evaluated >= 20`, `non_abstained >= 16`,
`actual_positive >= 4`, `incident_group_count >= 3`, `service_days >= 1.0`),
three distinct P32/P41/P44 source record sets, no single source above 60% of a
supported family's rows, at least seven global service-days, deterministic
source-record content hashes and offsets/timestamps, outcome-neutral partitions,
per-row covered-second denominators, safety-conformance diagnostic semantics,
post-incident leakage fail-closed behavior, actual P24 RiskSignal/RiskForecast
parity, release docs/verify integration, and no auth, production mutation, or
action authority. These floors are anti-tiny-N credibility checks, not
statistical significance claims. See `docs/operations/p105-ticket-roadmap.md`
and `docs/tickets/p105/README.md`.

## P105 release integration

P105 release integration is documented, but the current committed fixture is
still a tiny `smoke_only_missing_mode` smoke fixture. P106 remains locked until
fresh generated evidence is explicitly marked `release_qualified` and passes all
held-out, real-derived, source-diversity, service-day, formula, P24 parity, and
authority-counter floors. The P105 model card and final summary are
`docs/operations/p105-model-card.md` and
`docs/operations/p105-final-summary.md`.
## P111 frozen RCA accuracy evidence

P111 implements frozen, evidence-grounded RCA accuracy improvement on the
official RCAEval RE1-OB benchmark. On the 25-case repetition-3 blind split it
improves the paired P110 baseline from 68% to 80% service Top-1 and 40% to 84%
fault accuracy while retaining 100% evidence validity and zero unsafe-action
counters. Release remains fail-closed because the predeclared service Top-1 and
loss-fault floors and cryptographic reviewer gate are not met. Repetition 4
remains an untouched reserve for a separately frozen future phase.

## P112 completed: cross-system blind release failed closed

P112 generalized RCAEval ingestion and service-agnostic localization across
Sock Shop and Online Boutique, added paired freeze/request-envelope governance,
raw-response replay evidence, strict batch merging, and a dedicated release
profile. On the newly revealed 25-case RE1-OB repetition-4 split, the frozen
P111 baseline achieved 88% service Top-1 and 100% fault accuracy. The P112 live
candidate achieved 12% for both because 88% of responses failed the strict
output contract; the underlying deterministic model reached 76% Top-1, 92%
Top-3, and 68% fault accuracy. Safety counters stayed at zero, but quality,
repeatability, paired-delta, replay, per-fault, and cryptographic gates failed.
P112 is closed without release or action authority; repetition 4 is consumed
and cannot be reused as future blind evidence.

## P113 completed: fresh-blind diagnosis failed closed

P113 separated deterministic diagnosis from optional LLM narrative generation,
pinned the official 125-case RE1-TT archive, froze source/model/prompt/code/gates,
and scored every case with evaluator-owned hidden truth. The fresh-blind result
was 31.2% service Top-1, 49.6% Top-3, and 32.0% fault accuracy. Evidence
precision, diagnosis preservation, replay consistency, and disabled action
authority were all 100%, but every accuracy family gate failed. The NVIDIA
narrative stage was therefore not run. P113 is closed as a valid negative
benchmark, not a release candidate.

## P114 complete: deterministic RE2-OB acceptance passed

P114 verifies the official 90-case RCAEval RE2-SS archive, builds immutable
metric/log evidence graphs, and separates service localization from fault
signature classification. On consumed development data the deterministic path
reached 85.56% service Top-1, 63.33% fault accuracy, 56.67% joint Top-1, 100%
joint candidate recall, and 100% evidence precision with action authority
disabled. Constrained Nano 30B, Super 120B, and Ultra 550B adjudicators all
failed the pre-blind nonnegative-delta/repeatability gate and were excluded
from the authoritative path. The separately frozen deterministic candidate
then passed the one-shot 90-case RE2-OB acceptance: 81.11% service Top-1,
94.44% Top-3, 72.22% fault accuracy, 57.78% joint Top-1, 96.67% joint candidate
recall, and 100% evidence precision/replay/diagnosis preservation. Every
required safety counter was present and zero. This qualifies bounded diagnosis,
not production remediation. See `docs/operations/p114-final-summary.md`.

## P133 complete: local dead-man outbox

P133 turns P132's independent watchdog outcomes into a crash-safe, redacted
local outbox. It opens, updates, reminds, recovers, acknowledges, and retains
local dead-man events with deterministic identity and exact-zero authority. It
does not send notifications, access credentials, call connectors, execute
remediation, or mutate staging/production. See
`docs/operations/p133-final-summary.md`,
`docs/operations/p133-local-deadman-outbox-roadmap.md`, and
`docs/tickets/p133/README.md`.

## P134 complete: observation authority contract

P134 establishes a separate `OA*` observation-authority hierarchy before any
new source attachment. OA0 denies all observation proposals; OA1 permits only
bounded synthetic local-artifact policy declarations. OA2 provider-shaped
exports, OA3 live GET shadow, and OA4 credential/external reads remain blocked
for later reviewed phases. The canonical 24-case contract/fault matrix passes,
immutable receipt-ledger semantics are re-evaluated against the exact contract,
independent source-bound review has zero unresolved P0/P1/P2 findings, and all
runtime observation/action plus evaluator authority counters remain exact zero.
P134 performs no observation or action. P135 is the next dependency.

## P135 complete: provider-shaped local export attachment

P135 implements five strict local-file adapters for Prometheus range matrices,
Loki streams, Grafana dashboards, Sentry issue lists, and OTLP metrics JSONL.
Every read is descriptor-relative and bound to a P134 OA1 receipt, expected
content hash, byte/record estimates, parser budgets, immutable execution
receipt, and normalized P120 evidence. The canonical 30/30 matrix contains five
successful provider-shaped attachments, one securely re-read duplicate, and 24
fail-closed rejection/adversarial cases. Independent review records zero
P0/P1/P2/P3 findings and all forbidden-authority counters remain integer zero.
P135 qualifies local artifacts only, not live provider attachment or action.
