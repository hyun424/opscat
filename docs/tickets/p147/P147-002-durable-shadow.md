# P147-002 — Durable offline provider shadow

Status: DONE

- Implement bounded read-only providers, evidence-gap tools, cursor, heartbeat, restart, and deadman.
- Keep real endpoints explicit opt-in and noncanonical.
- Depends on: P147-001.
- Write scope: `app/services/p147_durable_shadow.py` and the minimal shared
  `app/services/p147_p152_contracts.py` contract surface.
- Acceptance: all five selectors GREEN; 8/8 cases; one restart resume and one
  deadman; bounded investigation calls; canonical network/model/action zero.
- Stop: mutation capability, unbounded query loop, cursor regression, or secret
  persistence.
