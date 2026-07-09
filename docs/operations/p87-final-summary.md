# P87 Final Summary

P87 implemented the Supervisor Run Report Artifact as a deterministic local/mock reporting layer over P86-style supervisor run state. It emits structured JSON and Markdown that explain run status, stop reason, terminal classification, item outcomes, checkpoint timeline, safety gates, next action, wakeup guidance, human decision requirements, audit metadata, claim boundary, and zero side-effect counters.

## Completed tickets

- P87-001 - Added report artifact schema with run ID, status, stop reason, terminal/non-terminal classification, audit metadata, claim boundary, and zero side-effect counters.
- P87-002 - Added completed, skipped, blocked, and resumable item summaries with duplicate completed item protection for resumed runs.
- P87-003 - Added checkpoint timeline rendering with cursor, completed item IDs, skipped item IDs, and event summaries.
- P87-004 - Added safety gate classification for evidence insufficiency, approval blocked, sandbox blocked, failure streak, budget limit, and max iterations.
- P87-005 - Added next recommended action, wakeup metadata, and human decision required sections.
- P87-006 - Added deterministic fixture scenarios for completed_all, max_iteration, needs_human, failed_guardrail, no_safe_work, and resumed-run reports.
- P87-007 - Added CLI JSON/Markdown smoke output and verification wiring.
- P87-008 - Added conservative release documentation without unattended production-operation claims.

## Verification

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_supervisor_run_report_artifact.py tests/test_p87_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app/services/supervisor_run_report_artifact.py scripts/run_supervisor_run_report_artifact.py tests/test_supervisor_run_report_artifact.py tests/test_p87_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app/services/supervisor_run_report_artifact.py scripts/run_supervisor_run_report_artifact.py tests/test_supervisor_run_report_artifact.py tests/test_p87_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev python scripts/run_supervisor_run_report_artifact.py --cases evals/actions/p87_supervisor_run_report_artifact.json --output-json /tmp/opscat-supervisor-run-report-artifact-latest.json --output-md /tmp/opscat-supervisor-run-report-artifact-latest.md`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs`

## Boundary

P87 does not execute actions, shell commands, processes, agents, live API calls, network calls, credential reads, external model calls, remediation, or production mutations. It is a local/mock report artifact, not unattended production operation.
