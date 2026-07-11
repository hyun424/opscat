# P121-008: docs, test spec, release evidence, crash/replay, and independent review

## Goal

Produce P121 roadmap, adversarial test spec, independent-style plan review,
ticket README, ticket files, release evidence requirements, crash/replay proof,
and honest bounded claim language.

## Contract

- Maintain planning artifacts:
  `docs/operations/p121-proactive-prevention-roadmap.md`,
  `docs/operations/p121-test-spec.md`,
  `docs/operations/p121-plan-review.md`,
  `docs/tickets/p121/README.md`, and tickets P121-001 through P121-008.
- Require release evidence to include hashes, denominators, confidence
  intervals, leading-indicator metrics, forecast metrics, evidence acquisition
  yield, counterfactual utility, false-positive metrics, alert-fatigue metrics,
  rollback metrics, harm metrics, causal attribution, recurrence reduction,
  crash/replay receipts, authority scans, unresolved risks, and exact counters,
  all zero.
- Require crash/replay coverage before and after indicator capture, forecast
  creation, evidence acquisition, decision selection, fatigue suppression,
  approval, L3 enqueue, L3 attempt, validation, rollback, attribution,
  recurrence update, and report write.
- Require independent review authored by a separate context from planner and
  implementer.
- Limit final claims to local/mock/sandbox proactive prevention readiness.

## Acceptance

The adversarial test spec covers evidence-before-action, forecast horizons,
counterfactuals, false positives, alert fatigue, deterministic approval,
rollback, validation, holdouts, calibration, abstention, authority boundaries,
crash/replay, independent review, and honest claims. Release evidence includes
required metrics and exact authority counters, all zero. Independent review
rejects production readiness, auth completion, live authority,
aggregate-only claims, self-review, and retuning on holdouts.

## Stop Rules

Stop if documentation or release evidence expands P121 into source/test work
during the planning turn, production authority, live connector authority,
credential handling, production or staging mutation, online policy mutation,
operator replacement, self-review, aggregate-only claims, post-holdout
retuning, omitted crash/replay proof, nonzero authority counters, or any claim
beyond local/mock/sandbox proactive prevention readiness.
