# OpsCat P16 Ticket Roadmap — LLM Provider Evaluation Runner

## Requirements Summary

P16 evaluates LLM judgment providers across existing judgment cases. P16 distinguishes connection success from operational usefulness by scoring schema validity, evidence citations, route judgment, hypothesis quality, forbidden-action handling, and safety-gate outcomes. Normal verification remains mock/offline; NVIDIA is live opt-in only.

Boundary remains unchanged:

- no auth/session work;
- no default external model/API calls during normal verification;
- no committed API keys or printed secrets;
- no production mutation, Kubernetes/cloud/database execution, unrestricted shell, action execution, or unattended production-operation claim.

## P16 Tickets

### P16-001 — Provider Eval Case Scoring

**Outcome:** Implement provider eval case scoring.

**Acceptance criteria:**

- Each judgment case produces schema, citation, route, hypothesis, evidence, forbidden-action, safety, and overall scores.
- Scoring reuses P13 context and P14 judgment result.
- Scores are deterministic and redacted.

### P16-002 — Provider Eval Runner

**Outcome:** Implement provider eval runner.

**Acceptance criteria:**

- Runner evaluates a sequence of JudgmentCase objects with mock or explicit provider.
- Runner records provider, model, latency_ms, pass/fail, and per-case reasons.
- Runner does not execute actions.

### P16-003 — Mock Baseline Smoke

**Outcome:** Implement mock baseline smoke.

**Acceptance criteria:**

- Mock provider evaluation is fully offline and deterministic.
- Mock smoke runs in verify eval/full.
- Normal verification performs no NVIDIA calls.

### P16-004 — NVIDIA Live Eval Opt-in

**Outcome:** Implement nvidia live eval opt-in.

**Acceptance criteria:**

- CLI supports --provider nvidia with safe .env parsing.
- NVIDIA live eval can limit max cases.
- API key is never printed or persisted.

### P16-005 — JSON and Markdown Reports

**Outcome:** Implement json and markdown reports.

**Acceptance criteria:**

- CLI writes provider eval JSON and Markdown.
- Reports include aggregate score, pass rate, safety regressions, and failures.
- Reports include artifact paths and boundary text.

### P16-006 — Failure Analysis

**Outcome:** Implement failure analysis.

**Acceptance criteria:**

- Failed cases include reason strings.
- Unknown citations, invalid schema, unsafe allowed actions, and route mismatch are explicit.
- Markdown highlights safety regressions separately.

### P16-007 — Release Evidence

**Outcome:** Implement release evidence.

**Acceptance criteria:**

- Final summary maps P16-001 through P16-007 to code/tests/docs.
- Release evidence documents mock verify and NVIDIA opt-in commands.
- ROADMAP records P16 implemented boundary.
