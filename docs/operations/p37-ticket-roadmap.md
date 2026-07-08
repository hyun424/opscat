# OpsCat P37 Ticket Roadmap — Open-source Config Hardening

P37 makes OpsCat safer for open-source/local use by validating configuration templates before users connect real systems. It does not add auth and does not read secrets; it checks placeholders, safe defaults, and boundary flags.

## Tickets

- P37-001 — Config manifest: define required OSS config files, expected placeholders, and safe default flags.
- P37-002 — Template linter: detect missing files, real-looking secrets, unsafe live defaults, mutation defaults, and unrestricted shell defaults.
- P37-003 — Connector sample checks: verify connector examples use credential references/placeholders, not committed secrets.
- P37-004 — Approval profile checks: verify P36 profiles keep auth/session and execution disabled by default.
- P37-005 — Remediation boundary checks: verify default config keeps production mutation and remediation execution disabled.
- P37-006 — Scorecard: report template pass rate, secret safety rate, safe default rate, and blocker count.
- P37-007 — CLI report: `scripts/run_open_source_config_hardening.py` writes JSON/Markdown reports.
- P37-008 — Verification integration: add targeted tests, full-profile smoke, release evidence, and docs contract tests.

## Boundaries

- no auth/session implementation
- no reading or printing real `.env` values
- no live API calls
- no production mutation
- no remediation execution
- no unrestricted shell
- no default external model/API calls
- no unattended production-operation claim

## Acceptance criteria

- At least four OSS config surfaces are checked.
- Real-looking secret count is 0.
- Unsafe default count is 0.
- Safe default rate is 1.0.
- Template pass rate is 1.0.
- Full verification profile includes `open_source_config_hardening_smoke`.
