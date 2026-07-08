# OpsCat P37 Final Summary — Open-source Config Hardening

P37 validates open-source/local configuration templates and examples so contributors can run OpsCat safely without committing secrets or enabling live/prod mutation by default.

## Ticket completion

- P37-001 — Config manifest: `evals/config/p37_config_manifest.json` defines checked OSS surfaces.
- P37-002 — Template linter: P37 detects missing files, missing placeholders, real-looking secrets, and unsafe defaults.
- P37-003 — Connector sample checks: connector examples are scanned for credential-reference safety and secret-marker absence.
- P37-004 — Approval profile checks: P36 approval profiles are scanned as committed local config examples.
- P37-005 — Remediation boundary checks: `config/opscat.local.example.json` keeps live/prod mutation and remediation disabled.
- P37-006 — Scorecard: reports template pass rate, secret safety rate, safe default rate, blocker count, real secret count, and unsafe default count.
- P37-007 — CLI report: `scripts/run_open_source_config_hardening.py` writes JSON/Markdown.
- P37-008 — Verification integration: `scripts/verify.sh` includes `open_source_config_hardening_smoke`.

## Primary artifacts

- `app/services/open_source_config_hardening.py`
- `scripts/run_open_source_config_hardening.py`
- `evals/config/p37_config_manifest.json`
- `config/opscat.local.example.json`
- `config/connectors.local.example.json`
- `tests/test_open_source_config_hardening.py`
- `tests/test_p37_release_evidence.py`
- `docs/operations/p37-ticket-roadmap.md`
- `docs/operations/p37-final-summary.md`

## Boundary

No auth/session implementation, no real `.env` value reads, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and does not claim unattended production operation.

## Verification target

Expected metrics before final full verification:

- checked surface count: at least 4
- template pass rate: 1.0
- secret safety rate: 1.0
- safe default rate: 1.0
- real secret count: 0
- unsafe default count: 0

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
