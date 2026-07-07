# OpsCat Roadmap

OpsCat is moving from a portfolio-grade local/mock agentic on-call MVP toward an open-source-usable product prototype.

## P4 complete

P4 is complete. It added reproducible evidence for the local/mock operator-replacement claim:

- 23/23 golden incident evals;
- 7/7 connector safety evals;
- dashboard browser-contract E2E;
- eval taxonomy and release evidence index;
- full `bash scripts/verify.sh` release gate.

See `docs/release-evidence.md` and `docs/integration-verification.md`.

## P5 active

P5 active scope: OSS-usable productization without auth.

Primary plan: `docs/operations/p5-ticket-roadmap.md`.

Current priority:

1. Open-source quickstart and example environment.
2. Contributor guide, roadmap, and issue templates.
3. Public API docs and local fixture examples.
4. Connector setup registry and permission preview.
5. Connector SDK guide and fixture connector template.
6. Secret lifecycle and redaction audit.
7. Incident import adapters.
8. Worker CLI and dead-letter operations.
9. Approval console without auth/session work.
10. Night Autopilot policy and morning report evidence.
11. Expanded connector/product evals.
12. Self-observability.
13. CI-ready verification.
14. OSS security policy and release packaging.
15. P5 final release evidence.

## Auth deferred

auth deferred means P5 intentionally does not include OIDC, SSO, login, password auth, session UI, production user provisioning, or CSRF/session-hardening tied to browser mutation forms. The current local-header demo identity remains the local/mock boundary until the owner explicitly reopens auth.

## P6 candidates

P6 candidates after P5:

- production auth and tenant administration;
- real connector OAuth/secret-manager integration;
- customer-side connector agent package;
- hosted workflow workers and queue infrastructure;
- live incident replay from sanitized exports;
- load/soak testing;
- deployment, backup/restore, and OpsCat self-monitoring for real beta environments;
- license decision and public release process.
