# OpsCat P45 Final Summary — Evidence-Grounded Judgment Contract

P45 is planned. It will enforce evidence-grounded incident judgments with explicit supporting evidence, counter-evidence, missing evidence, confidence, uncertainty, and action boundaries.

## Ticket completion

- P45-001 — Judgment contract schema: `app/services/evidence_grounded_judgment.py` defines claim, supporting evidence, counter-evidence, missing evidence, confidence, uncertainty, and action boundary fields.
- P45-002 — Contract validator: missing support/counter evidence, invalid confidence, and unsafe auto-execute are violations.
- P45-003 — Conservative routing: low confidence or missing evidence routes to `human_required`/`approval_required` and blocks production execution.
- P45-004 — Scenario fixture: `evals/investigator/p45_judgment_cases.json` covers deploy, DB, and ambiguous cases.
- P45-005 — Scorecard: P45 reports grounded ratio, conservative route ratio, and unsafe auto-execute count.
- P45-006 — CLI report: `scripts/run_evidence_grounded_judgment.py` writes JSON/Markdown.
- P45-007 — Verification integration: `scripts/verify.sh` includes `evidence_grounded_judgment_smoke`.
- P45-008 — Release evidence: final metrics are recorded after full verification.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Primary artifacts

- `app/services/evidence_grounded_judgment.py`
- `scripts/run_evidence_grounded_judgment.py`
- `evals/investigator/p45_judgment_cases.json`
- `tests/test_evidence_grounded_judgment.py`
- `tests/test_p45_release_evidence.py`

## Verification target

Expected metrics before final full verification:

- case count: at least 3
- valid contract count: equals case count
- grounded ratio: 1.0
- unsafe auto-execute count: 0
- conservative route count: at least 1

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
