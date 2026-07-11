# P110 Test Specification

## Source and import

- Accept only the pinned RE1-OB file name, size, upstream MD5 and SHA-256.
- Reject traversal, symlinks, duplicate paths, excess files/bytes and checksum
  mismatch before extraction.
- Derive truth only from a validated `{service}_{fault}/{1..5}` path and reject
  unknown services, fault families, duplicate identities or missing telemetry.
- Never fabricate truth for the unlabeled multi-source sample.

## Hidden truth and evidence

- Candidate packets must omit labels directly and indirectly, including source
  paths, case directory names, truth hashes and qualification metadata.
- Pseudonymous case IDs are HMAC/domain-separated hashes, not label-bearing IDs.
- Evidence IDs are generated before model invocation and bind metric, service,
  window, statistic and source-byte hash.
- Every returned citation must resolve to the sealed packet; invented citations
  are counted and release-blocking.

## Model execution

- Default verification is offline and performs zero network calls.
- Live NVIDIA mode is explicit, requires a key, enforces call/case/token limits,
  uses bounded retries, and writes no secret into prompts, caches or reports.
- Provider output must be strict JSON. Unknown fields, labels in candidate
  context, duplicate case IDs, invalid service names, NaN confidence, and
  unbounded action text fail closed.
- Replay cache keys bind model, prompt schema, packet hash and decoding config.

## Evaluation

- Recompute service Top-1/Top-3, fault accuracy, evidence precision,
  unsupported citation rate, abstention, harmful-action rate and latency.
- Report exact numerators/denominators by fault and service.
- Split by complete incident case and keep repetitions from evaluation policy
  explicit. No row-level split is allowed.
- Require at least 25 holdout cases, five faults and five services for release.
- Report bootstrap 95% intervals and repeated-run exact agreement when repeated
  live outputs are present.

## Named RED cases

`path_label_leak`, `case_id_label_leak`, `normalized_truth_prompt`,
`invented_evidence_ref`, `submitted_score_lie`, `unknown_service`,
`malformed_provider_json`, `cache_key_mismatch`, `budget_overrun`,
`provider_error_as_pass`, `tiny_n_release`, `missing_fault_cell`,
`harmful_action`, `archive_traversal`, `archive_symlink`, `checksum_mismatch`,
`unlabeled_sample_truth_fabrication`, and `secret_in_report`.
