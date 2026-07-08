# OpsCat P47 Final Summary — Tool Selection Planner

P47 is planned. It will turn investigation requests into safe read-only tool plans while blocking mutation and unrestricted shell execution.

## Ticket completion

- P47-001 — Tool catalog: P47 defines read-only Grafana/Datadog/Sentry/deploy/log tool plans and blocked mutation markers.
- P47-002 — Planner: `app/services/tool_selection_planner.py` maps investigation requests to concrete tool calls.
- P47-003 — Safety validator: shell, rollback, restart, delete, write, mutate, scale, and kill requests are blocked.
- P47-004 — Evidence references: every selected tool keeps hypothesis and evidence refs.
- P47-005 — Approval policy: blocked or low-confidence plans require approval/human handling.
- P47-006 — CLI report: `scripts/run_tool_selection_planner.py` emits JSON/Markdown.
- P47-007 — Verification integration: `scripts/verify.sh` includes `tool_selection_planner_smoke`.
- P47-008 — Release evidence: final metrics are recorded after full verification.

## Boundary

No live API calls, no auth/session work, no production mutation, no remediation execution, no unrestricted shell, no default external model/API calls, and no unattended production-operation claim.

## Primary artifacts

- `app/services/tool_selection_planner.py`
- `scripts/run_tool_selection_planner.py`
- `evals/investigator/p47_tool_selection_cases.json`
- `tests/test_tool_selection_planner.py`
- `tests/test_p47_release_evidence.py`

## Verification target

Expected metrics before final full verification:

- case count: 3
- selected tool count: at least 6
- blocked tool count: at least 2
- unsafe selected count: 0
- read-only ratio: 1.0

Final verified metrics are recorded in `docs/release-evidence.md` after the full verification profile passes.
## Final verification

Full profile passed with coverage gate 79.31%; P47 smoke passed with selected_tool_count=6, blocked_tool_count=3, read_only_ratio=1.0, and unsafe_selected_count=0.
