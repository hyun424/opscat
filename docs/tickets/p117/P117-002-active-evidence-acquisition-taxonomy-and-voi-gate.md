# P117-002: active evidence-acquisition taxonomy and VOI gate

## Goal

Model active evidence acquisition as a benchmark decision that requests typed
evidence classes when acting is not yet justified.

## Contract

- Define a frozen evidence-acquisition taxonomy for missing metric, log,
  topology, deploy/config, saturation, dependency, queue, DNS, certificate,
  quota, validation, and rollback evidence classes.
- Compute value of information from expected utility delta, uncertainty
  reduction, acquisition cost, and authority constraints.
- Emit only declarative evidence requests through `investigate_more` or
  `abstain`; never emit live connector calls, URLs, credentials, shell, query
  text, or mutation instructions.
- Detect taxonomy names, ordering, filenames, prompts, and markdown summaries
  that leak hidden labels.

## Acceptance

Correct `investigate_more` is at least 0.90 when required evidence is absent,
live-access request count is 0, taxonomy leakage probes pass, and every evidence
request cites the missing evidence marker that caused it.

## Stop Rules

Stop if evidence acquisition becomes a retrieval capability, connector call,
credential scope, or hidden-label side channel.
