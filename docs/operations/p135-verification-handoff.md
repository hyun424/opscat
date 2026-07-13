# P135 Verification Handoff

## Canonical command

```bash
UV_CACHE_DIR=/tmp/opscat-uv-cache bash scripts/verify.sh --profile p135-release
```

## Expected result

- 46 targeted P135 tests pass;
- targeted Ruff and Mypy pass;
- the real 30-case matrix passes with 5 successes, 1 duplicate, and 24
  fail-closed rejections;
- all five providers are represented exactly once;
- independent review has zero P0/P1/P2/P3 findings;
- all release gates are true;
- every forbidden-authority counter is exact integer zero;
- status is `p135_provider_shaped_export_attachment_qualified`;
- release evidence hash is
  `sha256:ab78a5757fecd5d52f3d2e698e97625f192b0cb8aecac54bda5e0a87e6d70ba7`.

## Promoted artifacts

- `evals/p135/case-matrix.json`
- `evals/p135/authority-ledger.json`
- `evals/p135/execution-ledger.json`
- `evals/p135/normalized-bundles.json`
- `evals/p135/independent-review.json`
- `evals/p135/release-evidence.json`

The release validator rehashes the current implementation, runner, tests,
profile, plan, fixtures, and P135 tickets. Editing any bound source requires a
new independent review artifact and canonical run.

## Preserved limits

Do not interpret P135 as authorization for credentials, environment reads,
provider APIs, network/DNS/socket access, subprocesses, shell commands,
notification delivery, remediation, staging/production mutation, or operator
replacement. Those surfaces remain exact-zero and fail closed.
