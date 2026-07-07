# OpsCat P6 Safety and Threat Model Refresh

P6 extends OpsCat from a local/mock first-response loop into a beta-grade agentic operations loop. This review is intentionally conservative: OpsCat remains local/mock, auth remains deferred, and the project is not production-ready.

## Assets

- Incident signals, normalized evidence, correlation groups, root-cause candidates, runbook plans, risk decisions, action attempts, verification outcomes, audit events, and generated reports.
- Local fixture secrets and metadata used for connector demos.
- Agentic eval fixtures and release evidence used to justify the beta claim.

## Trust boundaries

- Local-header demo identity is a test/demo boundary, not production auth.
- Fixture/default connector mode must not call real providers or mutate external systems.
- Evidence and reports cross from untrusted alert/log text into reviewer-visible Markdown/HTML and must be redacted/escaped.
- Policy decisions gate every action before execution; runbook text or agent suggestions are not authority.

## Abuse cases

- prompt/log injection in alerts or connector payloads;
- malicious alert payloads that attempt to alter runbook or policy behavior;
- secret exfiltration via evidence, reports, eval output, or operator UI;
- unsafe auto-remediation for production-like or high-blast-radius actions;
- cross-workspace merge of similar fingerprints;
- replay attacks against alert/action idempotency;
- eval overfitting that makes demos pass without enforcing safety invariants.

## Mitigations

- P6 evals require 100% unsafe action blocking for dangerous fixtures.
- P6 release docs keep local/mock and no-production-credentials boundaries visible.
- Existing tests cover redaction, dangerous production mutation denial, connector fail-closed behavior, and workspace scoping.
- `scripts/verify.sh --profile full` runs lint, typecheck, tests, coverage, evals, demos, Docker config, and hygiene checks without credentials.
- Operator browser surfaces remain read-only for mutation workflows while auth remains deferred.

## Remaining gaps

- Production auth, SSO/OIDC, session security, tenant administration, CSRF/session hardening, hosted workers, external secret management, and real provider deployment remain future work.
- P6 local/mock evidence does not prove unattended production safety.
- Real customer logs, production credentials, and live provider mutations are explicitly unsupported.
- Before production beta use, repeat this review with deployed auth, secrets, connector, logging, and incident-retention controls.
