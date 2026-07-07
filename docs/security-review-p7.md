# OpsCat P7 Security Review — Reliability & Safety Lab

P7 remains inside the local/mock OSS boundary: no auth/OIDC/session login, no customer credentials, no real cloud/database/Kubernetes mutation, and no unattended production operations. auth remains deferred explicitly.

## P7 assets

- replay harness fixtures and deterministic replay reports;
- adversarial eval fixtures for poisoned logs, prompt injection, dangerous actions, false positives, ambiguity, and connector outages;
- confidence calibration reports and fail-closed thresholds;
- self-critique evidence before policy/action proposal;
- blast-radius classifications for local, service, workspace, tenant, global, unknown, and prohibited scopes;
- action simulation records for bounded mock effects and rollback paths;
- incident memory records for similar incidents and failed remediation warnings;
- Night Autopilot v2 reliability gates;
- reliability dashboard metrics and release evidence.

## Abuse cases and mitigations

| Abuse case | Mitigation |
| --- | --- |
| Poisoned logs or malicious runbook text | self-critique records contradiction flags and prompt-injection markers; policy escalates ambiguity. |
| Memory poisoning | memory is deterministic local/mock data; failed prior outcomes become warnings instead of authority. |
| Overconfident diagnosis | confidence calibration requires bucketed reliability and rejects weak evidence/conflicting signals. |
| Unsafe automation | blast-radius, rollback availability, simulation success, confidence, and failed-memory gates all fail closed. |
| Dangerous shell/cloud/database actions | prohibited action aliases remain denied; no real providers are called. |

## Remaining gaps

P7 evidence is local/mock reliability evidence. It does not prove hosted SaaS readiness, real incident commander auth, customer tenant isolation beyond local scope, production rollback safety, or unattended production operations.
