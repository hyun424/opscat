# P136-002 - Secure incremental index scanner

## Scope

Implement descriptor-relative bounded whole-index reads, complete-line parsing,
partial-line deferral, consumed-prefix integrity, global chain/sequence checks,
and fail-closed rotation continuity.

## Acceptance

- Symlink/hardlink/nonregular/identity races are rejected.
- Append, partial completion, valid rotation, replay, truncation, prefix mutation,
  gaps, forks, and parser budgets have regression tests.
- Pending partial state binds byte hash/length, file identity, line-start cursor,
  and observed size; committed cursor does not advance.
- Old-identity pending partial plus rotation fails closed.
- Rotated exact replay prefixes resolve from bounded canonical P136 state; only
  the first unseen entry carries rotation lineage.
- Prior checkpoint survives every rejected transition.
