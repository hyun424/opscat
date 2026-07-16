# P153 Staging Read-only Shadow Test Specification

1. Reject stale or forged P152 evidence, production profiles, write methods,
   unsafe routes, raw credentials, request-controlled authorization headers,
   unallowlisted hosts, unsafe budgets, redirects, and unknown providers.
2. Run a recorded Prometheus/Loki/Sentry cycle and produce normalized,
   hash-bound evidence with a deploy-regression hypothesis supported by at least
   two independent providers.
3. When a provider is missing or evidence conflicts, issue only bounded
   read-only follow-up requests and return `insufficient_evidence`.
4. Persist and resume a self-hashed forward-monotonic cursor without
   duplicating evidence; reject malformed or hash-corrupt state.
5. Redact authorization, token, password, cookie, API-key, and DSN-like values
   recursively from reports and audit records.
6. Live mode requires HTTPS, explicit acknowledgement, environment-variable
   secret references, and a safe transport. Qualification mode uses injected
   recorded responses and performs zero real network calls.
7. Release evidence requires a writer-separated zero-finding review and binds
   P152 report, freeze, review, release, current P153 sources, profile, report,
   and freeze manifest.
8. Canonical counters for external model, action execution, approval,
   production mutation, write request, secret persistence, and real network are
   all exactly zero.

## Frozen selectors

- `test_contract_and_predecessor_fail_closed`
- `test_happy_path_investigates_and_builds_grounded_judgment`
- `test_missing_evidence_abstains_and_resume_is_deduplicated`
- `test_live_boundary_redaction_and_budget_fail_closed`
- `test_release_evidence_requires_zero_finding_review`
