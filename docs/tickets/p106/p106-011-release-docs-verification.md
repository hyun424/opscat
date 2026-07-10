# P106-011 - Release Documentation and Verification Integration

## Goal

Document P106 release evidence and wire a local/offline smoke into verification
without weakening existing checks.

## Contract

- Release docs list P106 metrics, zero authority counters, benchmark command,
  target tests, safety boundary, and stop condition.
- `scripts/verify.sh --profile docs` includes the P106 release-evidence
  contract test.
- `scripts/verify.sh --profile eval` and the default full profile include the
  offline preventive-action benchmark smoke, which safely extracts the
  SHA-pinned real-derived P105 archive into a fresh temporary directory and
  passes the extracted rows artifact with `--p105-artifact`.
- P107 is documented as blocked unless the full conjunction passes:
  shared fail-closed coverage, exact zero harmful actions, and simulation-only
  mutation-plan evidence.

## Acceptance

Docs must not claim auth, production mutation, live remediation execution, LLM
authority, or P107 unlock from P106 alone.

Fresh smoke evidence must assert `scored=true`, one eligible planner
evaluation, zero regret and harm, `1.0` safe-fallback and fail-closed rates, one
mutation-shaped simulation-only plan, and exact zero authority.
