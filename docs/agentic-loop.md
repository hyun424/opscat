# OpsCat P6 Agentic Loop

OpsCat P6 implements a deterministic local/mock operations loop:

```text
observe -> correlate -> diagnose -> plan -> risk -> act -> verify -> report
```

- **Observe** accepts local mock/provider-shaped fixture signals; no production credentials are required.
- **Correlate** groups signals by tenant, workspace, service, environment, fingerprint, time window, provider reference, and deploy marker.
- **Diagnose** ranks root-cause candidates with confidence, evidence, counter-evidence, missing evidence, and a next diagnostic.
- **Plan** selects a bounded runbook from the local registry.
- **Risk** maps every action to `auto_execute`, `approval_required`, `human_required`, or `blocked` using deterministic policy.
- **Act** executes only safe local/mock actions or approval-gated dry-run artifacts.
- **Verify** records recovery evidence and escalates when recovery is not proven.

Decision traces are stored as redacted `decision_trace` evidence and timeline entries. The trace API is `GET /incidents/{INCIDENT_ID}/trace`; the operator detail view links to it.

## Local boundary

P6 remains a beta/local portfolio milestone. It does not implement OIDC/SSO/login, unrestricted shell execution, production customer credential collection, or unattended production mutation.
