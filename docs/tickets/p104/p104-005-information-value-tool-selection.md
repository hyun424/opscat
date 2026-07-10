# P104-005 - Information-Value Tool Selection

## Goal

Choose the next read-only diagnostic by deterministic information-value proxy:
unresolved criticality, contradiction resolution, freshness refresh need,
source diversity, prior attempts, unavailable tools, and tool cost.

## Tests First

- Highest-ranked tool resolves the most important remaining critical gap.
- Contradiction-resolution tools outrank optional supporting evidence tools.
- Attempted tools are not selected again unless a freshness refresh is allowed.
- Unavailable tools are not retried in the same episode.
- Ranking does not consume hidden expected-tool/scorer labels.

## Implementation Notes

- Produce a ranked list for reports, but execute at most one selected tool per
  decision step.
- Reuse P103's repeated-tool prevention pattern and count prevented repeats.
- Refresh attempts require a new trace ID and must be reported separately.

## Acceptance

- Repeated tool execution counter remains zero except explicitly allowed
  freshness refreshes.
- Tool selection is explainable from public requirements and evidence states.

## Verification

Run targeted P104 tests and benchmark equal-state checks after P104-009.
