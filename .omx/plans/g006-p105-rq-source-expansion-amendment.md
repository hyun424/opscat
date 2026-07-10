# G006/P105-RQ Source-Expansion Amendment Plan

Plan source: `docs/operations/p105-g006-source-expansion-amendment.md`.
Test-spec source:
`docs/operations/p105-g006-source-expansion-test-spec-amendment.md`.

## Scope

Documentation-only amendment for G006/P105-RQ. No production or test code is
changed by this planning artifact.

## Deliverables

1. Add source-expansion amendment and test-spec amendment.
2. Add P105-023 through P105-029 macro tickets.
3. Update P105 roadmap and ticket index so executors have one macro sequence:
   plan review -> RED contract tests -> adapters/harness -> actual runs ->
   release benchmark -> independent code and architecture review -> full
   verify -> only then P106.

## Acceptance

- Current exact P105 floors remain unchanged.
- Unsupported-family rows are non-counting.
- DejaVu A1, Apache/Hadoop/Zookeeper parsers, queue harness, and deploy harness
  have concrete command and artifact boundaries.
- Source registry production has an exact owner, schema, output paths, command,
  and downstream consumer boundary.
- Queue and deploy harnesses have exact fixed seeds, clocks, schedules,
  partition/sampling rules, output paths, byte-identical rerun checks, and
  tamper checks.
- A1 counts only seven relevant db-connection-limit incidents; if 4+3 incident
  groups cannot be reproduced from reviewed bytes, the plan requires another
  honest reviewed database source instead of cloning.
- `command_argv`, `created_at`, reviewed registry, eligibility manifest,
  provenance, privacy, license, reproducibility, and stop conditions are
  specified.
- No synthetic padding, label leakage, post-label partitioning, heuristic
  family authority, fabricated coverage, production mutation, or credential
  reads are allowed.

## Verification

Documentation-only validation:

```bash
git diff --check
UV_CACHE_DIR=/private/tmp/opscat-uv-cache bash scripts/verify.sh --profile docs
```
