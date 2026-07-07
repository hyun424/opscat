# OpsCat P10 Ticket Roadmap — Incident Judgment Benchmark

## Requirements Summary

P10 makes OpsCat's incident-response judgment measurable. P9 built a local/mock Autonomous Incident Commander. P10 adds a benchmark layer that turns external-style logs, metrics, and synthetic incidents into standardized OpsCat judgment cases, runs the commander, scores the output against a rubric, and reports regressions.

Boundary remains unchanged unless explicitly reopened by the owner:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, customer credentials, or hosted SaaS claims;
- no external dataset download required for normal verification;
- seed datasets are small, repo-local, redacted, license-safe examples inspired by public formats;
- automatic actions remain local/mock, allowlisted, policy-gated, simulated, audited, reversible, and test-backed.

## P10 Goal

Build a credible **Incident Judgment Benchmark** where OpsCat can:

1. represent external dataset samples as standard judgment cases;
2. import LogHub-like logs and NAB-like metric windows into OpsCat cases;
3. define expected hypotheses, required evidence, forbidden actions, expected routes, and verification criteria;
4. score commander output across diagnosis, evidence, safety, action route, verification, and explanation;
5. run a bounded benchmark from CLI;
6. compare against a baseline;
7. produce markdown/JSON reports for portfolio review and future model/prompt improvements.

## P10 Tickets

### P10-001 — Judgment Dataset Schema

**Outcome:** Define a stable schema for benchmark cases, rubric, and score results.

**Acceptance criteria:**

- Case schema includes incident, signals/evidence, expected hypotheses, required evidence, forbidden actions, expected route, verification criteria, and tags.
- Output schema is deterministic, JSON-serializable, redacted, and local/mock only.
- Validation rejects empty case IDs and missing expected routes.

### P10-002 — LogHub-style Adapter

**Outcome:** Convert LogHub-like log rows into OpsCat judgment cases.

**Acceptance criteria:**

- Adapter accepts repo-local JSONL/CSV style rows without network calls.
- Anomaly/error lines become evidence and expected hypothesis hints.
- Prompt/log injection markers create forbidden-action and safety expectations.

### P10-003 — NAB-style Metric Adapter

**Outcome:** Convert NAB-like timestamp/value windows into metric judgment cases.

**Acceptance criteria:**

- Adapter calculates baseline, anomaly ratio, stale/no-data/partial states.
- Anomaly windows become expected routes and verification criteria.
- No-data is classified as insufficient evidence, not healthy.

### P10-004 — Judgment Rubric Format

**Outcome:** Define scoring rubric primitives.

**Acceptance criteria:**

- Rubric supports expected root causes, required evidence, forbidden actions, expected route, verification, and explanation keywords.
- Rubric can be embedded in seed fixture files.
- Rubric can express human_required and blocked routes.

### P10-005 — Commander Judgment Evaluator

**Outcome:** Score P9 commander output against benchmark rubrics.

**Acceptance criteria:**

- Scores diagnosis, evidence, safety, action route, verification, and explanation.
- Safety hard-fails when forbidden actions are suggested or unsafe routes pass.
- Returns per-case reasons and overall weighted score.

### P10-006 — Dataset Conversion CLI

**Outcome:** Convert seed external-style datasets into benchmark cases.

**Acceptance criteria:**

- CLI supports `--source loghub` and `--source nab` over repo-local fixtures.
- CLI writes deterministic JSON cases.
- CLI refuses unknown sources and does not download data.

### P10-007 — Judgment Benchmark Runner

**Outcome:** Run cases through the commander and evaluator.

**Acceptance criteria:**

- Runner loads seed cases, runs commander, scores each case, and emits JSON/Markdown.
- Includes smoke command suitable for full verification.
- Output includes overall, diagnosis, safety, action, verification, and regression fields.

### P10-008 — Regression Baseline

**Outcome:** Compare benchmark output to a baseline.

**Acceptance criteria:**

- Baseline comparison identifies improved, unchanged, regressed, and safety-regressed cases.
- Safety regression is called out separately from normal score drift.
- Missing baseline is handled as first-run mode.

### P10-009 — Benchmark Report

**Outcome:** Generate a reviewer-friendly markdown report.

**Acceptance criteria:**

- Report lists scenario scores, weak dimensions, safety blocks, and improvement hints.
- Report states local/mock/no-auth boundary.
- Report is redacted.

### P10-010 — Seed Dataset Pack

**Outcome:** Add small built-in benchmark fixtures.

**Acceptance criteria:**

- Includes LogHub-like API/deploy/log-injection samples.
- Includes NAB-like spike/no-data/stale metric samples.
- Includes synthetic false-recovery and conflicting-signal cases.

### P10-011 — Verification Integration

**Outcome:** Add benchmark smoke to verification.

**Acceptance criteria:**

- `scripts/verify.sh --profile full` runs a bounded judgment benchmark smoke.
- `scripts/verify.sh --profile eval` includes the benchmark.
- Docs profile validates P10 release evidence.

### P10-012 — P10 Release Evidence

**Outcome:** Close P10 with reproducible evidence and roadmap updates.

**Acceptance criteria:**

- Final summary maps P10-001 through P10-012 to code/tests/docs.
- Release evidence includes benchmark commands and artifacts.
- `bash scripts/verify.sh --profile full` passes before closure.

## Execution Order

1. P10-001 Judgment Dataset Schema
2. P10-004 Judgment Rubric Format
3. P10-002 LogHub-style Adapter
4. P10-003 NAB-style Metric Adapter
5. P10-005 Commander Judgment Evaluator
6. P10-006 Dataset Conversion CLI
7. P10-007 Judgment Benchmark Runner
8. P10-008 Regression Baseline
9. P10-009 Benchmark Report
10. P10-010 Seed Dataset Pack
11. P10-011 Verification Integration
12. P10-012 Release Evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P10 closure.
