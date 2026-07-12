# P125-003: data-loss ledger and durability assertions

## Goal

Define durable record accounting for future long-running shadow runs.

## Contract

- Track events, observations, judgments, receipts, audit records, counters,
  and reports.
- Report lost, duplicate, malformed, and recovered counts.
- Fail closed on missing ledgers or non-integer counts.

## Acceptance

Future resilience reports can substantiate zero-data-loss claims within local
or sandbox scope.

## Stop Rules

Stop if data-loss claims omit denominators or promote unexplained losses.

