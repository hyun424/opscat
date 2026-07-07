# OpsCat Runbooks

P6 runbooks live in `app/services/runbook_service.py` and are deterministic local/mock plans. Each step declares:

- preconditions;
- required permission/capability;
- risk hint;
- dry-run support;
- rollback expectation;
- verification check.

Current registry:

- recent deploy regression;
- API 5xx/dependency timeout diagnostics;
- queue backlog recovery;
- connector outage or missing secret;
- diagnostic-only human handoff.

Unknown or low-confidence incidents select diagnostic-only steps and refuse mutation.
