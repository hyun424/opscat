# Security Policy

OpsCat is currently a local/mock open-source prototype for agentic operations workflows. It is not a production security boundary and auth is deferred until a later explicitly scoped phase.

Security-sensitive reports should be sent through GitHub's private vulnerability reporting feature when enabled. If unavailable, open a minimal public issue requesting a private contact channel without including exploit details or secrets. Maintainers target acknowledgement within 7 days; this is a best-effort open-source policy, not an SLA.

## Supported scope

Current supported security scope:

- local/mock demos and fixture-backed tests;
- local-header demo identity for tenant/workspace scoping;
- metadata-only local secret setup examples;
- dry-run or fixture-backed connectors;
- policy-gated mock actions;
- deterministic eval and verification evidence.

Current unsupported scope:

- production credentials;
- real customer incidents or customer logs;
- live provider OAuth/token operations;
- real Slack/GitHub/Sentry mutation;
- production auth, SSO, OIDC, sessions, passwords, or browser CSRF/session guarantees.

## Safe disclosure

Use this safe disclosure process for issues or pull requests for bugs that do not expose sensitive data. For security-sensitive reports, share only a minimal reproduction with synthetic fixture data.

Do not submit secrets. Do not submit customer logs. Do not submit tokens, private keys, production credentials, customer data, proprietary runbooks, or live provider payloads. Replace sensitive values with `[REDACTED]` and use local fixture examples.

## What to include

A useful report includes:

- affected local/mock surface;
- steps to reproduce with fixture data;
- expected safe behavior;
- actual behavior;
- command output with secrets removed;
- whether auth is deferred or explicitly out of scope for the issue.

## Contributor security rules

- Keep connectors fixture-backed or dry-run by default.
- Keep actions policy-gated and approval-gated when they are write-like.
- Add redaction tests when adding new payload/report/evidence fields.
- Add connector eval or incident eval coverage for new integration behavior.
- Do not add production-ready security claims unless the corresponding auth, tenancy, secret, and deployment controls exist.

## P6 safety note

P6 adds agentic-loop safety documentation in `docs/security-review-p6.md` and deterministic policy routes in `docs/operations/safety-policy.md`. Auth remains deferred; production mutation remains blocked/local-mock only.
