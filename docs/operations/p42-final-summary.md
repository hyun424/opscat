# OpsCat P42 Final Summary — External Dataset Acquisition & Holdout Evaluation

P42 is planned. It will add an opt-in external dataset acquisition plan and deterministic holdout evaluation while keeping normal verification local and network-free.

## Ticket completion

- P42-001 — External dataset manifest: `evals/real_datasets/external/p42_manifest.json` defines LogHub/NAB/local AIOps source metadata and fixtures.
- P42-002 — Acquisition planner: `app/services/external_dataset_acquisition.py` validates source cards and dry-run status.
- P42-003 — Opt-in downloader boundary: network fetches require explicit `--allow-network`; default verification performs zero downloads.
- P42-004 — Holdout split builder: deterministic train/dev/holdout split is derived from manifest source IDs and seed.
- P42-005 — Holdout scorer: holdout sources are scored through the P41 raw replay harness.
- P42-006 — CLI report: `scripts/prepare_external_datasets.py` writes JSON/Markdown.
- P42-007 — Verification integration: `scripts/verify.sh` includes `external_dataset_acquisition_smoke`.
- P42-008 — Release evidence: final metrics are recorded after full verification passes.

## Boundary

No external downloads during normal verification, no live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Primary artifacts

- `app/services/external_dataset_acquisition.py`
- `scripts/prepare_external_datasets.py`
- `evals/real_datasets/external/p42_manifest.json`
- `tests/test_external_dataset_acquisition.py`
- `tests/test_p42_release_evidence.py`
- `docs/operations/p42-ticket-roadmap.md`
- `docs/operations/p42-final-summary.md`

## Verification result

Full verification passed with P42 external dataset acquisition smoke enabled. Verified metrics:

- source count: 3
- dry-run download count: 0
- holdout source count: 2
- holdout raw source count: 2
- holdout parsed record count: 4
- label coverage: 1.0
- root-cause accuracy: 1.0
- route accuracy: 1.0
- unsafe action count: 0
- boundary violation count: 0
- network allowed: false
- external downloads performed: false
- split train/dev/holdout: 0/1/2
- P42 passed: true

Full profile evidence: `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full` passed; coverage gate 78.77%; `app/services/external_dataset_acquisition.py` coverage 85.17%; report written to `/tmp/opscat-external-dataset-acquisition-latest.md`.
