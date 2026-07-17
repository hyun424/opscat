# P166 Tickets

Dependency: canonical P165 release. Owner surface: sealed evaluator in the
shared service, P166 fixtures/tests, runner/verifier, and `evals/p166`.

1. **P166-001 — Commitment.** Split evidence from sealed truth, hash prediction
   before truth-open time, and reject truth/outcome/resolution fields embedded
   in evidence.
2. **P166-002 — Metrics.** Recompute top-1/top-3, precursor recall, healthy false
   positive rate, lead time, abstention quality, and citation validity from
   immutable rows.
3. **P166-003 — Adversarial validation.** Reject missing citations, future
   leakage, altered truth, altered aggregate, altered row, or self-hash.
4. **P166-004 — Evidence.** Done when top-3 and citation validity equal 1.0,
   precursor recall is at least 0.80, false positives at most 0.05, prediction
   always precedes truth opening, and authority counters are zero.
