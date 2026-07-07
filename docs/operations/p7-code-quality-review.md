# OpsCat P7 Code Quality Review

## Review scope

This review covers the P7 documentation and integration contract for `docs/operations/p7-ticket-roadmap.md`. It is intended for the coordinated P7 lanes:

1. P7-001/P7-002 replay harness and adversarial evals;
2. P7-003/P7-004 confidence calibration and self-critique gate;
3. P7-005/P7-006 blast-radius engine and action simulator;
4. P7-007/P7-008 incident memory and Night Autopilot v2;
5. P7-009/P7-010/P7-011/P7-012 failure-mode report, reliability dashboard, safety docs, and release evidence.

## Current worktree finding

At review time this worktree contains the P7 roadmap but not the future implementation modules listed by the roadmap, such as `app/services/replay_service.py`, `app/services/confidence_calibration.py`, `app/services/self_critique_service.py`, `app/services/blast_radius.py`, `app/services/action_simulator.py`, `app/services/incident_memory.py`, or `app/services/reliability_dashboard.py`. This review therefore locks the documentation, release-evidence, and safety-contract expectations that those lanes must satisfy when integrated.

## Quality gates for implementation lanes

- Keep the no-auth/local-mock boundary explicit in code, tests, docs, eval fixtures, and dashboard text.
- Prefer deterministic service-layer functions and local fixtures over external providers or hidden network calls.
- Fail closed when replay fixtures are malformed, evidence is weak, confidence is overcalibrated, blast radius is unknown, simulation cannot bound touched resources, or memory reports failed prior remediation.
- Keep report/dashboard surfaces read-only unless an API route already has the local-header principal and approval semantics used elsewhere in OpsCat.
- Make every reliability claim reproducible through a command, test, or generated local artifact.

## Documentation updates made by this lane

- Added `docs/security-review-p7.md` for P7 assets, threats, mitigations, and remaining production gaps.
- Added `docs/operations/p7-final-summary.md` as the P7 review/release evidence handoff.
- Linked P7 reviewer commands and artifacts from `docs/release-evidence.md`.
- Reinforced the no-auth/local-mock boundary in `ROADMAP.md`.
- Added `tests/test_p7_release_evidence.py` so future edits cannot silently drop the P7 documentation contract.

## Integration risks for the leader

- The final P7 summary should be updated with concrete integrated commits and command outputs after all implementation lanes merge.
- `scripts/run_replay_evals.py` and `/tmp/opscat-replay-evals-latest.md` are documented as required P7 reviewer surfaces; they must exist before claiming full P7 completion.
- If another lane adds browser mutation UX, it needs a separate auth/session safety decision because P7 currently keeps auth deferred.
