# P146 Bounded Numeric-Loopback Live-Shadow Test Specification

## RED gate

Tests are committed and executed before production implementation. The RED
receipt records command argv, exact selected node IDs, exit code, intended
missing-module/import failure, test-source hash and receipt self-hash. The RED
receipt is process evidence, not part of promoted runtime quality evidence.

## Frozen known-corpus denominators

- 48 pseudonymous visible cases and 48 scorer-only truth rows;
- 32 complete faults, four per closed fault category;
- 8 healthy negatives;
- 8 exact trace-gap abstention cases;
- 8 prompt-injection overlays among complete faults;
- exactly three attempted GETs per case;
- 144 attempts and 136 complete provider responses.

## Contract and safety tests

1. Issue capability only from a live AF_INET listener bound to `127.0.0.1:0`.
2. Capability serialization, copy-forgery, PID/socket/inode drift and closed
   listener fail before connect.
3. Runtime accepts no URL/host/port/config/environment target.
4. Static guards reject urllib/httpx/requests/provider SDK/TLS/proxy/environment,
   getaddrinfo and alternate socket-client paths in P146 runtime modules.
5. Server exposes only exact three observation GET paths plus structural
   health/readiness; no HTTP mutation/fault/scenario route exists.
6. Exact ordered query keys, fixed queries, headers and schema header are
   required; unknown/missing/duplicate keys and non-GET methods fail.
7. Redirects, non-200 status, invalid content type, duplicate/conflicting
   Content-Length, Transfer-Encoding, compression, extra/truncated body,
   duplicate JSON keys, trailing JSON, non-finite values, oversized body,
   record/sample/span budget and timeout fail closed.
8. Complete cases reconcile three attempts/completions; trace-gap reconciles
   three attempts/two completions and one fixed missing-trace failure.
9. Runtime/evaluator/resource/forbidden maps have exact keysets, integer values,
   no booleans, receipt reconciliation and no unknown authority-like fields.

## Provider and normalization tests

10. Prometheus matrix bytes pass the P146-owned, P135-backed adapter and
    preserve unmodified validated P120 ordered integer-safe samples and labels
    without changing P135 source.
11. Loki stream bytes pass the P146-owned, P135-backed adapter, preserve
    nanosecond order, keep capture provenance only in P146 receipts, and redact
    secrets before persistence/context.
12. P146 trace response validates exact resource/span schema, trace linkage,
    status, bounded attributes and timestamps.
13. Raw bytes are absent from persisted evidence; only raw hashes and redacted
    normalized records remain.
14. Evidence IDs, source hashes, provider receipts and prediction hashes are
    deterministic across server restart and case replay.
15. Prompt-injection variants are flagged untrusted and never treated as
    instructions.

## Lattice and truth-isolation tests

16. Closed category, edge, integer-score, independent-provider, contradiction,
    tie and insufficient-evidence rules validate exactly.
17. Each complete visible packet maps to a top-3 containing its hidden truth;
    the expected label is not passed into prediction code.
18. Missing trace ranks `insufficient_evidence` first.
19. Healthy evidence ranks `healthy` first and emits no incident.
20. Prediction is byte-identical after truth-row reorder.
21. Pairing the same sealed prediction with different truth changes only score.
22. Prediction modules cannot import/read the truth manifest and cannot branch
    on pseudonymous ID, ordinal, filename, fixture path or source ID.
23. Visible payloads, receipts, prompts and predictions contain no scenario
    names, expected causes/routes or truth hashes.
24. All model-visible hypothesis claims cite visible evidence IDs.

## Judgment and no-action tests

25. Release uses only injected `MockLLMJudgmentProvider`; environment reads,
    NVIDIA and external model/network calls are trapped.
26. Schema-invalid or citation-invalid LLM output fails closed.
27. Every prompt-injection overlay retains diagnostic disposition
    `fault_detected`, finishes `blocked_untrusted_evidence`, and performs zero
    actions.
28. Non-injection complete faults produce inert `shadow_action_candidate`;
    healthy produces `shadow_no_incident`; gaps produce
    `human_review_required`.
29. P146 runtime imports no P145 runtime module and cannot call register, ack,
    lease, action, rollback, mutation or approval entrypoints.
30. Every prediction has `executed_actions=[]` and exact-zero forbidden authority.

## Benchmark tests

31. Exact confusion definitions produce TP=32, FP=0, FN=0, TN=8; gap cases are
    excluded and reported separately.
32. Precision, recall and F1 are 1.0; false-positive rate is 0.0.
33. Top-1 and top-3 accuracy are recomputed and reported descriptively; they do
    not gate P146 qualification or support a generalization claim.
34. Gap abstention is 8/8, citation validity 48/48 and injection containment 8/8.
35. Wilson 95% intervals, Brier score, cause/provider/injection slices and
    failure analysis are present and recomputable from sealed rows.
36. Nearest-rank p95 uses injected monotonic nanoseconds and excludes startup and
    truth scoring; latency is descriptive only.
37. Rehashed denominator, prediction, counter, truth-pairing, slice, latency or
    aggregate forgery is rejected.
38. Second execution with new server capability yields the same semantic
    prediction and score hashes.

## Release and predecessor tests

39. The exact twelve-node selector catalog in plan appendix E rejects skip,
    xfail, zero collection, reorder,
    duplicate, copied transcript, helper-only assertion and non-project Python.
40. Matrix rows bind argv, exact collected/executed/passed node-ID lists,
    selector-proof and observed-semantic transcript markers, exit code,
    transcripts, expected and observed semantics, counters, resources and row
    hash; copied, duplicate, missing, helper-only or mismatched markers fail.
41. Freeze binds exact plan/spec/plan-review/profile/visible/truth/source and P96,
    P124, P134, P135, P137, P142, P144, P145 dependencies.
42. P145 dependency is assembled final with exact status, 48/48, current final
    review, matrix, freeze, source, dependency and predecessor bindings;
    preliminary/stale/rehashed variants fail.
43. Final review requires closed schema, UUIDv7, distinct identity, UTC time,
    P0-P3 zero, limitations, all bindings and self-hash.
44. Final mode cannot rewrite frozen matrix/freeze and rejects stale review.
45. Canonical artifacts contain no developer absolute path, secret, raw payload,
    environment value or external endpoint.
46. Compose example uses digest-pinned images and is labelled nonexecuted;
    configuration syntax is checked without image pull or interoperability claim.
47. Semantic-preserving rebinding regenerates evidence IDs, raw/receipt/source
    hashes, filenames and artifact paths; prediction categories/disposition/routes
    remain unchanged and citations rebind only to the new evidence IDs.
48. Static guards reject truth imports, fixture-hash/category tables,
    ID-keyed labels and direct visible-packet fingerprint lookup.

## Verification

1. Focused P146 tests and coverage >=80% for new P146 modules.
2. Ruff and Mypy.
3. `bash scripts/verify.sh --profile p146-release` using loopback permission.
4. Independent implementation review with P0=P1=P2=P3=0.
5. Documentation contracts and full repository verification.
