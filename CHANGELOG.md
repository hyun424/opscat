# Changelog

All notable OpsCat local/mock release evidence changes are tracked here.

## Unreleased

### P5 OSS productization

- Added open-source quickstart, example environment, contributor docs, and safe issue templates.
- Added connector catalog permission previews, connector SDK docs, local fixture examples, and API docs.
- Added metadata-only secret lifecycle APIs and fixture incident import normalization.
- Added workflow CLI stats/drain/dead-letter operations.
- Added approval console action previews without browser mutation forms because auth deferred remains the P5 boundary.
- Added Night Autopilot policy audit endpoint and morning report evidence.
- Added self-observability metrics and CI verification profiles.
- Added OSS security policy and safe disclosure docs.
- Added release packaging docs, deployment dry run, and versioned evidence instructions.

### P4 evidence

- Local/mock incident agent loop with deterministic evals.
- Policy-gated mock actions with approval, execution attempt records, verification, escalation, and reports.
- Connector failure/idempotency evals proving fail-closed behavior.
- Server-rendered operator dashboard and release evidence index.

### P98 selector evaluation

- Added blind causal comparison for rule-based, observation-only, and LLM-shaped selectors over the P97 operational scenario matrix.
- Added explicit opt-in NVIDIA advisory adapter with fail-closed parsing and no action authority.
- Added measured selector safety, recovery, escalation, and runbook-regret evidence; results remain synthetic-lab-only.

### P99 operational failure matrix

- Expanded causal coverage to 52 operational families and 520 cases across infrastructure, data, network, dependency, workload, security, and regional failures.
- Added 40 new closed-registry local lab actions and visible approval boundaries for high-risk families.
- Added broad matrix CLI, measured 140,400-request evidence, and release verification contracts.

### P100 stateful incident investigator

- Added bounded observe-act-verify-adapt sessions with sanitized history and a three-step budget.
- Added failed-first-action fallback, partial/compound completion, natural-recovery restraint, and safe escalation gates.
- Added a four-arm 520-case benchmark with 6,240-trial evidence: 56.47% stateful recovery versus 34.55% one-shot and 39.42% blind recovery versus 2.88%.
- Corrected required/runbook versus harmful-action overlap in the original scenario generator and locked catalog consistency with regression tests.
- Added release evidence and verification smoke while preserving the loopback-only, in-memory, no-production-mutation boundary.

### P101 tool-using hypothesis investigator

- Added executed read-only diagnostics, symptom-derived tool hypotheses, negative-result demotion, and evidence-gated P100 action delegation.
- Added a three-arm hidden-evidence benchmark with 100% relevant-tool discovery, 94.23% Top-1 accuracy, and 100% recovery retention over 4,680 trials.
- Added fixed-tool ablation, safety gates, CLI reports, release evidence, and verification integration.

### P102 LLM diagnostic tool planner evaluation

- Added a provider-neutral, exact-JSON diagnostic planner over the closed P101 read-only tool registry.
- Added original, paraphrased, opaque-topology, and prompt-injection-like evaluation variants.
- Added deterministic offline and explicit opt-in NVIDIA scorecards with strict fail-closed validation and zero action authority.
- Added targeted safety tests, CLI reports, release evidence, and verification integration.

### P103 multi-step LLM diagnostic episode

- Connected provider-neutral LLM tool selection to the bounded P101 investigation loop.
- Added negative-result replanning, attempted-tool removal, explicit tool budgets, repeated-tool prevention, and provider-failure escalation.
- Kept positive-evidence remediation behind P100's deterministic closed-registry policy with zero provider action authority.
- Added equal-state fixed/heuristic/LLM comparisons, strict and outcome-based metrics, bounded NVIDIA evaluation, and release verification.

### P104 evidence gap investigator

- Added deterministic evidence sufficiency gates for missing, stale, contradicted, unavailable, duplicate, and valid-absence evidence states before policy handoff.
- Added network-free CLI benchmark evidence over the full committed 10-case P104 fixture with P104/P103/P101/fixed-tool/control equal-state comparisons.
- Added release evidence and verification integration while preserving no auth, no production mutation, no provider action authority, and default external calls at zero.

### P105 planning hardening

- Planned P105 release-hardening tickets P105-012 through P105-015 after review
  identified tiny-fixture gate credibility gaps.
- Planned explicit `smoke_only`/`release_qualified` mode semantics with
  missing-mode normalization to `smoke_only_missing_mode`, default-false
  release/P106 status, anti-tiny-N held-out and real-derived floors,
  P32/P41/P44 source-record provenance, unioned service-day exposure
  denominators, outcome-neutral partitioning, private-harness-only diagnostic
  leaks, post-incident leakage fail-closed behavior, actual P24 parity, release
  docs/verify integration, and continued no auth, no production mutation, and no
  action authority.

### P105 release integration

- Added P105 model-card and final-summary docs that explicitly mark the
  committed tiny fixture as `smoke_only_missing_mode` evidence and keep P106
  locked until generated `release_qualified` evidence exists.
- Documented P105 qualification floors, metric formulas, P32/P41/P44
  source-record provenance scope, union service-day denominator rules, actual
  P24 `RiskSignal`/`RiskForecast` parity, model limitations, and no-auth,
  no-production-mutation, no-action-authority boundaries.
- Wired P105 benchmark smoke and release evidence anchors into verification
  documentation while preserving default offline, local/mock execution.

## Stable vs experimental

Stable in local/mock mode: tests, evals, fixture ingestion, local-header demo identity, mock action policy gates, connector evals, docs, and verification profiles.

Experimental: production deployment, real connector credentials, OAuth, auth/session UI, external metrics export, hosted workflow infrastructure, and real customer production use.

## P6 agentic loop

- Added deterministic correlation, root-cause ranking, runbook planning, risk routing, safe action metadata, recovery verification evidence, decision traces, agentic eval runner, and one-command local demo.
