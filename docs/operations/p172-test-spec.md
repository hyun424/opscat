# P172 Test Spec

- Build the active investigator from the P169 observed-provider capability
  registry.
- Expose only typed allowlisted read-only queries for observed metrics, logs,
  traces, deploy history, health, and topology providers.
- Record every hypothesis revision, tool choice, result hash, contradiction,
  budget decrement, freshness check, and stop reason.
- Enforce at most eight read-only tool calls and one bounded model deliberation
  budget per episode.
- Reject unsupported tools, configured-but-unobserved providers, unavailable
  providers, free-form targets, credential requests, write methods, and stale
  critical evidence.
- Verify every action-ready conclusion cites at least two fresh independent
  source classes observed in P169.
- Compare active investigation against the P171 single-pass arm without
  increasing unsafe recommendations or healthy-window false alerts.
