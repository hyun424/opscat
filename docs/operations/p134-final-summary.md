# P134 Final Summary

## Result

P134 qualifies a deterministic, credential-free, network-free observation-
authority policy contract. The promoted release status is
`p134_observation_authority_contract_qualified`.

P134 decides whether an observation proposal would be permitted under a strict
contract. It does not perform the observation. It adds no file ingestion,
provider SDK or HTTP call, live GET, credential access, notification delivery,
command execution, remediation, staging/production mutation, or operator-
replacement authority.

## Implemented

- A separate five-level `OA*` hierarchy prevents observation permission from
  being confused with action authority. P134 qualifies only OA0 and OA1; OA2,
  OA3, and OA4 remain blocked for later reviewed phases.
- Strict canonical contract, structural review, proposal, decision receipt, and
  ledger schemas reject unknown fields, boolean integers, unsafe labels, URLs,
  paths, credential-like values, malformed timestamps, and non-zero P121 action
  authority.
- The pure evaluator enforces validity, review freshness, kill switch, level,
  host, method, capability, attempt, single-response, timeout, cumulative, and
  unique-value budgets without reading a clock or performing I/O.
- Immutable receipts embed the full canonical proposal. Ledger validation
  recomputes proposal hashes, deterministic receipt IDs, contract policy
  outcomes, counter transitions, genesis/previous links, sequence, and final
  counters, so rehashed forged allowances fail closed.
- Canonical duplicate proposals reuse the original receipt and byte-identical
  ledger. Changed request IDs, sequence drift, clock rollback, out-of-window
  requests, receipt reorder, counter tamper, and action-authority escape fail
  closed.
- Release evidence binds current sources, profile, matrices, ledger, authority
  accounting, exact claims, resource use, and a separately authored independent
  review. Reviewer identity is explicitly not authenticated.

## Promoted evidence

`evals/p134/` contains:

- `contract-matrix.json`: 18/18 cases pass, comprising one allowed case, 16
  deterministic denials, and one byte-identical duplicate.
- `fault-matrix.json`: 6/6 adversarial cases reject tampered review, changed
  replay, boolean counter, URL/credential-shaped input, ledger reorder, and
  non-zero action authority.
- `receipt-ledger.json`: two allowed policy decisions with 300 estimated bytes,
  30 estimated records, two hosts, two methods, and two capabilities.
- `authority-ledger.json`: runtime observation/action and evaluator authority
  counters remain exact integer zero; evaluator activity reports one invocation,
  one profile read, and five artifact writes.
- `independent-review.json`: current-source review with zero P0/P1/P2/P3 and the
  explicit unauthenticated-reviewer limitation.
- `release-evidence.json`: all eight release gates pass with an exact 24/24
  principal denominator.

The canonical run used 116 ms wall time, 113 ms CPU, and 28,196,864 bytes peak
RSS under the 20 s, 10 s, and 64 MiB limits.

## Reproduce

```bash
bash scripts/verify.sh --profile p134-release
```

The promoted release evidence hash is
`sha256:eed48c9b7192bccf7c4392cb7385b894c09c76f17d33e8990be6cbb00e8288fc`.

## Next dependency

P135 may consume OA1 only to parse bounded, credential-free provider-shaped
local export artifacts for Prometheus, Loki, Grafana, Sentry, and OpenTelemetry.
P135 must add provenance and execution receipts for actual local reads; it must
not introduce provider SDKs, live requests, credentials, delivery, remediation,
or mutation.
