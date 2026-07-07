# Night Autopilot Wake-Up Report

Night Autopilot is a local/mock quiet-hours simulation for low-risk operations. It is designed to help while an operator sleeps without granting broad production authority.

## Safety boundary

- No production action is executed automatically.
- Only allowlisted services, environments, and actions can run.
- `max_automatic_risk` defaults to `low`.
- Unknown, high-risk, production, exhausted-attempt, and failed-verification paths escalate with a human wake-up payload.
- Auth remains deferred; local examples use `X-OpsCat-*` demo headers.

## Policy knobs

Use `PUT /night-autopilot/policy` to audit a local policy update for the current tenant/workspace:

- `quiet_start` / `quiet_end` / `timezone`
- `max_automatic_risk`
- `max_attempts_per_incident`
- `allowed_services`
- `allowed_environments`
- `escalation_contacts`

The update is metadata-only and is recorded as `night_autopilot_policy_updated` in the audit log.

## Morning report evidence

Every simulation returns a morning report with:

- detected incident count;
- resolved incident count;
- escalated incident count;
- actions taken;
- blocked actions;
- verification outcomes;
- follow-ups;
- the incident evidence report.

The report is intentionally conservative: if policy cannot prove that the action is low-risk and allowlisted, OpsCat blocks the automatic path and escalates.
