# OpsCat P8 Security Review

P8 adds AI Incident Responder War Room evidence while preserving the no-auth/local/mock boundary. Auth/OIDC/SSO/session login remains explicitly deferred. The feature set does not claim unattended production operation.

## In-scope surfaces

- Operator war room panel and demo copy.
- Agent reliability score display.
- Runbook critique and missing-evidence summary.
- Human question generation for blocked or approval-gated paths.
- Redacted report export links and release evidence.

## Threats and controls

| Threat | Risk | Mitigation / evidence |
| --- | --- | --- |
| stale or poisoned incident memory | Past failed remediations or stale context could make the responder overconfident. | Reliability/memory gates from P7 remain fail-closed; P8 demo copy frames memory as evidence, not authority. |
| over-trusting reliability score | Operators may treat a score as permission to act. | UI states hard policy gates still decide action eligibility; tests assert local/mock boundary language. |
| prompt/log injection in war room text | Alert text or runbook text could influence unsafe execution. | Text is HTML-escaped and redacted; mutation remains typed, policy-gated, and approval-based. |
| secret exposure in evidence or report export | Evidence/report links could leak tokens, emails, or provider secrets. | Existing redaction is used for reports; docs tests assert no known secret markers. |
| unsafe runbook improvement suggestions | Suggested runbook changes could drift into unverified production mutation. | Suggestions are review-only; local/mock action registry and policy deny production/cloud/database/shell mutation. |
| UI implying production autonomy | Portfolio demo could overclaim replacement of production operators. | Demo and security docs repeat local/mock, auth-deferred, and no unattended production-operation claims. |

## Boundary statement

P8 remains no-auth/local/mock. It does not add OIDC, SSO, login, password auth, session UI, browser mutation forms, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, or live provider mutation.

## Verification mapping

- War room/demo copy: `tests/test_p8_demo.py`, `tests/test_operator_dashboard_e2e.py`.
- Threat and boundary docs: `tests/test_p8_security_docs.py`.
- Release closure evidence: `tests/test_p8_release_evidence.py`.
- Full gate: `bash scripts/verify.sh --profile full`.
