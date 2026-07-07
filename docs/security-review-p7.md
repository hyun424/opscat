# OpsCat P7 Security Review — Reliability & Safety Lab

P7 remains a **local/mock** reliability lab. Auth remains deferred: no OIDC, SSO, login, browser session, password, CSRF/session-hardening, or production user provisioning is implemented in P7.

## P7 safety assets

- Incident replay fixtures and replay runner (`evals/replay`, `scripts/run_replay_evals.py`).
- Adversarial replay cases for noisy logs, poisoned text, dangerous action attempts, duplicate alerts, ambiguous root causes, and connector outage masking.
- Confidence calibration reports with bucket accuracy, overconfidence, underconfidence, and fail-closed thresholds.
- Self-critique records before risk/action proposal.
- Blast radius assessments for local, service, workspace, tenant, global, unknown, and prohibited scopes.
- Action simulation evidence before mock execution.
- Incident memory similarity records and prior failed-remediation warnings.
- Night Autopilot v2 gates that require confidence, low blast radius, rollback, simulation, and clean memory.
- Failure-mode reports and reliability dashboard metrics.

## Abuse cases and mitigations

| Abuse case | P7 mitigation |
| --- | --- |
| Poisoned logs or malicious runbook text | Adversarial replay fixtures require prompt/log injection to escalate or block, not auto-remediate. |
| Dangerous action request hidden in alert text | Policy, blast radius, and simulator block shell, cloud, database, secret, and production mutations. |
| Overconfident diagnosis with weak evidence | Confidence calibration and self-critique fail closed when evidence is sparse or conflicting. |
| Memory poisoning or failed prior remediation | Incident memory is deterministic/local; failed similar incidents become warnings that block automation. |
| Night Autopilot unsafe action while humans sleep | Night Autopilot v2 requires high confidence, service/local blast radius, rollback availability, simulation pass, no failed-memory warning, allowed service/environment, and max-attempt limits. |
| Silent terminal path | Failure-mode reports include uncertainty, alternate hypotheses, missing evidence, blocked actions, and escalation reasons. |

## Remaining gaps

- P7 does not prove unattended production operation.
- P7 does not use real customer credentials or live provider mutation.
- P7 does not implement auth/session/OIDC; the local-header demo identity remains the boundary.
- P7 replay and action simulation are deterministic local/mock evidence, not a substitute for hosted production incident response hardening.

## P7 explicit reviewer phrases
Auth/OIDC/SSO/session login remains explicitly deferred. P7 covers replay, adversarial log injection, confidence calibration, self-critique, blast radius, action simulation, incident memory, memory poisoning, and Night Autopilot v2. It does not claim unattended production operation; auth remains deferred and all evidence is local/mock.

Replay poisoning is an explicit P7 threat model item alongside adversarial log injection and memory poisoning.

replay poisoning remains an explicit P7 threat model item.

overconfident diagnosis is explicitly covered by confidence calibration and self-critique gates.
