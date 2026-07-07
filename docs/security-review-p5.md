# P5 Security Review

This review covers the OSS/productization surfaces added in P5. OpsCat remains local/mock; auth remains deferred; no production credentials should be used.

## Review principles

- Every unsafe path should fail closed.
- Every output path should preserve redaction.
- Every data query should respect tenant/workspace scope.
- Every write-like path should be approval-gated, dry-run, or explicitly local/mock.
- Every residual production gap should be documented instead of hidden.

## Surface checklist

### connector setup

Adversarial checks:

- Unknown connector/capability fails closed.
- Catalog exposes least-privilege roles and required secret names before setup.
- No broad token request appears in docs or API examples.

Controls: connector catalog tests, connector eval `setup_permission`, dry-run metadata.

Residual gaps: real OAuth/provider consent screens are not implemented.

### secret lifecycle

Adversarial checks:

- Metadata list never returns plaintext or ciphertext.
- Deleting a secret causes connector calls to fail closed.
- Audit logs include name/scope but not secret value.

Controls: metadata-only `/secrets`, local envelope provider, secret lifecycle tests.

Residual gaps: external secret manager and production rotation policy are not implemented.

### incident import

Adversarial checks:

- Unsupported provider fails closed.
- Duplicate fixture delivery is idempotent.
- Secret-bearing fixture fields are redacted before persistence/reporting.

Controls: signal normalizer tests and connector eval `import_normalization`.

Residual gaps: raw production log ingestion is not supported.

### worker CLI

Adversarial checks:

- Queue stats expose counts, not payload secrets.
- Drain is bounded by limit.
- Failed jobs can be dead-lettered visibly.

Controls: workflow CLI tests and verify smoke.

Residual gaps: distributed leases and hosted worker infrastructure are not implemented.

### approval console

Adversarial checks:

- Cross-workspace action detail returns 404.
- Action preview shows risk, policy, evidence, preconditions, and post-checks.
- No browser mutation form exists before auth/session safety.

Controls: operator approval console tests.

Residual gaps: authenticated browser approval UX is not implemented.

### Night Autopilot

Adversarial checks:

- Production/high-risk paths escalate rather than execute.
- Attempt limits block automatic loops.
- Morning report includes blocked actions and verification outcomes.

Controls: Night Autopilot policy tests and wake-up report docs.

Residual gaps: real sleep-time production remediation is not enabled.

### self-observability

Adversarial checks:

- Metrics are tenant/workspace scoped.
- Metrics contain counts only, not raw payloads or customer data.
- Connector failures and escalations are counted.

Controls: `/metrics` tests and self-observability docs.

Residual gaps: external Prometheus/OpenTelemetry export is not implemented.

## Residual gaps

- auth remains deferred: no OIDC, SSO, sessions, passwords, or browser CSRF/session guarantee.
- no production credentials or real customer data should be used.
- no live provider mutation is enabled.
- no external secret manager is configured.
- no hosted workflow worker, load test, or production deployment gate exists.

## Review result

P5 is suitable for local/mock OSS demonstration and portfolio review. It is not suitable for real customer production use until the residual gaps are explicitly designed, implemented, and verified.
