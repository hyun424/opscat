# OpsCat P36 Final Summary — Approval Control Plane

P36 routes P35 shadow decisions through named local approval profiles. It records what would be auto-allowed, approval-required, or blocked without auth work, live calls, production mutation, or remediation execution.

## Ticket completion

- P36-001 — Approval profile manifest: pending implementation.
- P36-002 — Shadow decision intake: pending implementation.
- P36-003 — Route evaluator: pending implementation.
- P36-004 — Auto-approval boundary: pending implementation.
- P36-005 — Night-watch escalation: pending implementation.
- P36-006 — Safety scorecard: pending implementation.
- P36-007 — CLI report: pending implementation.
- P36-008 — Verification integration: pending implementation.

## Primary artifacts

- `app/services/approval_control_plane.py`
- `scripts/run_approval_control_plane.py`
- `evals/approval/p36_profiles.json`
- `tests/test_approval_control_plane.py`
- `tests/test_p36_release_evidence.py`
- `docs/operations/p36-ticket-roadmap.md`
- `docs/operations/p36-final-summary.md`

## Boundary

No auth/session work, no live API calls, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Verification target

Expected metrics before final full verification:

- profile count: at least 3
- request count: at least 4
- profile coverage: 1.0
- unsafe auto action count: 0
- execution count: 0
- blocked untrusted action count: at least 1
- auto allowed count: at least 1

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
