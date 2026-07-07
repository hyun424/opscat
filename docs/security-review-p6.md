# OpsCat P6 Security Review

## Assets and boundaries

- Incident signals, correlated evidence, root-cause candidates, runbooks, policy decisions, action attempts, verification results, connector call records, and decision traces.
- Trust boundary: local/demo headers and local/mock execution only. Auth/OIDC/SSO/session login remains explicitly deferred.
- Provider-shaped Sentry behavior uses fixture mode by default; real provider calls are opt-in and credential-gated.

## Threats and mitigations

- Prompt/log injection: treated as untrusted evidence and redacted before trace/report/UI rendering.
- Secret exfiltration through evidence: redaction is applied to signal normalization, reports, connector results, and decision traces.
- Unsafe auto-remediation: deterministic policy blocks production mutation, database mutation, cloud deletion, arbitrary shell, and secret access.
- Cross-workspace merge: correlation keys include tenant/workspace and record rejected neighbors.
- Replay/idempotency: incident and connector idempotency keys prevent duplicate confidence inflation and duplicate escalations.
- Eval overfitting: P6 evals score multiple dimensions over the golden scenario set and keep outputs in temp paths by default.

## Remaining gaps

OpsCat P6 is not production-ready for unattended production operations. It has no hosted multi-tenant auth, no production credential collection, and no unrestricted external mutation path.
