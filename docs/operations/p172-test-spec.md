# P172 Test Spec

- Build the active investigator from the P169 observed-provider capability
  registry.
- Reject P172-local provider declarations as observation evidence. If canonical
  P169 has no live-observed attachment, emit `attachment_required` with zero
  tools and zero tool calls.
- Bind canonical P169 file hash, release evidence hash, status, and live-observed
  flag as an explicit P172 secondary dependency validated again at release.
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
