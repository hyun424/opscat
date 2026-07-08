# OpsCat P44 Final Summary — Larger Public Dataset Benchmark Matrix

P44 is planned. It will expand public benchmark evidence from one scorecard into a multi-source matrix with source-level and family-level scoring.

## Ticket completion

- P44-001 — Matrix manifest: `evals/real_datasets/external/p44_benchmark_matrix_manifest.json` defines two LogHub and three NAB public sample sources plus fallback fixtures.
- P44-002 — Matrix runner: `app/services/public_dataset_matrix.py` reuses P43 acquisition/materialization and scores each source independently.
- P44-003 — Family aggregation: P44 aggregates source-level metrics into loghub/nab family-level score rows.
- P44-004 — Error analysis: P44 records false-positive/false-negative proxy counts, unsafe action count, and worst sources.
- P44-005 — Offline verification path: full verification runs fixture fallback with zero downloads.
- P44-006 — Opt-in public benchmark path: `--allow-network` downloads public samples into `/tmp` or user-selected artifact roots.
- P44-007 — CLI report: `scripts/run_public_dataset_matrix.py` emits JSON/Markdown benchmark matrix reports.
- P44-008 — Release evidence: final offline and opt-in public matrix metrics are recorded after verification.

## Boundary

No external downloads during normal verification, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Primary artifacts

- `app/services/public_dataset_matrix.py`
- `scripts/run_public_dataset_matrix.py`
- `evals/real_datasets/external/p44_benchmark_matrix_manifest.json`
- `tests/test_public_dataset_matrix.py`
- `tests/test_p44_release_evidence.py`
- `docs/operations/p44-ticket-roadmap.md`
- `docs/operations/p44-final-summary.md`

## Verification result

Full verification passed with P44 offline matrix smoke enabled, then explicit opt-in public download matrix passed with network access.

Offline full-verification matrix:

- dataset mode: fixture_fallback
- source count: 5
- download count: 0
- matrix row count: 5
- family count: 2
- parsed record count: 18
- root-cause accuracy: 1.0
- route accuracy: 1.0
- false-positive proxy count: 0
- false-negative proxy count: 0
- network allowed: false
- external downloads performed: false

Opt-in public download matrix:

- dataset mode: downloaded_public_sample
- source count: 5
- download count: 8
- matrix row count: 5
- family count: 2
- parsed record count: 10000
- label coverage: 1.0
- root-cause accuracy: 1.0
- route accuracy: 1.0
- unsafe action count: 0
- false-positive proxy count: 0
- false-negative proxy count: 0
- worst sources: none
- network allowed: true
- external downloads performed: true
- generated artifacts committed: false
- P44 passed: true

Full profile evidence: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full` passed; coverage gate 78.99%; `app/services/public_dataset_matrix.py` coverage 87.62%; offline report written to `/tmp/opscat-public-dataset-matrix-latest.md`; live opt-in report written to `/tmp/opscat-public-dataset-matrix-live.md`.
