# OpsCat Portfolio Demo

Run the five-minute local demo:

```bash
uv run --no-sync --extra dev python scripts/demo_agentic_loop.py
```

The command prints incident ID, correlation result, top cause, selected runbook, risk decision, action result, verify result, report path, and operator URL.

Why this is agentic AI: OpsCat observes provider-shaped signals, correlates them, diagnoses likely causes, plans from runbooks, applies deterministic risk policy, executes only safe local/approved actions, verifies recovery, and leaves an auditable trace.

Boundary: local/mock beta demo only; no production readiness or unattended production mutation is claimed.
