# OpsCat P17 Ticket Roadmap — LLM Policy Calibration

## Scope

P17 turns LLM provider judgment into a safer agent runtime decision by adding a deterministic policy calibration layer after LLM judgment and safety gating. The calibrator is not a second LLM. It is the domain-specific approval governor that downgrades over-aggressive provider routes, removes risky automatic actions, and records why OpsCat did not trust the provider's raw recommendation.

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real rollback/restart/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- NVIDIA live evaluation remains explicit opt-in via local `.env`; secrets are never committed or printed.
- OpsCat does not claim unattended production operation in P17.

## Tickets

### P17-001 — Calibration result schema

Create a stable policy calibration result contract with provider route, safety-gate route, calibrated route, retained actions, removed actions, fatal risk flags, and reasons.

Acceptance:
- Calibration output serializes to JSON-compatible dictionaries.
- Output keeps provider and safety-gate routes for auditability.
- Output never claims actions were executed.

### P17-002 — Context risk classification

Classify prompt injection, unsafe action requests, metric-only/no-data ambiguity, missing evidence, and deploy/rollback-sensitive situations from the context packet, judgment, and rubric.

Acceptance:
- Prompt injection and unsafe action requests force `blocked`.
- No-data/stale/metric-only evidence forces `human_required` unless stronger corroborating evidence exists.
- Deploy rollback/restart-sensitive proposals cannot stay auto-approved.

### P17-003 — Conservative route downgrade policy

Implement deterministic route precedence so policy can override the provider and safety gate.

Acceptance:
- `blocked` wins for injection/forbidden unsafe action evidence.
- `human_required` wins for insufficient evidence or ambiguous no-data signals.
- Provider `local_mock_auto_allowed` is only retained when all auto-approval conditions pass.

### P17-004 — Action filter

Filter automatic action candidates after calibration.

Acceptance:
- `human_required` and `blocked` retain no automatic actions.
- Rollback/restart/scale/delete/shell/database/cloud/Kubernetes actions are removed from automatic candidates.
- Read-only local/mock information gathering can be retained only for `local_mock_auto_allowed`.

### P17-005 — Provider evaluation integration

Integrate calibration into P16 provider evaluation scoring.

Acceptance:
- Scoring uses `calibrated_route` as the final route while preserving raw provider route.
- Forbidden-action scoring considers removed actions and calibration reasons.
- JSON output includes calibration details for every case.

### P17-006 — Report and verification integration

Expose calibration in Markdown reports and normal verification smoke.

Acceptance:
- Provider eval Markdown shows provider route, calibrated route, and calibration reasons.
- `scripts/verify.sh` includes a P17 policy calibration smoke in local/mock mode.
- No external provider calls are added to default verification.

### P17-007 — Release evidence

Document P17 final evidence and update roadmap/release artifacts.

Acceptance:
- `docs/operations/p17-final-summary.md` maps tickets to artifacts and verification.
- `docs/release-evidence.md` references P17 artifacts.
- `ROADMAP.md` records P17 implemented status and boundary.
