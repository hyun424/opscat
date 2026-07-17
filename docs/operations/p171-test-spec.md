# P171 Test Spec

- Seal outcome labels separately from agent-visible staging evidence.
- Evaluate root cause, affected service, precursor onset, severity, recommended
  response class, natural recovery, uncertainty, citations, and abstentions.
- Compare deterministic baseline, current LLM candidate, and no-action baseline
  on the same sealed episodes.
- Produce only an informational report below 30 labeled incident/precursor
  episodes or 200 healthy windows.
- Require separately pre-registered confidence-bound sample gates before any
  promotion claim, including at least 300 healthy windows for a zero-observed
  false-alert 1% upper-bound claim.
- Verify top-1 root-cause accuracy, top-3 recall, precursor recall, healthy false
  alert rate, citation validity, unsupported diagnosis count, unsafe
  recommendation count, calibration, selective accuracy, abstention, OOD
  behavior, and per-family denominators.
