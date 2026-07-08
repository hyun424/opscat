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

## Verification target

Expected metrics before final evidence commit:

- offline source count: at least 2
- offline download count: 0
- offline root-cause accuracy: at least 0.9
- offline route accuracy: at least 0.9
- opt-in public download count: at least 2 if network is available
- generated artifacts committed: false

Final verified metrics are recorded in `docs/release-evidence.md` after full verification and opt-in public benchmark execution.
