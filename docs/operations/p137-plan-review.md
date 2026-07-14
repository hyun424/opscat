# P137 Plan-Readiness Review

Review date: 2026-07-14

Verdict: APPROVE

## Scope

Reviewed only:

- `docs/operations/p137-evidence-to-incident-roadmap.md`
- `docs/operations/p137-test-spec.md`
- `docs/tickets/p137/*.md`

Inspected for feasibility only:

- P120 normalization source/tests
- P134 observation authority source/tests
- P135 provider export attachment source/tests
- P136 incremental observer source/tests and fixtures

No planning docs or implementation files were modified during the review except
this approval artifact, which was created only after approval.

## Review Rounds and Resolutions

1. P136 handoff and validator feasibility:
   - Confirmed the plan uses actual P136 validator call shapes:
     `validate_incremental_observer_config(p136_config)`,
     `validate_observer_runtime_authority(p136_config, authority, now=now)`,
     and `validate_promotion_record(promotion, expected_entry=expected_entry,
     runtime=runtime)`.
   - Confirmed the plan assigns `segment_receipt_bytes` validation to P137 and
     does not claim P136 validates those bytes.
   - Confirmed checkpoint membership is planned against
     `checkpoint.promotion_keys[promotion.entry_hash] == complete canonical
     promotion record`, with embedded `promotion_key` recomputed separately.

2. Canonical byte and handoff publisher readiness:
   - Confirmed the plan requires canonical lowercase hexadecimal exact bytes,
     rejects uppercase/prefix/odd/empty/non-hex encodings, verifies
     `decoded.hex()` round trip, descriptor length, and byte hashes.
   - Confirmed the handoff publisher work includes genesis sequence/root,
     persisted root, next-sequence allocation, previous-hash chaining,
     checkpoint binding, atomic replace, file fsync, parent fsync, and recovery.

3. P120/P135 conversion readiness:
   - Confirmed P137 does not infer semantics from arbitrary P135
     `failure_reason` or P120 `str(exc)` strings.
   - Confirmed denominator-failure conversion requires current P135 failure
     bundle validation, P120 `fail_closed`, exact equality to the sole P120
     `state_reasons` element, normalized failure-label equality when present,
     and maps validator-accepted failures to closed P137 codes.
   - Confirmed success/context conversion is total over actual P120/P135 fields
     and rejects unknown P120 state reasons.

4. Classification, requests, runtime activity, and release matrix:
   - Confirmed weak and decisive counter reasons are separate and have distinct
     weights.
   - Confirmed classification is fail-closed for `aborted_fail_closed` only when
     both classification write and ledger CAS succeed.
   - Confirmed the closed request catalog has exactly 15 entries and matrix rows
     30-44 use them in roadmap lexical order.
   - Confirmed the release matrix has exactly 60 rows and includes SIGINT,
     SIGTERM, corrupt state, CAS conflict, rollback, same-sequence fork,
     previous-hash discontinuity, torn fixed-path replacement, four crash points,
     bounded continuous mode, heartbeat/readiness/stale handoff, and resource
     exhaustion.
   - Confirmed runtime activity, forbidden authority, evaluator activity, and
     resource maps are specified as exact schemas; delta profiles must materialize
     full post-override maps and reject profile-only aliases.

5. Authority and source-bound release gates:
   - Confirmed P137 preserves zero auth/provider/network/credential/action/
     remediation/notification/mutation authority.
   - Confirmed plan-readiness review is separated from final frozen-source
     implementation review, and final release validation must consume frozen
     matrix plus review artifacts without regenerating reviewed inputs.

## Mechanical Checks

- `awk` matrix row count over
  `docs/operations/p137-evidence-to-incident-roadmap.md`: 60 rows.
- Rows 30-44 are the exact 15 request catalog entries in lexical order:
  `compare_current_window_to_promoted_baseline`,
  `fetch_record_by_evidence_id`, `join_records_by_entity_and_window`,
  `select_records_by_content_hash`, `select_records_by_entity_ref`,
  `select_records_by_label_hash`, `select_records_by_provider`,
  `select_records_by_risk_flag`, `select_records_by_signal_family`,
  `select_records_by_system_id`, `select_records_by_time_window`,
  `select_rejections_by_reason`, `summarize_log_preview_hashes`,
  `summarize_numeric_samples`, `summarize_topology_refs`.
- Targeted feasibility tests:
  `uv run pytest tests/test_p120_normalization.py tests/test_p135_provider_export_attachment.py tests/test_p136_incremental_observer.py tests/test_p136_runner.py`
  passed: 81 passed, 1 existing Starlette deprecation warning.

## Reviewed File Hashes

```text
0bfbe287cc070c312cac3391ec0b836624f771d266fb595a6b4c7ab4d046b19a  docs/operations/p137-evidence-to-incident-roadmap.md
57ccd9565ef67fd15f5469d899bcee248ec3d2ec1e1bccb3eaef5e710a6f4d7d  docs/operations/p137-test-spec.md
72e91d06009d090e103b374a46b5fe7d57914584a8077519db62d151681534b5  docs/tickets/p137/P137-001-contract-schema.md
0f940eb5b89587de48cf254097c2f549d12f88a0fea132d4a6818244a144b137  docs/tickets/p137/P137-002-p136-ingest.md
9fca2b9349a1cff56b518b8166cbbe96d98000222898af3590725a326664d20a  docs/tickets/p137/P137-003-correlation.md
c5b475a1cb5e8d005e65a72632b21accbb2b26b9c59a4a5b89a2a9418e60d7a0  docs/tickets/p137/P137-004-hypotheses.md
53273491ee732e77a6ab741b130445a46c304f3fa7bd3afdbc9ab6aacc36bea1  docs/tickets/p137/P137-005-bounded-evidence-requests.md
ebaeeeacab56b7c052368c3bd6b36ad61838f6805f9ba2252254c885af4a4007  docs/tickets/p137/P137-006-classification-ledger.md
61c4cff348890b6afc180062fbef040eac7592d10b59161ccc4660a30770581b  docs/tickets/p137/P137-007-recovery-lease-signals-budgets.md
0313eea03cc185e7bc09aaa194c9e1a3e421e938ca74b69832305416bea9cac4  docs/tickets/p137/P137-008-canonical-runner-cli.md
753bda1cfed497b3b91ca284671f94690315bdf9e81bcbcfa20bf0cb81a8d4ca  docs/tickets/p137/P137-009-release-evidence-docs-review.md
b95db78d0868bb22f68b78fb5bd424e60ab8d46758acf82c29b0cbff06423d5b  docs/tickets/p137/P137-010-final-verification.md
27ff432a2c275adfb9e590af24db1569cd739ae564952f4c35bb5ad59075fb5c  docs/tickets/p137/README.md
d40a735ea0656001c4b84538d3701a78e59639f33e55bce1f59b2583dd8897be  app/services/p120_normalization.py
539447062ff98814c5de910893d1479c830a2d8b782b3d05cc3b51290fe02aad  app/services/p134_observation_authority.py
e6e217c90d415dad719cf923f3bc8429db6439aa513cf0f3364944b1d1484488  app/services/p135_provider_export_attachment.py
1ee59e336dec58b11351e593e1a2abee76d208722397d066fad99e297440c8de  app/services/p136_incremental_observer.py
5dbacb15a776511cebab3e2daeac8bec5ac26de962dcc6299057226ff0c728c8  tests/test_p120_normalization.py
d11cb26b6d8bbccdadd8126c4f1bcb3de47d3fa7e6cf0809d65ee6d60e3d7492  tests/test_p134_observation_authority.py
8b76e8b57b346880d803423425435fd5bd079b4d8b7996dff98582f064c6ae47  tests/test_p135_provider_export_attachment.py
2309c86b610ee6ca9a807421d38bf5e969a8d974c76a575ac606d61c0a43863a  tests/test_p136_incremental_observer.py
a153019450416b7b090d5c6a8b960eb603a57ce4ad67e13d433c444850482a03  tests/test_p136_runner.py
22d9cbe866f38f4e8f7d6b0ab6f31c7fa8c9316e19f22b716a63046981480c68  tests/fixtures/p136/builders.py
```

## Limitations

- This is a plan-readiness review, not a final implementation review.
- No P137 implementation exists in this review scope.
- The approval is bound to the exact file contents and hashes above.
- The final P137 implementation still requires source-bound review over frozen
  source, docs, profile, fixtures, and canonical matrix output.

## Final Decision

APPROVE. P0=0, P1=0, P2=0, P3=0.
