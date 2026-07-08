# OpsCat P25 Final Summary — Proactive Signal Corpus Expansion and Calibration

P25 expands proactive prevention evaluation from a 12-window proof-of-concept to a calibrated 100+ proactive windows corpus. Each fixture now carries expected route, ETA range, confidence floor, expected auto capabilities, approval-required capabilities, and blocked capabilities. The calibration evaluator verifies ETA/route/confidence/action-safety behavior deterministically.

## Tickets closed

- P25-001 Proactive taxonomy: 30+ risk types across resource exhaustion, DB, queue, SLO, deploy, dependency, observability, security, data pipeline, and false-positive/noise families.
- P25-002 Fixture expansion: `evals/proactive/seed/risk_windows.json` now contains 120 proactive windows.
- P25-003 Expected outcome schema: fixtures include expected route, ETA range, minimum confidence, auto capabilities, approval-required capabilities, and blocked capabilities.
- P25-004 Calibration evaluator: `evaluate_proactive_calibration` reports route_mismatch_count, eta_out_of_range_count, confidence_below_floor_count, unsafe_auto_action_count, and capability mismatch counts.
- P25-005 Calibration report CLI: `scripts/run_proactive_calibration.py` writes JSON/Markdown reports.
- P25-006 Verification integration: `proactive_calibration_smoke` is included in `scripts/verify.sh`.
- P25-007 Release evidence: roadmap and release evidence updated.

## Corpus coverage

- 100+ proactive windows: 120.
- 30+ risk types: 42.
- Routes: preventive_review, monitor, and blocked.
- Safety: automatic actions remain limited to read-only diagnostics, reports, and notification drafts.

## Artifacts

- `app/services/proactive_risk_sentinel.py`
- `scripts/run_proactive_calibration.py`
- `evals/proactive/seed/risk_windows.json`
- `tests/test_p25_proactive_corpus_calibration.py`
- `tests/test_p25_release_evidence.py`
- `docs/operations/p25-ticket-roadmap.md`
- `docs/operations/p25-final-summary.md`
- `/tmp/opscat-proactive-calibration-latest.md`

## Verification

Targeted GREEN:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_p25_proactive_corpus_calibration.py tests/test_p25_release_evidence.py
# 6 passed
```

Static and related regression:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app/services/proactive_risk_sentinel.py scripts/run_proactive_risk_sentinel.py scripts/run_proactive_calibration.py tests/test_proactive_risk_sentinel.py tests/test_p24_release_evidence.py tests/test_p25_proactive_corpus_calibration.py tests/test_p25_release_evidence.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app/services/proactive_risk_sentinel.py scripts/run_proactive_risk_sentinel.py scripts/run_proactive_calibration.py tests/test_proactive_risk_sentinel.py tests/test_p24_release_evidence.py tests/test_p25_proactive_corpus_calibration.py tests/test_p25_release_evidence.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_proactive_risk_sentinel.py tests/test_p24_release_evidence.py tests/test_p25_proactive_corpus_calibration.py tests/test_p25_release_evidence.py
# ruff passed; mypy passed; 13 passed
```

Calibration smoke:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_proactive_calibration.py \
  --fixtures evals/proactive/seed/risk_windows.json \
  --output-json /tmp/opscat-proactive-calibration-p25.json \
  --output-md /tmp/opscat-proactive-calibration-p25.md
# windows=120 risk_types=42 passed=True route_mismatch=0 eta_out=0 unsafe_auto=0 action_execution_enabled=False
# routes: preventive_review=96, monitor=12, blocked=12
```

Calibration expected results:

```text
route_mismatch_count=0
eta_out_of_range_count=0
confidence_below_floor_count=0
unsafe_auto_action_count=0
missing_expected_count=0
auto_capability_mismatch_count=0
approval_capability_mismatch_count=0
blocked_capability_mismatch_count=0
```

Full verification:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full
# Verification complete (full); coverage gate passed: 76.54% >= 60.00%; P25 proactive calibration smoke executed
```

## Boundary

P25 is no-auth/local-mock by default. It does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, remediation execution, or unattended production-operation claims; it does not claim unattended production operation.
