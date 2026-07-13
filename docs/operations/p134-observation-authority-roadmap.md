# P134 Observation Authority Contract

## Outcome

Define and qualify the machine-checkable boundary that separates observation
authority from action authority before OpsCat attaches any new provider-shaped
export or live read-only source.

P134 evaluates observation proposals and emits immutable decision receipts. It
does not read telemetry, open sockets, resolve credentials, invoke providers,
launch subprocesses, execute commands, deliver notifications, or remediate an
incident. P135 may consume the qualified local-artifact level for exported
files. P136 may later propose a separately reviewed opt-in live GET-only level.

## Authority levels

The closed observation-authority order is deliberately named `OA*` so it
cannot be confused with the existing action-authority levels:

1. `OA0_CONTRACT_ONLY` - all observation proposals are denied; only contract
   validation is available.
2. `OA1_LOCAL_ARTIFACT` - proposals may target bounded synthetic
   `local-artifact` labels with local stat/read/list methods; P134 qualifies
   only the policy decision, not the filesystem operation.
3. `OA2_PROVIDER_SHAPED_LOCAL_EXPORT` - reserved and denied until P135.
4. `OA3_OPT_IN_LIVE_GET_SHADOW` - reserved and denied until P136.
5. `OA4_CREDENTIAL_OR_EXTERNAL_READ` - forbidden while auth and an explicit
   credential authority contract remain deferred.

Action, mutation, notification delivery, credential access, shell execution,
and remediation are not observation levels. They remain governed by the exact
zero P120/P121 authority registry and cannot be enabled by a P134 contract.

## Canonical representation

Every P134 object is a strict JSON object. Unknown or missing keys fail closed.
Canonical hashes use UTF-8 JSON with sorted keys, compact separators, no NaN or
Infinity, and the existing `stable_hash` `sha256:` prefix. A self-hash excludes
only its own hash field. Labels match `[a-z0-9][a-z0-9._-]{0,63}`. Hash fields
match `sha256:[0-9a-f]{64}`. Timestamps are UTC second-precision RFC3339 values
`YYYY-MM-DDTHH:MM:SSZ`; offsets, fractions, naive times, and leap seconds fail.
Sequences and versions are integers from 1 through 1,000,000 and never booleans.
Lists are duplicate-free and stored in lexical order.

Unknown keys, booleans substituted for integers, URLs, IP literals, paths,
provider endpoints, credential-like names or values, headers, query strings,
shell fragments, mutation verbs, and free-form capabilities fail closed. The
five exact `OA*` enum strings are exempt only from the generic text scan; they
cannot appear in any other field.

## Contract envelope

`p134.observation_authority_core.v1` has exactly these fields:

- `schema_version`, `contract_id`, `contract_version`, `subject_ref_hash`;
- `max_authority_level`;
- `allowed_hosts`, `allowed_methods`, `allowed_capabilities`;
- `budgets`;
- `valid_from`, `expires_at`, `default_decision`, `kill_switch`;
- `action_authority`, `core_hash`.

`max_authority_level` is structurally one of the five closed levels, but P134
accepts a promotable core only at OA0 or OA1. OA0 requires empty allowlists. OA1
requires 1..64 `allowed_hosts` matching
`local-artifact(?:[.][a-z0-9][a-z0-9._-]{0,47})?`, a non-empty subset of
`LOCAL_STAT`, `LOCAL_READ_FILE`, and `LOCAL_LIST_DIR`, and a non-empty subset of
the closed capabilities. These are policy aliases and method declarations, not
paths, hostnames, or performed I/O. OA2/OA3/OA4 in a contract core fail with
`authority_level_not_qualified`; they may appear only in denied proposal cases.
`default_decision` is exactly `deny`. `kill_switch` is a JSON boolean.

`budgets` has exactly these positive integer fields and bounds:

- `window_seconds`: 60..86,400;
- `max_allowed_requests_per_window`: 1..1,000;
- `max_allowed_estimated_response_bytes_per_window`: 1..1,073,741,824;
- `max_allowed_estimated_records_per_window`: 1..10,000,000;
- `max_unique_hosts_per_window`: 1..64;
- `max_unique_methods_per_window`: 1..8;
- `max_unique_capabilities_per_window`: 1..32;
- `max_single_response_bytes`: 1..67,108,864;
- `max_timeout_ms`: 1..60,000;
- `max_attempt_number`: 1..10.

`action_authority` contains every P121 authority counter exactly once as an
integer zero. `valid_from` is strictly earlier than `expires_at`.

`p134.observation_review_receipt.v1` has exactly:

- `schema_version`, `contract_core_hash`;
- `decision` (`approve` or `reject`);
- `reviewer_ref_hash`, `reviewed_at`, `expires_at`;
- `limitations` exactly the lexical list
  `no_action_authority`, `oa2_oa3_oa4_blocked`, `policy_only_no_io`, and
  `reviewer_identity_unauthenticated`;
- `review_receipt_hash`.

The review time must fall inside the core validity interval and the review
expiry must be later than the review time and no later than core expiry. The
receipt proves only that the exact core bytes were structurally reviewed. It
does not authenticate the reviewer or provide an external signature.

`p134.observation_authority_contract.v1` has exactly `schema_version`, `core`,
`review_receipt`, and `contract_hash`. Missing or hash-mismatched review data is
a structural error. A valid `reject` receipt is evaluable but denies with
`review_not_approved`; expiry denies with `review_expired`.

## Closed capabilities

P134 recognizes only:

- `telemetry.metadata.read`;
- `telemetry.metrics.read`;
- `telemetry.logs.read`;
- `telemetry.traces.read`;
- `telemetry.events.read`;
- `telemetry.topology.read`.

The promoted P134 profile uses only `OA1_LOCAL_ARTIFACT`, three synthetic
`local-artifact.*` aliases, and the three local method declarations above.
This makes host/method unique budgets testable without adding real hosts or I/O.
OA2/OA3/OA4 and network-shaped methods are represented only by denied
adversarial cases.

## Proposal and decision receipts

`p134.observation_proposal.v1` has exactly `schema_version`, `request_id`,
`sequence`, `proposed_at`, `requested_level`, `source_ref_hash`, `host_label`,
`method`, `capability`, `estimated_response_bytes`, `estimated_records`,
`timeout_ms`, `attempt_number`, and `proposal_hash`. Byte and record estimates
are non-negative integers bounded by 67,108,864 and 10,000,000 respectively;
timeout and attempt are positive integers within the global maxima above.
`method` is structurally `LOCAL_STAT`, `LOCAL_READ_FILE`, `LOCAL_LIST_DIR`, or
reserved `HTTP_GET`; only the three local declarations can be allowed. The
proposal contains no URL, path, credential, header, payload, query, hostname
discovered at runtime, or arbitrary metadata.

Evaluation is pure and performs no observation. It validates the contract and
review receipt, enforces the kill switch, validity window, level, allowlists,
and all budgets against the supplied ledger. It emits one
`p134.observation_decision_receipt.v1` with exactly `schema_version`,
`receipt_id`, `sequence`, `request_id`, `proposal`, `proposal_hash`, `contract_hash`,
`contract_core_hash`, `review_receipt_hash`, `decision`, `reasons`,
`evaluated_at`, `previous_receipt_hash`, `counters_before`, `counters_after`,
`action_authority`, and `receipt_hash`. `proposal` is the complete canonical
strict proposal object and must hash to `proposal_hash`; it is safe to persist
because the proposal schema contains only labels and hashes, never paths,
credentials, payloads, or endpoints. `evaluated_at` is exactly `proposed_at`;
the evaluator never reads a wall clock. `receipt_id` hashes only contract and
proposal hashes. `decision` is `allowed` only when `reasons=[]`; otherwise it is
`denied` and reasons use this fixed order:

1. `contract_only_level`
2. `contract_not_yet_valid`
3. `contract_expired`
4. `review_not_approved`
5. `review_expired`
6. `kill_switch_active`
7. `authority_level_exceeds_contract`
8. `authority_level_not_qualified`
9. `host_not_allowlisted`
10. `method_not_allowlisted`
11. `method_not_qualified`
12. `capability_not_allowlisted`
13. `attempt_budget_exceeded`
14. `allowed_request_budget_exceeded`
15. `cumulative_byte_budget_exceeded`
16. `cumulative_record_budget_exceeded`
17. `host_budget_exceeded`
18. `method_budget_exceeded`
19. `capability_budget_exceeded`
20. `single_response_byte_budget_exceeded`
21. `timeout_budget_exceeded`

Malformed contracts, proposals, ledgers, or hashes raise a closed validation
error and create no receipt. A new denied proposal still appends one receipt and
increments evaluated/denied plus policy-denial and/or budget-denial accounting.
It never increments allowed request, byte, record, host, method, or capability
accounting. A reason numbered 1..12 is policy denial; 13..21 is budget denial;
mixed denials increment both denial-class counters once.

## Budgets and ledger

`p134.observation_receipt_ledger.v1` has exactly `schema_version`,
`contract_hash`, `window_started_at`, `window_ends_at`, `next_sequence`,
`receipts`, `counters`, `action_authority`, and `ledger_hash`. Window end equals
start plus the contract window exactly. Every new proposal sequence equals
`next_sequence`, including denials. The first receipt's
`previous_receipt_hash` is the canonical hash of exactly
`{"schema_version":"p134.ledger_genesis.v1","contract_hash":...,"window_started_at":...,"window_ends_at":...}`;
later receipts link the immediately prior receipt hash.

`counters` has exactly `evaluated_count`, `allowed_count`, `denied_count`,
`allowed_estimated_response_bytes`, `allowed_estimated_records`,
`budget_denial_count`, `policy_denial_count`, `unique_allowed_host_count`,
`unique_allowed_method_count`, `unique_allowed_capability_count`,
`allowed_host_counts`, `allowed_method_counts`, and
`allowed_capability_counts`. Scalar values and map values are non-negative
integers, never booleans. Map keys must be members of the contract allowlists;
unique counts equal the number of positive map entries.

Because each receipt embeds its canonical proposal, ledger validation must
recompute every before/after transition from the proposal estimates and
host/method/capability labels. Rehashing a fabricated counter sequence cannot
make it semantically current.

Request, cumulative byte/record, and unique host/method/capability budgets apply
only to the next otherwise-allowable proposal. The single-response, timeout,
and attempt budgets apply to every proposal. Denials consume only evaluated and
denial accounting. Duplicates consume nothing: before sequence validation, an
existing `request_id` with the same proposal hash returns the original receipt
and byte-identical ledger plus an out-of-band `duplicate=true` result. The
canonical matrix counts duplicate evaluations separately; the immutable ledger
does not contain a duplicate counter or duplicate receipt. An existing request
ID with a different proposal hash raises `request_id_reuse_conflict`.

A proposal outside the ledger window, earlier than the previous receipt time,
or carrying a non-next sequence is a structural `proposal_outside_ledger_window`,
`clock_rollback`, or `sequence_mismatch` error. It creates no receipt and leaves
the ledger byte-identical.

Counters are policy accounting, not proof that telemetry was read. P135/P136
must add execution receipts before claiming real observation. Clock rollback,
sequence gaps, receipt tamper, contract drift, or inconsistent counters block
the ledger.

## Independent review evidence

The runtime review receipt above is part of the product contract. Independent
plan/code review is separate process evidence in
`p134.independent_review.v1`. The release runner does not create it. A distinct
reviewer writes `evals/p134/independent-review.json` with exact source hashes,
`reviewer_role=independent_code_reviewer`,
`implementation_role=implementation_agent`, distinct non-secret context hashes,
integer P0/P1/P2/P3 finding counts, `decision=approve`, stated limitations, and
`independent_review_hash`. Release requires zero P0/P1/P2 and current source bindings. This
records writer/reviewer separation but, without auth, does not cryptographically
prove identity.

## Threat and trust boundary

- P134 is credential-free and network-free.
- It trusts only current hash-valid local input bytes supplied to the pure
  evaluator; it does not establish OS identity, authenticate a reviewer, or
  authorize a transport.
- Host labels are policy labels, not DNS resolutions.
- Estimated bytes/records are preflight budgets, not measured I/O.
- `p134.authority_ledger.v1` separates runtime authority from evaluator
  activity. Runtime uses exact-zero P121 counters plus exact-zero
  `telemetry_source_read_count`, `provider_call_count`, and `socket_call_count`.
  Non-authority evaluator activity reports integer `runner_invocation_count`,
  `profile_read_count`, and `artifact_write_count`. Evaluator authority reports
  exact-zero `subprocess_launch_count`, `signal_count`, `socket_call_count`,
  `credential_read_count`, and `telemetry_source_read_count`. The shell that
  invokes the runner is outside service runtime and is disclosed by
  `runner_invocation_count=1`; the runner itself launches no process.
- P134 grants no observation execution, action, mutation, delivery, or
  operator-replacement authority.

## Delivery slices

1. Contract core, closed levels, allowlists, redaction, and exact-zero action
   authority.
2. Hash-bound review receipt and validity/escalation gate.
3. Proposal validator and deterministic fail-closed decision engine.
4. Budget ledger, idempotency, sequence validation, and decision receipts.
5. Deterministic contract/fault matrices and local CLI runner.
6. Independent review, release evidence, docs, and `p134-release` verification.

## Required artifacts

- `app/services/p134_observation_authority.py`
- `app/services/p134_release_evidence.py`
- `scripts/run_p134_observation_authority.py`
- `tests/test_p134_observation_authority.py`
- `tests/test_p134_release_evidence.py`
- `evals/p134/input/authority-profile.json`
- `evals/p134/contract-matrix.json`
- `evals/p134/fault-matrix.json`
- `evals/p134/receipt-ledger.json`
- `evals/p134/authority-ledger.json`
- `evals/p134/independent-review.json`
- `evals/p134/release-evidence.json`
- `scripts/verify.sh` with a dedicated `p134-release` dispatch

## Completion gate

P134 is complete only when every required positive and adversarial case passes,
all artifacts are deterministic and hash-bound to current sources, independent
review has no unresolved P0/P1/P2 finding, the dedicated release profile passes,
and all credential, network, subprocess, command, remediation, staging mutation,
and production mutation counters remain exact integer zero. Release validation
must mechanically reject any claim of file ingestion, provider attachment, live
GET, notification delivery, remediation, or operator replacement.
