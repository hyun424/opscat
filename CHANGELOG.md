# Changelog

### P111 evidence-grounded RCA accuracy

- Added a frozen multi-stage diagnosis pipeline that combines NVIDIA evidence
  analysis with a deterministic fault prior trained only on earlier repetitions.
- On the 25-case repetition-3 blind split, improved the paired P110 baseline
  from 68% to 80% service Top-1, 88% to 96% Top-3, and 40% to 84% fault
  accuracy, with 100% evidence validity and zero unsafe-action counters.
- Added configuration/source/request hashing, blind-role guards, preserved raw
  response replay, paired comparison, calibration, and repeat-agreement gates.
- Kept release qualification closed: service Top-1 was below 84%, loss-fault
  accuracy was below 60%, and no cryptographic independent reviewer exists.

### P110 labeled real-data LLM diagnosis

- Added safe import and hidden-truth isolation for the official 125-case
  RCAEval RE1-OB dataset, with a balanced 25-case holdout.
- Added strict mock/replay/NVIDIA candidate execution, source-bound evidence
  citations, budgets, response hashing, and zero action authority.
- Recorded a provenance-hardened Nemotron rerun of 80% service Top-1, 92%
  Top-3, 52% fault accuracy, and 100% citation validity on the holdout;
  disk/loss classification remains weak.
- Added bootstrap intervals, per-service/per-fault cells, fail-closed release
  evidence, independent-review requirements, and a `p110-release` profile.
- Added sealed scorer-truth/source bindings, cache-keyed replay, strict batch
  provenance, evaluator-owned action-risk scoring, and adversarial regressions
  after the first independent implementation review rejected the release path.
- Preserved and replayed raw provider responses during merge, and kept hard
  release qualification closed because local JSON review is not cryptographic
  proof of reviewer identity or live provider execution.
- Added sealed scorer-truth/source bindings, cache-keyed replay, strict batch
  provenance, evaluator-owned action-risk scoring, and adversarial regressions
  after the first independent implementation review rejected the release path.

### P109 real operations evidence benchmark

- Added versioned, fail-closed contracts for immutable external source
  provenance, RCAEval normalization, and externally executed
  MicroRemed-compatible result bundles.
- Added a pinned, checksummed public Baro/RCAEval metric sample for real-source
  parser validation. It has no authoritative root-cause labels and therefore
  cannot qualify diagnosis accuracy or a real-data release.
- Added diagnosis and remediation metrics with explicit numerator/denominator
  semantics, hidden scorer truth, independent verifier requirements,
  contamination gates, deterministic reports, and a zero-execution-authority
  boundary.

All notable OpsCat local/mock release evidence changes are tracked here.

## Unreleased

### P137 local evidence-to-incident triage

- Added a P136-owned sequenced fixed-path handoff publisher and P137 validator
  over current P136 authority, checkpoint, promotion, canonical-byte, review,
  and release contracts.
- Added exact evidence atoms, deterministic incident correlation, closed
  hypotheses with integer semantic ranking, a 15-operation local-only evidence
  request catalog, terminal classifications, and a CAS-chained investigation
  ledger.
- Added nonblocking process leasing, atomic/fsynced state, checkpoint lineage,
  crash replay, finite continuous mode, heartbeat/readiness/termination records,
  and exact-zero forbidden authority.
- Added a source-bound 60-case release matrix and dedicated `p137-release`
  verification profile with complete case-input/probe and fixture-tree content
  freezes, explicit per-case effective-config hashes, scenario-authored
  evaluator expectations rederived from frozen input oracles, and independent
  resource budgets.
- Added exact real-P136 atom ingestion for named Grafana/Loki integration cases
  while explicitly retaining the remaining rows as source-bound component
  fixtures with no P136 or live-provider authenticity claim.
- Added self-hash/link validation for publisher state and pending intent before
  mutation, plus semantic durable-state recovery that revalidates atom domains
  and deterministically re-executes persisted evidence-request selection.
  Auth, credentials, provider/network access, notification, action,
  remediation, and production mutation remain excluded.

### P131 always-on local monitor

- Added a standalone monotonic-cadence local JSONL monitor with bounded reads,
  atomic hash-verified checkpoints, lease protection, rotation handling, and
  restart-safe duplicate suppression.
- Added independent watchdog and HTTP liveness/readiness surfaces for missing,
  stale, future, malformed, and tampered state plus source freshness and canary
  degradation.
- Added deterministic P131 runtime/watchdog/release evidence and a dedicated
  verification profile with exact-zero P121 authority.
- Kept direct live connectors, auth, credentials, network calls, subprocesses,
  remediation, staging mutation, and production mutation out of P131.

### P121 proactive prevention readiness

- Added durable local-sandbox L3 execution with WAL/hash-chain recovery,
  `flock`, CAS/idempotency, leases, partial-L3 replay, rollback recovery, and
  tamper detection while preserving exact-zero production authority.
- Replaced pre-scored frozen rows with raw visible inputs and scorer-only
  hidden truth; the evaluator now derives predictions/outcomes and enforces
  system, temporal, and near-duplicate leakage checks.
- Regenerated P121 frozen evaluation and release evidence for 360 cases with
  15 crash/replay recovery points.

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

### P106 documentation and release verification

- Added P106 ticket docs, roadmap, planning-review ledger, and final-summary
  structure for the simulation-only preventive action planner.
- Documented canonical P105 prerequisite validation, P104 sufficiency,
  shared registry/policy/simulator/blast/memory composition, optional advisory
  LLM limits, and the P107 conjunctive gate.
- Wired the local/offline P106 benchmark smoke into the eval/full verification
  path with SHA-pinned extraction of the real-derived P105 fixture, and added
  the P106 docs contract test to the docs profile.
- Recorded fresh scored evidence: one eligible planner evaluation, zero regret
  and harm, `1.0` safe-fallback and fail-closed rates, one mutation-shaped
  simulation-only plan, and exact zero authority.
- Recorded prior verifier findings as fixed. P107 gate evidence is eligible,
  but P106 grants no execution authority; final independent implementation code
  and architecture/safety review remain pending.

### P107 docs and verification integration

- Added P107 roadmap and ticket index for the local/mock or isolated canary
  prevention executor release lane.
- Documented exact zero authority: no auth, production adapters, credentials,
  network calls, shell execution, cloud mutation, database mutation, or
  production mutation.
- Documented P106 eligibility as evidence only: P107 recomputes the canonical
  P106 gate, while P106 keeps `p107_unlocked=false`.
- Added the `p107-release` verification profile with all 15 P107 release test
  files and the canary evidence CLI smoke, without removing P105/P106 gates.
- Documented the P108 deterministic replay handoff and the requirement for
  matching fresh independent review JSON before `p108_replay_gate_ready=true`.

### P108 deterministic prevention outcome learning

- Added raw P107 ingress recomputation, an immutable content-linked outcome
  ledger, seven conservative outcome labels, counterfactual scoring, and
  phase-bounded credit assignment.
- Added data-only recommendations with `applied=false`, rollback/version
  bindings, six-cell holdout promotion gates, per-family drift/safety checks,
  and exact-zero offline authority enforcement.
- Added the L01-L16 learning fixture matrix, deterministic JSON/Markdown CLI,
  `p108-release` verification profile, and fresh non-self independent-review
  hash contract.

## Stable vs experimental

Stable in local/mock mode: tests, evals, fixture ingestion, local-header demo identity, mock action policy gates, connector evals, docs, and verification profiles.

Experimental: production deployment, real connector credentials, OAuth, auth/session UI, external metrics export, hosted workflow infrastructure, and real customer production use.

## P6 agentic loop

- Added deterministic correlation, root-cause ranking, runbook planning, risk routing, safe action metadata, recovery verification evidence, decision traces, agentic eval runner, and one-command local demo.
