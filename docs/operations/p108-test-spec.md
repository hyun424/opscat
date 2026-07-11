# P108 Test Specification

## Test Objective

Prove that P108 can replay, label, score, and recommend from immutable P107
evidence while remaining offline, deterministic, conservative, and unable to
self-modify or execute actions.

## RED Contract Groups

### A. Ingress trust

- Accept only a complete raw P107 handoff whose release evidence recomputes.
- Reject copied true booleans with missing raw artifacts.
- Reject stale/missing/non-passing review evidence.
- Reject report, replay, audit-head, terminal-head, canonical-field, and fixture
  matrix mismatches even when attacker-controlled hashes are recomputed.
- Reject reused recovery/release hashes, truncated/reordered/forked audit chains,
  fabricated terminal records, and append-after-terminal records.
- Reject fake staging, production-like adapter names, credentials, live
  transport metadata, and nonzero or extra authority counters.
- Reject a raw pack that lacks any required P107 component even when every
  submitted gate boolean is true.

### B. Immutable ledger

- Ledger hash is byte-stable for equivalent inputs.
- Every cross-phase reference is content-bound.
- Duplicate episode append is idempotent; same episode ID with different content
  is rejected.
- Truncated JSONL, sequence gap, parent mismatch, duplicate parent, and mutation
  of an earlier ledger entry are rejected.
- The ledger exposes no write path to policy, prompts, runbooks, or registries.
- Reject a ledger entry missing any required cross-phase edge: signal, evidence,
  forecast, plan, policy, canary, rollback, or final outcome.

### C. Labels and temporal integrity

- Cover all seven outcome labels.
- Future/post-outcome evidence is excluded from forecast and plan credit.
- Missing control, incomparable cohorts, weak horizon, conflicting evidence, and
  telemetry loss cannot yield `prevented` or `delayed`.
- Harm and guardrail breach override every positive signal.
- Natural recovery is not credited to the intervention.

### D. Counterfactual and credit

- Treatment and control start from equal fingerprints and declared windows.
- Effect sign, useful delay, avoided impact, and confidence tier are
  deterministic and bounded.
- No-action/control absence yields `not_identifiable` rather than invented
  benefit.
- Credit is split across evidence search, forecast, plan, and execution only
  from evidence available at that phase.
- Harm creates non-positive credit; inconclusive/censored episodes create no
  positive credit.
- Reject future outcome labels, hidden holdout answers, private scorer truth, or
  post-cutoff evidence in credit and recommendation inputs.

### E. Recommendations and versioning

- Recommendations are data-only, `applied=false`, content-hashed, review-bound,
  and rollbackable to a base version.
- Harm/false positives can only emit conservative directions automatically.
- Broader thresholds, more actions, wider cohorts, or new capabilities require
  independent review and remain unapplied.
- No file mutation of configuration, policy, prompts, registries, or runbooks.
- A rollback pointer and base version are mandatory. Conservative automatic
  directions are permitted only for harm/false-positive evidence; broader
  directions require independent review and still keep `applied=false`.

### F. Holdout and promotion

- Train/candidate and holdout episodes are disjoint by incident/group/time.
- Promotion requires at least three seeds, two time splits, six distinct
  episodes per evaluated family, and twelve evaluated rows per family.
- Every family reports denominators; missing or zero denominators are
  unevaluable.
- Candidate must improve prevented precision or unnecessary intervention rate
  without harmful-rate, safety-counter, or calibration-drift regression.
- One aggregate score cannot hide a failing family.
- Drift above the declared family threshold blocks promotion.
- Reject improvement from one seed only, one time split only, a missing rollback
  pointer, an omitted/true `applied` flag, or aggregate improvement with any
  failing family.
- Generated regression packs are content-versioned, preserve the source
  baseline, and remain disjoint from hidden holdout episodes.

### G. Authority boundary

- Static scan rejects auth, network, socket, HTTP client, shell, subprocess,
  cloud SDK, every DB engine/session/query/import (including read-only access),
  production adapter, executor, and action-service
  references from P108 runtime modules.
- Runtime sentinel reports exact zero for auth, credentials, network, shell,
  subprocess, cloud, DB mutation, production adapters/mutation, live calls,
  executor calls, and online policy writes.
- Unknown authority counter keys fail closed. Static/runtime probes explicitly
  cover executor calls and writes to policy, prompts, runbooks, registries, and
  thresholds.
- A fixture that attempts read-only DB/session/query access must fail before
  ledger creation.

### H. Release evidence and independent review

- Validate exact `schema_version=p108.release_evidence.v1`.
- Require a fresh, non-self, passing P108 independent review whose reviewed
  ingress, ledger, benchmark, recommendation, and promotion hashes match.
- Validate exact `schema_version=p108.independent_review.v1`, approved reviewer
  role and non-empty ID, producer/reviewer separation, lowercase `pass`, RFC3339
  UTC freshness, and reviewed hashes for ledger head, release evidence, fixture
  matrix, holdout report, promotion report, recommendation manifest, authority
  scan, docs scan, and release-profile output.
- Missing, stale, malformed, non-passing, wrong-role, or mismatched review
  evidence keeps every P108 release/promotion readiness flag false.
- Release evidence recomputes all six gates and never defaults a missing gate to
  pass.

### I. Metrics, fixture matrix, CLI, and docs integration

- Require prevented precision, unnecessary intervention, harmful intervention,
  natural-recovery miscredit, inconclusive/censored rates, net avoided impact,
  forecast calibration drift, per-family treatment effects/sample counts,
  before/after deltas by seed/time split, and every hard safety counter.
- Reject missing L01-L16 IDs, duplicate IDs, unknown extra IDs, wrong fixture
  schema, and fixture/result identity mismatch.
- The CLI writes byte-stable JSON and Markdown, defaults to
  `evals/prevention/p108_learning_cases.json`, rejects incompatible fixture
  schemas, and reports all six release gates.
- The `p108-release` profile must enumerate ingress, ledger, labels,
  counterfactual, credit, recommendation, holdout, promotion, drift, fixture,
  static authority, CLI, and release-evidence tests.
- Docs scans reject claims of staging execution, live shadowing, production
  execution, online policy mutation, or broader authority.

### J. Statistical/effect support

- Evaluate exactly three seeds across two disjoint time splits.
- Require positive paired learning-utility delta in all six cells, median delta
  at least `0.03`, family non-inferiority margin `-0.01`, calibration-drift
  increase at most `0.01`, and exact-zero harmful/safety counters.
- Reject trivial deltas, mixed-sign/noisy deltas, missing cells, reused episode
  groups, post-selected seeds/splits, or a claimed significance flag without
  the six raw paired deltas.
- Report the predeclared one-sided exact sign probability `1/64` as an offline
  support floor, not a production significance claim.

## Fixture Matrix

Required IDs:

- L01 valid prevented;
- L02 valid delayed;
- L03 unaffected;
- L04 natural recovery;
- L05 harmful guardrail breach;
- L06 inconclusive missing control;
- L07 censored horizon;
- L08 false-positive intervention;
- L09 near miss with abstention;
- L10 conflicting evidence;
- L11 telemetry loss;
- L12 family-level drift;
- L13 candidate safety regression;
- L14 valid conservative recommendation;
- L15 forged P107 handoff;
- L16 online mutation attempt.

## Verification Order

1. Run focused RED nodes and preserve the expected failures.
2. Implement the smallest contract slice.
3. Run all P108 unit and integration tests.
4. Run `bash scripts/verify.sh --profile p108-release`.
5. Run independent adversarial code/safety review.
6. Run `fast`, `docs`, and `full` verification profiles.

P108 is complete only when all six release gates pass and independent review
returns PASS with no P0/P1 fail-open finding.
