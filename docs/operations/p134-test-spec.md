# P134 Test Specification

## Test-first rule

Behavioral tests must fail before implementation. Release evidence is added only
after the contract and evaluator tests pass. P134 tests must not open sockets,
read credentials, execute subprocesses from the service module, or perform a
real observation.

## Contract tests

- Accept only the five closed `OA*` authority levels and qualify only OA0/OA1.
- Reject action-like levels, unknown keys, malformed hashes, invalid times,
  boolean integers, OA1 empty allowlists, duplicate entries, URLs, IP literals,
  paths, credential-like fields/values, headers, provider endpoints, query
  strings, and mutation/shell fragments.
- Require empty allowlists for OA0; reject OA2/OA3/OA4 as a promotable contract
  maximum while allowing those exact enum values only in denied proposals.
- Require `default_decision=deny`, exact-zero P121 authority counters, bounded
  budgets, `valid_from < expires_at`, and a review receipt bound to the exact
  core hash.
- Reject missing, rejected, expired, stale, optimistic, or tampered review
  receipts. State explicitly that the receipt is not authenticated identity.

## Proposal and decision tests

- Allow valid OA1 `LOCAL_STAT`, `LOCAL_READ_FILE`, and `LOCAL_LIST_DIR`
  proposals for synthetic `local-artifact.*` aliases and closed capabilities
  without performing I/O.
- Deny OA2/OA3/OA4, reserved `HTTP_GET`, unknown hosts, unknown capabilities, excessive
  attempts, expired contracts, early contracts, kill-switch contracts, and every
  budget overflow before allowance.
- Structurally reject outside-window timestamps, clock rollback, and sequence
  mismatch with no receipt and a byte-identical ledger.
- Reject unrecognized `GET`/`HEAD`/`POST`/mutation method strings structurally;
  P134 recognizes only the three local declarations and reserved `HTTP_GET`.
- Reject paths, URLs, headers, credentials, payloads, free-form metadata,
  provider names, and unexpected proposal keys.
- Produce deterministic IDs and hashes from semantic inputs, not randomness or
  wall-clock reads.
- Re-evaluating the same canonical proposal reuses the same receipt and leaves
  the complete ledger byte-identical; the returned evaluation wrapper alone
  exposes `duplicate=true` for matrix accounting.
- Reusing a request ID with changed canonical bytes fails closed.

## Ledger tests

- Validate exact sequence, previous-receipt links, contract hash, receipt hash,
  before/after counters, and ledger hash.
- Validate the canonical proposal embedded in every receipt, require its hash
  to equal `proposal_hash`, and recompute all counter transitions from it.
- Require the exact contract/window-derived genesis hash for the first receipt
  and the immediately preceding receipt hash thereafter.
- Count evaluated/allowed/denied proposals exactly. Assert that the immutable
  ledger has no duplicate counter and no duplicate receipt.
- Count allowed estimated bytes and records only after policy allowance.
- Track unique and per-value host/method/capability counts exactly.
- Prove that new policy denials increment only evaluated/denied and
  policy-denial; new budget denials increment only evaluated/denied and
  budget-denial; mixed reasons increment both denial classes once. Neither
  class consumes allowed request/byte/record/unique budgets.
- Prove request/cumulative/unique budgets apply only to an otherwise-allowable
  proposal, while single-response, timeout, and attempt budgets apply to every
  proposal.
- Reject missing counters, negative counters, booleans, count regressions,
  unknown map keys, receipt reorder, receipt deletion, receipt duplication,
  and mixed-contract ledgers.
- Preserve exact-zero action authority in contract, receipt, ledger, and release
  evidence.

## Adversarial no-authority tests

- Monkeypatch socket creation, DNS lookup, HTTP clients, environment reads,
  subprocess launch, shell helpers, and command runners; service evaluation must
  not invoke them.
- Scan serialized artifacts for credential-like values, URLs, absolute paths,
  headers, raw reviewer labels, and raw subject labels.
- Any release claim of real file ingestion, provider export attachment, live
  GET shadow, delivery, remediation, or operator replacement must block release.
- Validate a separately authored `p134.independent_review.v1` with current
  source hashes, distinct reviewer/implementation context hashes, zero P0/P1/P2,
  and an explicit unauthenticated-identity limitation. The release runner must
  not generate this artifact.

## Deterministic matrix

The promoted runner must include at least these principal cases:

1. OA0 default deny.
2. OA1 allowed proposal.
3. deterministic duplicate.
4. capability denied.
5. host denied.
6. method denied.
7. level escalation denied.
8. kill switch deny.
9. contract not yet valid.
10. contract expired.
11. allowed-request budget exhausted.
12. byte budget exhausted.
13. record budget exhausted.
14. host budget exhausted.
15. capability budget exhausted.
16. response byte estimate too large.
17. timeout too large.
18. attempt budget exhausted.
19. tampered review receipt.
20. changed request ID replay rejected.
21. boolean counter rejected.
22. URL/credential-shaped input rejected.
23. ledger reorder rejected.
24. non-zero action authority rejected.

The denominator is fixed at 24 principal cases. Helper assertions may not
inflate the pass rate.

## Release gates

- Dedicated tests and static checks pass.
- Exactly 24/24 principal cases pass.
- The canonical matrix includes at least one allowed, one duplicate, and all
  named denial/fault classes.
- Service runtime performs zero telemetry/file source reads, credential reads, network
  calls, subprocesses, shell commands, provider calls, deliveries, remediation,
  staging mutations, and production mutations.
- `p134.authority_ledger.v1` reports runtime P121 counters and
  telemetry/provider/socket counters as exact zero; evaluator authority reports
  exact-zero subprocess/signal/socket/credential/telemetry reads; evaluator
  activity separately reports one runner invocation and exact non-negative
  profile-read/artifact-write counts.
- Canonical wall time is at most 20 seconds, self-plus-child CPU at most 10
  seconds, and peak resident memory at most 64 MiB.
- Source, input, summary, and release hashes are current and semantically
  validated.
- The canonical self-contained receipt ledger is promoted separately from the
  matrix summary and semantically revalidated during release.
- `scripts/verify.sh` exposes `p134-release` and runs targeted tests, Ruff, Mypy,
  the bounded runner, independent-review validation, and release validation.
- Release validation mechanically rejects a claim of actual observation,
  provider attachment, live GET, delivery, remediation, or operator replacement.
- Release status is exactly
  `p134_observation_authority_contract_qualified`.
