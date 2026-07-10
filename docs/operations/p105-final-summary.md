# P105 Final Summary - Calibrated Failure Forecast Engine

## Delivered

- Local calibrated failure-forecasting harness for P105 benchmark rows.
- Release evidence contract separating tiny smoke fixtures from generated
  `release_qualified` evidence.
- Model card documenting modes, floors, formulas, provenance, P24 parity,
  limitations, commands, and authority boundaries.
- README, ROADMAP, CHANGELOG, release-evidence, and verify-script integration
  for the P105 smoke path.

## Current evidence status

The committed P105 fixture is intentionally tiny and has no mode metadata. It
normalizes to `smoke_only_missing_mode`. It can validate benchmark wiring,
formula rendering, diagnostic partition handling, and release-doc contracts, but
it is not release-qualified performance evidence.

P106 remains locked until generated evidence exists with
`mode=release_qualified`, adequate held-out and real-derived denominators,
P32/P41/P44 source-record provenance, union service-day coverage, outcome-neutral
partitions, actual P24 `RiskSignal`/`RiskForecast` parity, and zero authority
counters.

## Qualification floor summary

- Held-out: per-family evaluated >= 30, non-abstained >= 24, actual positives
  >= 6, incident groups >= 4, service days >= 2.0.
- Real-derived: per-family evaluated >= 20, non-abstained >= 16, actual
  positives >= 4, incident groups >= 3, service days >= 1.0.
- Source diversity: at least three materialized P32/P41/P44 source record sets
  and no single canonical source tuple above 60% of a family real-derived row
  denominator.
- Global service-day floor: merged service-day coverage >= 7.0.

These floors prevent tiny-N release claims; they are not statistical
significance claims.

## Metric and denominator summary

P105 reports Brier, ECE, precision, recall, useful lead-time rate,
false-alerts per service-day, abstention rate, held-out improvement over P24,
and real-derived transfer rows with explicit numerators and denominators.
Service-day coverage is computed from merged coverage intervals for each
evaluated split/family/service/source scope. Missing or zero denominators are
reported explicitly and fail closed where the release gate requires a value.

## Boundaries

P105 is no-auth, local/offline by default, action-disabled, and not a production
operation authority. It performs no production mutation, remediation execution,
provider action execution, default external model calls, credential use, live
API mutation, Kubernetes/cloud/database mutation, or P106 action planning.
Optional provider rationale remains advisory text only.

## Verification anchors

- `app/services/failure_forecast_engine.py`
- `scripts/run_failure_forecast_benchmark.py`
- `evals/proactive/forecast/p105_release_benchmark_rows.json`
- `tests/test_failure_forecast_engine.py`
- `tests/test_p105_release_evidence.py`
- `docs/operations/p105-model-card.md`
- `docs/operations/p105-ticket-roadmap.md`
- `docs/tickets/p105/README.md`

Offline smoke:

```bash
uv run --no-sync --extra dev python scripts/run_failure_forecast_benchmark.py \
  --release-benchmark evals/proactive/forecast/p105_release_benchmark_rows.json \
  --output-json /tmp/opscat-p105-release-benchmark-smoke.json
```
