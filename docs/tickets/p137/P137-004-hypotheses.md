# P137-004 - Hypothesis ranking

## Scope

Implement incident-scoped hypotheses with closed categories, closed statement
codes, support edges, contradiction edges, missing-evidence items, exact atom
classification fields, the closed relation/weight/classifier table,
deterministic integer scoring, and stable ranking.

## Acceptance

- Hypotheses use only closed categories and closed statement codes.
- Support, contradiction, and missing-evidence edges bind exact evidence atom
  hashes, reason codes, windows, weights, request need class, and edge hashes.
- Statement codes, reason codes, atom-field enums, evidence-state-to-edge rules,
  denominator-failure mapping, total input-to-statement mapping, and integer
  score formulas are the closed sets from the roadmap.
- Closed reason codes include separate `decisive_counter_signal` and
  `weak_counter_signal` entries. Weak counter input maps to
  `weak_counter_signal` with `contradicts_soft` weight `-2`; decisive counter
  input maps to `decisive_counter_signal` with `contradicts_decisive` weight
  `-5`.
- Statement, reason, marker, counter-signal, and denominator-failure rules read
  only the explicit atom fields produced by P137-002 conversion. They must not
  read raw P120/P135 records or assume P120 has `risk_flags`.
- Missing evidence splits into `LOCAL_SELECTION` and `EXTERNAL_UNAVAILABLE`;
  unavailable needs are never executed. P135 adapter denominator failures use
  the source-bound generic `p135_adapter_failure` plus
  `local_catalog_selectable` mapping from P137-002 and do not infer
  `EXTERNAL_UNAVAILABLE` from arbitrary failure-reason text.
- Ranking sorts by deterministic semantic score tuple. Lexical hypothesis hash
  orders storage only and does not resolve semantic top-hypothesis ties.
- Tests cover support dominance, contradiction suppression, blocking missing
  evidence, unavailable external needs, benign-pattern ranking, and
  deterministic ties.
- Probability floats, invented evidence, free-form classifications, and
  unbounded edge lists fail closed.
