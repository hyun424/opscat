# P172 Tickets

Dependency: canonical P171 benchmark readiness evidence. Any real staging
utility claim additionally requires non-informational live benchmark evidence. Owner surface:
evidence-gap-investigator adaptation, P169 observed-provider capability
registry, decision trace, and P172 documentation only until implementation
begins.

1. **P172-001 — Capability registry.** Expose only typed read-only queries for
   metrics, logs, traces, deploy history, health, and topology providers
   actually observed in the canonical P169 attachment.
2. **P172-002 — Source independence gates.** Reject configured-but-unobserved,
   unknown, unavailable, stale, unsupported, or credential-requiring providers
   before they can satisfy evidence requirements.
3. **P172-003 — Investigation trace.** Record every hypothesis revision, tool
   choice, result hash, contradiction, budget decrement, freshness check, and
   stop reason.
4. **P172-004 — Budget and fail-closed behavior.** Enforce at most eight
   read-only tool calls and one bounded model deliberation per episode. Budget
   exhaustion, stale critical evidence, target expansion, free-form URLs or
   queries, and write methods fail closed.
5. **P172-005 — Utility evidence.** Done when action-ready conclusions cite at
   least two fresh independent observed source classes and active investigation
   improves selective diagnosis utility over the P171 single-pass arm without
   increasing unsafe recommendations or healthy-window false alerts.
