# OpsCat Roadmap

OpsCat is moving from a portfolio-grade local/mock agentic on-call MVP toward a beta-grade agentic operations system.

## P4 complete

P4 is complete. It added reproducible evidence for the local/mock operator-replacement claim:

- 23/23 golden incident evals;
- 7/7 connector safety evals;
- dashboard browser-contract E2E;
- eval taxonomy and release evidence index;
- full `bash scripts/verify.sh` release gate.

See `docs/release-evidence.md` and `docs/integration-verification.md`.

## P5 complete

P5 delivered OSS-usable productization without auth: quickstart, contributor docs, issue templates, connector setup/permission preview, secret lifecycle, incident import fixtures, worker CLI, approval console, Night Autopilot evidence, expanded connector evals, self-observability, CI profiles, security policy, and release packaging.

Historical P5 active plan: `docs/operations/p5-ticket-roadmap.md`.

## P6 active

P6 active scope: Beta-grade agentic ops loop without auth.

Primary plan: `docs/operations/p6-ticket-roadmap.md`.

Current priority:

1. Real-provider-shaped Sentry connector deepening.
2. Incident correlation engine.
3. Root-cause candidate generator.
4. Runbook registry and planner.
5. Risk scoring engine v2 and action policy DSL.
6. Safe action runner with dry-run, rollback metadata, and audit.
7. Post-action verification and recovery-state machine.
8. Agent decision trace and audit timeline.
9. Operator console incident timeline and agentic action view.
10. Agentic eval suite v1.
11. One-command beta demo of the full agentic loop.
12. P6 safety/threat-model refresh.
13. P6 release evidence and roadmap update.
14. Portfolio demo polish package.

## Auth deferred

auth deferred means P5 and P6 intentionally do not include OIDC, SSO, login, password auth, session UI, production user provisioning, or CSRF/session-hardening tied to browser mutation forms. The current local-header demo identity remains the local/mock boundary until the owner explicitly reopens auth.

## P6 candidates

P6 candidates have been promoted into the P6 active roadmap. Remaining out-of-scope production candidates for later phases:

- production auth and tenant administration;
- real connector OAuth/secret-manager integration beyond local opt-in secrets;
- customer-side connector agent package;
- hosted workflow workers and queue infrastructure;
- live incident replay from sanitized exports;
- load/soak testing;
- deployment, backup/restore, and OpsCat self-monitoring for real beta environments;
- license decision and public release process.

## P7 active

P7 active scope: Agent Reliability & Safety Lab without auth. P7 focuses on replay-based reliability, adversarial evals, confidence calibration, self-critique, blast-radius analysis, action simulation, incident memory, Night Autopilot v2, failure-mode reporting, reliability dashboard metrics, and release evidence. See `docs/operations/p7-ticket-roadmap.md`. The active boundary is no-auth/local-mock: P7 does not add login/session UI, production credentials, hosted SaaS operations, or unrestricted production mutation.

## P7 candidates

P7 should focus on safety/autonomy hardening after the P6 loop exists:

- action blast-radius calculator;
- rollback guarantee checker;
- adversarial incident/log-injection evals;
- incident memory and similarity search;
- confidence calibration and self-critique before execution;
- production deployment packaging with explicit auth/tenant decision deferred or reopened by the owner.

## P6 — Beta-grade agentic ops loop

Status: implemented as local/mock beta evidence. See `docs/operations/p6-ticket-roadmap.md`, `docs/agentic-loop.md`, and `docs/release-evidence.md`. P7 candidates: hardened auth, stronger tenant isolation, real provider SDK hardening, and production-grade approval workflows.

## P7 complete

P7 is implemented as a local/mock Agent Reliability & Safety Lab: replay harness, adversarial evals, confidence calibration, self-critique, blast-radius checks, action simulation, incident memory, Night Autopilot v2 gates, failure-mode reporting, reliability dashboard metrics, security review, and release evidence. Auth remains deferred and production unattended-ops claims remain out of scope.
