# P172 Plan Review

Decision: approved for bounded active read-only evidence investigation only.

- Adapt the existing evidence-gap investigation behavior to the P169 observed
  provider capability registry.
- Treat canonical P169 release evidence as the sole provider-observation source;
  P172-local configuration cannot mint an observed capability.
- Expose only typed allowlisted provider queries for metrics, logs, traces,
  deploy history, health, and topology.
- Treat observed-provider source independence as a release gate: configured but
  unobserved, unknown, or unavailable providers cannot satisfy evidence
  requirements.
- Require every action-ready conclusion to cite at least two independent source
  classes with fresh evidence checked at decision time.
- Reject unsupported tools, free-form URLs or queries, credential requests,
  write methods, target expansion, budget exhaustion, and stale critical
  evidence before any approval-like conclusion.
- Until P169 proves live attachment, qualify only registry readiness with the
  fail-closed `attachment_required` route and no available tools.
