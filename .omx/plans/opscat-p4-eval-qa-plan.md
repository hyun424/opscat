# OpsCat P4 Eval/QA Plan — Operator-Replacement Trust Evidence

## Requirements summary

OpsCat already has a green local/mock P3 foundation: async webhook queueing, immutable action attempts, connector idempotency, and an operator dashboard. P4 must prove the product promise with repeatable evidence: OpsCat should handle known routine incidents, escalate uncertain/risky cases, redact unsafe data, and generate a portfolio-ready evaluation report without external credentials.

## RALPLAN-DR summary

### Principles

1. Evaluation evidence is a product surface, not just tests.
2. Unknown, unsafe, or unverifiable incidents must escalate rather than silently pass.
3. Fixtures must cover both happy paths and adversarial/noisy operational reality.
4. Keep P4 local/mock-only; do not introduce live provider dependencies.
5. Reports must be deterministic enough for CI and portfolio demos.

### Decision drivers

1. Recruiter/customer trust: show how OpsCat is judged, not only that it runs.
2. Safety: detect false auto-resolution, missing escalation, secret leakage, and wrong policy decisions.
3. Maintainability: fixture schema and runner should be simple stdlib/Python surfaces integrated with pytest and `verify.sh`.

### Viable options

- Option A: Pytest-only golden tests. Fast and simple, but weak as a product artifact because it lacks a readable eval report.
- Option B: Dedicated eval runner plus pytest contracts. Chosen. Produces CI-readable JSON/Markdown while tests enforce schema and decisions.
- Option C: Add an external eval framework. Rejected for P4 because it adds dependency and obscures the deterministic local/mock story.

## ADR

### Decision

Build a first-class local eval harness around `evals/golden/*.json`, `scripts/run_evals.py`, and generated JSON/Markdown reports. Expand the golden corpus from 4 to 20 scenarios, including adversarial and no-silent-failure cases.

### Drivers

- Portfolio needs evidence that resembles production model/eval practice.
- Paid-beta readiness needs a repeatable safety gate.
- Existing deterministic agent makes local evals cheap and reliable.

### Alternatives considered

- Pytest-only: rejected because it does not create stakeholder-facing eval evidence.
- External eval service/framework: rejected because P4 must stay local, deterministic, and dependency-light.
- UI-only QA next: rejected because dashboard polish is less important than proving operational judgment.

### Consequences

- New scenario additions require fixture + expectation updates.
- The eval runner becomes a release artifact and should remain stable/CLI-friendly.
- Some scenarios will initially map to existing deterministic branches until richer agent logic is added.

## Acceptance criteria

1. At least 20 golden fixtures exist under `evals/golden`.
2. Each fixture declares input alert, expected cause substring, acceptable actions, policy decision, minimum evidence count, required post-checks, expected final route, and safety flags.
3. A stdlib CLI `scripts/run_evals.py` runs all or selected scenarios in-process without external credentials.
4. Runner emits machine-readable JSON and human-readable Markdown reports.
5. Runner fails non-zero when any scenario mismatches expected policy/action/evidence/route/redaction.
6. Pytest covers fixture schema, runner summary, report output, and at least one failure-path eval.
7. `bash scripts/verify.sh` includes the eval runner gate.
8. Docs explain how eval evidence supports “operator replacement” claims and list remaining eval gaps.

## Implementation phases

### Phase A — RED contracts

Files:
- `tests/test_eval_runner.py`
- `tests/test_golden_evals.py`

Tests:
- require >=20 fixtures;
- require richer fixture fields;
- assert `scripts.run_evals.run_evals()` returns pass/fail counters and per-scenario records;
- assert Markdown/JSON outputs are written;
- assert a deliberately impossible expectation fails cleanly.

### Phase B — Fixture expansion

Files:
- `evals/golden/*.json`

Add scenarios covering:
- bad deploy variants;
- DB pool/latency-like symptom;
- external timeout;
- worker backlog/poison-like symptom;
- duplicate/recovered alert;
- low-confidence ambiguity;
- missing runbook;
- protected auth/security/data domains;
- verification failure;
- prompt-injection-like log text;
- secret-bearing alert text;
- stale alert;
- conflicting evidence;
- critical severity escalation.

### Phase C — Runner implementation

Files:
- `scripts/run_evals.py`

Behavior:
- create isolated in-memory SQLite DB per scenario;
- exercise `create_and_investigate()` directly for deterministic sync evaluation;
- evaluate cause/action/policy/post-check/evidence/route/redaction;
- optionally approve actions when fixture says expected terminal route requires execution;
- write JSON and Markdown summaries;
- exit non-zero on failure when invoked as CLI.

### Phase D — Release integration and docs

Files:
- `scripts/verify.sh`
- `docs/integration-verification.md`
- `docs/portfolio-summary.md`
- `docs/operations/production-ai-team-plan.md`

Add eval gate to release verification and document latest eval coverage.

## Plan review / self-critique

- Risk: 20 fixtures could be shallow duplicates. Mitigation: schema includes category/safety flags and expected route so each fixture proves a different behavior axis.
- Risk: runner duplicates pytest. Mitigation: pytest enforces runner contracts; runner creates stakeholder-facing reports.
- Risk: direct service evaluation bypasses HTTP auth. Mitigation: P4 runner targets agent judgment and safety decisions; dashboard/API auth remains covered by existing API tests.
- Risk: false confidence from deterministic mock agent. Mitigation: docs explicitly call these local/mock evals and leave live connector/model evals for P6+.

## Verification steps

1. RED: `uv run --no-sync --extra dev pytest tests/test_eval_runner.py tests/test_golden_evals.py -q` fails for missing runner/fixture count.
2. GREEN targeted: same command passes.
3. Eval CLI: `uv run --no-sync --extra dev python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md` passes.
4. Static/regression: compileall, Ruff, mypy, pytest.
5. Release: `bash scripts/verify.sh` passes.

## Stop condition

P4 slice is complete when the eval corpus is >=20 scenarios, runner/report tests pass, release gate includes evals, docs reflect current verified behavior, and a Lore GREEN commit is created.
