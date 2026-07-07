# OpsCat P8 Demo Script — AI Incident Responder War Room

This demo is for portfolio/reviewer use. It is local/mock only: no production credentials, live provider calls, Kubernetes/cloud/database mutation, hosted SaaS operations, or unattended production-operation claims are involved.

## Goal

Show one understandable P8 flow:

`alert -> war room -> score -> runbook critique -> action gate -> report`

## Commands

```bash
uv run --no-sync --extra dev python scripts/demo.py
```

Expected visible output includes:

- `P8 flow: alert -> war room -> score -> runbook critique -> action gate -> report`
- `P8 War Room URL: /operator/incidents/<incident-id>`
- `P8 boundary: local/mock only; does not claim unattended production operation`
- incident status, action gate policy, report path, and Night Autopilot local/mock summary.

## Reviewer walkthrough

1. Run the demo command.
2. Open the printed `P8 War Room URL` in a local app session or request it through `GET /operator/incidents/{incident_id}`.
3. Confirm the war room page shows:
   - reliability score that cannot bypass hard policy gates;
   - runbook critique/missing-evidence summary;
   - human question prompt for approval-gated decisions;
   - action gate with policy/status/target;
   - report export links for redacted evidence.
4. Follow the report link to inspect redacted incident evidence.

## Safety narration

Say explicitly: OpsCat is demonstrating a bounded local/mock AI Incident Responder. It does not add auth, does not perform live provider mutation, and does not claim unattended production operation. Approval remains API-instruction based until production auth/session design exists.

## Verification

```bash
uv run --no-sync --extra dev pytest -q tests/test_p8_demo.py tests/test_operator_dashboard_e2e.py
uv run --no-sync --extra dev python scripts/demo.py
bash scripts/verify.sh --profile full
```
