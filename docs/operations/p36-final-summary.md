# OpsCat P36 Final Summary — Approval Control Plane

P36 routes P35 shadow decisions through named local approval profiles. It records what would be auto-allowed, approval-required, or blocked without auth work, live calls, production mutation, or remediation execution.

## Ticket completion

- P36-001 — Approval profile manifest: `evals/approval/p36_profiles.json` defines local control profiles.
- P36-002 — Shadow decision intake: P36 loads P35 shadow cases and converts proposed/blocked actions into approval requests.
- P36-003 — Route evaluator: every request is routed as `auto_allowed`, `approval_required`, or `blocked`.
- P36-004 — Auto-approval boundary: only safe read-only/report/notification capabilities can be auto-allowed.
- P36-005 — Night-watch escalation: ambiguous or mutation-shaped mitigation remains approval-required or blocked.
- P36-006 — Safety scorecard: reports profile coverage, approval burden, blocked-untrusted count, unsafe auto count, and execution count.
- P36-007 — CLI report: `scripts/run_approval_control_plane.py` writes JSON/Markdown.
- P36-008 — Verification integration: `scripts/verify.sh` includes `approval_control_plane_smoke`.

## Primary artifacts

- `app/services/approval_control_plane.py`
- `scripts/run_approval_control_plane.py`
- `evals/approval/p36_profiles.json`
- `tests/test_approval_control_plane.py`
- `tests/test_p36_release_evidence.py`
- `docs/operations/p36-ticket-roadmap.md`
- `docs/operations/p36-final-summary.md`

## Boundary

No auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and does not claim unattended production operation.

## Verification result

Full verification passed with P36 included in `scripts/verify.sh`:

- profile count: 3
- request count: 10
- profile decision count: 30
- profile coverage: 1.0
- auto allowed count: 6
- approval required count: 12
- blocked count: 12
- blocked untrusted action count: 12
- unsafe auto action count: 0
- execution count: 0
- total coverage gate: 78.22% >= 60.00%
- `app/services/approval_control_plane.py` coverage: 89.62%

Generated artifacts: `/tmp/opscat-approval-control-plane-latest.md` and `/tmp/opscat-approval-control-plane-latest.json`.
