# OpsCat P43 Final Summary — Opt-in Public Dataset Download & Benchmark Scorecard

P43 is implemented as a public download benchmark path. It downloads small public dataset samples only when explicitly allowed, materializes them into P41-compatible raw replay files, and scores the resulting benchmark.

## Ticket completion

- P43-001 — Public benchmark manifest: `evals/real_datasets/external/p43_public_benchmark_manifest.json` defines public LogHub/NAB URLs and fallback fixtures.
- P43-002 — Network opt-in downloader: `app/services/public_dataset_benchmark.py` downloads only when `--allow-network` is passed and enforces max-byte limits.
- P43-003 — Raw materializer: downloaded LogHub raw logs and NAB CSV/label windows are converted into P41-compatible JSONL/CSV.
- P43-004 — Benchmark scorer: materialized files are scored through the P41 raw replay harness.
- P43-005 — Offline fallback: normal verification uses repo-local fixtures and performs zero downloads.
- P43-006 — CLI report: `scripts/run_public_dataset_benchmark.py` writes JSON/Markdown scorecards.
- P43-007 — Verification integration: `scripts/verify.sh` includes `public_dataset_benchmark_smoke` in offline mode.
- P43-008 — Release evidence: final offline and opt-in public download metrics are recorded after verification.

## Boundary

No external downloads during normal verification, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Primary artifacts

- `app/services/public_dataset_benchmark.py`
- `scripts/run_public_dataset_benchmark.py`
- `evals/real_datasets/external/p43_public_benchmark_manifest.json`
- `tests/test_public_dataset_benchmark.py`
- `tests/test_p43_release_evidence.py`
- `docs/operations/p43-ticket-roadmap.md`
- `docs/operations/p43-final-summary.md`

## Verification result

Full verification passed with P43 offline smoke enabled, then explicit opt-in public download benchmark passed with network access.

Offline full-verification smoke:

- dataset mode: fixture_fallback
- source count: 2
- download count: 0
- materialized source count: 2
- parsed record count: 7
- root-cause accuracy: 1.0
- route accuracy: 1.0
- network allowed: false
- external downloads performed: false

Opt-in public download benchmark:

- dataset mode: downloaded_public_sample
- source count: 2
- download count: 3
- downloaded bytes: 918821
- materialized source count: 2
- parsed record count: 4000
- label coverage: 1.0
- root-cause accuracy: 1.0
- route accuracy: 1.0
- unsafe action count: 0
- network allowed: true
- external downloads performed: true
- generated artifacts committed: false
- P43 passed: true

Full profile evidence: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full` passed; coverage gate 78.90%; `app/services/public_dataset_benchmark.py` coverage 84.99%; offline report written to `/tmp/opscat-public-dataset-benchmark-latest.md`; live opt-in report written to `/tmp/opscat-public-dataset-benchmark-live.md`.
