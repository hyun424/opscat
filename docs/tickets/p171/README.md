# P171 Tickets

Dependency: canonical P170 wall-clock soak-runtime readiness evidence. Any live
quality claim additionally requires completed P170 24-hour evidence. Owner surface:
truth sealing, blinded evaluation inputs, adjudication schema, benchmark runner,
and P171 documentation only until implementation begins.

1. **P171-001 — Sealed episode schema.** Store agent-visible evidence separately
   from operator-confirmed labels for root cause, affected service, precursor
   onset, severity, response class, natural recovery, uncertainty, and citations.
2. **P171-002 — Baseline comparison.** Run deterministic baseline, current LLM
   candidate, and no-action baseline on the same sealed episodes with identical
   visibility.
3. **P171-003 — Sample gate semantics.** Produce only informational point
   estimates below 30 labeled incident/precursor episodes or 200 healthy
   windows. Require separately pre-registered sample sizes for confidence-bound
   claims, including at least 300 healthy windows for a zero-observed false-alert
   1% upper-bound claim.
4. **P171-004 — Metric gates.** Report top-1 root-cause accuracy, top-3 recall,
   precursor recall, healthy false-alert rate, citation validity, unsupported
   diagnosis count, unsafe recommendation count, calibration, selective
   accuracy, abstention, OOD behavior, confidence intervals, and per-family
   denominators.
5. **P171-005 — Claim controls.** Done when aggregate scores cannot hide a
   failed family and reports explicitly state whether results are informational
   or confidence-bound qualified.
