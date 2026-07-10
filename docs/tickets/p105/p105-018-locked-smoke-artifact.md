# P105-018 - Locked Smoke Artifact

## Goal

Create a locked smoke artifact that proves wiring and formula behavior without
ever being eligible for release qualification or P106 unlock.

## Tests First

- Add RED tests requiring smoke artifacts to use `smoke_only` or
  `smoke_only_missing_mode`.
- Add RED tests proving tiny-N, hand-computed, fixture-only, and missing-mode
  runs always keep `release_qualified=false` and `p106_unlocked=false`.
- Add RED tests proving smoke artifacts cannot be promoted by editing only
  mode metadata, file names, or manifests.
- Add RED tests requiring smoke stop conditions to appear in release docs.

## Implementation Notes

- Keep smoke evidence useful for local formula, leakage, and docs checks.
- Store smoke manifests and hashes separately from qualified artifacts.
- Do not reuse smoke hashes in qualified evidence.

## Acceptance

- Smoke evidence remains deterministic and local/offline.
- Smoke evidence is visibly locked and cannot satisfy release floors.
- Release docs name the smoke artifact as wiring evidence only.
- P106 remains locked regardless of smoke metric values.

## Acceptance Commands

Future implementation must make these commands pass after first observing RED:

```bash
uv run --no-sync --extra dev pytest -q \
  tests/test_p105_release_qualified_artifacts.py::test_locked_smoke_artifact_cannot_unlock_p106
```

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark evals/proactive/forecast/p105_release_benchmark_rows.json \
  --output-json /tmp/opscat-p105-release-benchmark-smoke.json
```

## Stop Condition

Stop if smoke output can pass a release floor, receive P106 gate pass credit, or
be promoted into a qualified artifact without source-record regeneration and
full verification.
