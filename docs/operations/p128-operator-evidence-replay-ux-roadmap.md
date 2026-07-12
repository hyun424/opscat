# P128 Operator Evidence Replay UX Roadmap / PRD

## Objective

P128 plans an operator UX for inspecting evidence, replay, fail-closed reasons,
and verification receipts. Implementation is pending.

## Product Claim

P128 may claim only a planned local/sandbox/replay UX for evidence inspection.
It may not claim live production operations, auth completion, credentialed
access, real staging/production mutation, or operator replacement.

Required limitation: P128 is an evidence/replay inspection plan only. Auth is
deferred, credentials are out of scope, and all production/staging mutation and
credential authority counters remain zero.

## Scope

- Replay browser for P123 recorded runs.
- Quality report view for P124 denominators, slices, and failures.
- Resilience view for P125 restart, cost, and data-loss evidence.
- Disposable-lab action receipt view for P126.
- Fail-closed reason view for P127.
- Claim and limitation panel that prevents production/autonomy overclaiming.

## Non-Authority Boundary

The UX is read-only. It must not request credentials, call live connectors,
mutate staging or production, trigger remediation, run shell/subprocess
actions, execute LLM commands, or hide exact-zero authority counters.

## Tickets

1. `[planned] P128-001` - replay and evidence navigation model
2. `[planned] P128-002` - quality, resilience, and fail-closed views
3. `[planned] P128-003` - receipt provenance, counters, and limitations
4. `[planned] P128-004` - read-only UX guardrails and redaction
5. `[planned] P128-005` - verification handoff and beta dependency gate

## Gates

- Implementation may start only after all P128 planning artifacts and tickets
  are accepted.
- UX actions remain read-only and local/sandbox/replay qualified.
- Every displayed claim links to evidence or an explicit limitation.

## Executable Contract

- Service: `app/services/p128_operator_beta.py`
- Route: `app/api/operator.py` under `/operator`
- Tests: `tests/test_p128_operator_beta.py` and
  `tests/test_operator_dashboard_e2e.py`
- Runner: `scripts/run_p128_operator_beta.py`
- Verify profile: `p128-release`
- Fixture: `evals/p128/input/operator-scenarios.json`
- Outputs: `evals/p128/ux-contract.json`, `evals/p128/release-evidence.json`
- Schemas: `p128.operator_scenario.v1`, `p128.ux_contract.v1`,
  `p128.release_evidence.v1`

The UI exposes evidence IDs, hypotheses, uncertainty, policy and risk,
pre/post state, approval status, replay/report links, authority counters,
fail-closed reasons, and limitations. HTML must use semantic landmarks and
keyboard-safe links, escape untrusted content, contain no inline scripts or
secret values, expose no browser mutation form while auth is deferred, and
show a local/sandbox beta banner. A reviewer reaches each required evidence
surface in at most five links.

Verification commands are both targeted pytest files, the runner, and
`bash scripts/verify.sh p128-release`.
