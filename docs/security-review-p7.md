# OpsCat P7 Security Review

## Assets and boundaries

P7 adds reliability and safety-lab assets around the existing local/mock agent loop:

- replay scenarios, adversarial/noisy fixtures, replay outputs, and eval summaries;
- confidence calibration buckets, self-critique findings, and failure-mode summaries;
- blast-radius classifications, rollback availability, and action simulation evidence;
- incident-memory similarity records and prior-remediation warnings;
- Night Autopilot v2 gate decisions, morning-report rationale, and blocked-action queues;
- reliability dashboard metrics and P7 release evidence.

The boundary remains **local/mock**. Auth/OIDC/SSO/session login remains explicitly deferred. P7 must not collect production credentials, perform unrestricted shell/cloud/database mutation, or imply hosted multi-tenant production operation.


## Current implementation status

In this worktree, the P7 roadmap is the target contract while several implementation services remain pending integration. Current action metadata still represents blast radius as string action metadata; structured scope derivation over payloads is pending P7-005. Current mock action execution is deterministic and local, but a dedicated simulator precondition record is pending P7-006. The shared decision trace still uses the P6 stages (`observe`, `correlate`, `diagnose`, `plan`, `risk`, `act`, `verify`); the explicit P7 self-critique stage is pending P7-004 integration.

## Threats and mitigations

- **replay poisoning**: fixture inputs can bias confidence or make unsafe routes appear safe. Mitigation: replay scenarios remain deterministic, reviewed as repo data, and scored against explicit expected route/action/verification fields.
- **adversarial log injection**: incident messages, runbooks, provider envelopes, and logs are untrusted. Mitigation: P7 adversarial evals include prompt/log injection and require escalation or blocked action outcomes when instructions conflict with policy.
- **overconfident diagnosis**: high confidence without enough evidence can lead to unsafe automation. Mitigation: calibration thresholds, evidence-count checks, contradiction flags, and self-critique objections fail closed before auto action.
- **memory poisoning**: similar-incident retrieval can amplify bad historical remediations. Mitigation: memory evidence records outcome, failed-action warnings, and deterministic similarity reasons instead of treating prior actions as authority.
- **Unsafe Night Autopilot v2 automation**: quiet-hours actions are risky if the gate only checks an allowlist. Mitigation: v2 requires high confidence, low blast radius, reversibility, successful simulation, no failed-memory warning, allowed service/environment, and max-attempt controls.
- **Dashboard/report overclaiming**: reliability metrics can be mistaken for production readiness. Mitigation: P7 release evidence distinguishes fixture/local reliability from unattended production operation.

## Review checklist for P7 changes

1. No new route, dashboard form, eval runner, or demo path may require auth/session work unless the owner explicitly reopens that scope.
2. Replay/eval runners must not call real providers or require external credentials.
3. Action proposals must carry critique, blast-radius, rollback, simulation, and failure-mode evidence before execution or approval.
4. Reports and dashboards must render untrusted text safely and keep mutation paths API-gated/local.
5. Reliability claims must link to commands and fixture outputs, not subjective assertions.

## Remaining gaps

OpsCat P7 does not claim unattended production operation. Production auth, tenant administration, real customer credential collection, hosted workers, live provider mutation, live incident replay, load/soak testing, and production SLO monitoring remain outside the no-auth/local-mock P7 boundary.
