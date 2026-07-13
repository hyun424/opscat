# P135 Test Specification

## Test-first rule

Behavioral tests must fail before P135 implementation. Tests may read only
temporary local fixtures. They must monkeypatch and fail on socket, DNS, HTTP,
credential/environment, subprocess, shell, signal, delivery, action, or
remediation access.

## Manifest and authority tests

- Accept only the five closed provider/format pairs and valid signal families.
- Require exact-key schemas, canonical hashes, lexical unique source IDs,
  bounded integers that reject booleans, strict UTC timestamps, and a P134
  contract hash plus allowed OA1 decision receipt for every artifact.
- Reject missing, denied, duplicate, stale, expired, tampered, wrong-method,
  wrong-capability, wrong-source, wrong-estimate, or wrong-contract P134 data.
- Reject absolute/traversal/empty/dot/NUL/URL/URI/drive/shell/credential-shaped
  paths and expected sizes or records outside manifest/P134 budgets.
- Reject provider/format/signal mismatches and source ID reuse with changed
  canonical bytes.
- Require exact separate authority and observation-activity counter maps;
  reject missing, unknown, boolean, nonzero-authority, and misplaced values.

## Filesystem tests

- Read a regular UTF-8 file beneath an allowlisted temporary root through a
  root-relative descriptor and return exact SHA-256/byte/stat evidence.
- Reject symlinks in any path component, hard links, FIFOs, sockets, devices,
  directories, paths outside the root, changed inode, changed size/mtime,
  growth, truncation, and content-hash mismatch.
- Enforce per-file/total byte caps before and during chunked reads; never
  allocate based on an untrusted declared length.
- Reject invalid UTF-8, duplicate JSON keys, NaN/Infinity, over-depth,
  over-node, over-string, over-line, over-attribute, and over-record payloads.
- Assert no absolute path or raw payload appears in receipts or promoted
  release artifacts.

## Provider adapter tests

- Prometheus: accept a successful matrix result, preserve deterministic sample
  order, reject non-success/vector/scalar/malformed samples/non-finite values.
- Loki: accept successful streams with decimal nanosecond timestamps, stable
  label order, and bounded lines; reject matrix in the streams adapter,
  malformed timestamps, nested structured metadata, and overlong lines.
- Grafana: accept a Classic dashboard with integer schema/version and panel
  list; emit topology records; reject V1/V2 resources, missing title/panels,
  duplicate panel IDs, and claims that panel declarations are observed values.
- Sentry: accept a bounded top-level issue-list array; reject custom wrappers,
  malformed counts/times, duplicate issue IDs, and unbounded nesting. Event
  detail payloads require a separate future format version.
- OpenTelemetry: accept JSONL lines containing exactly one of resourceMetrics,
  resourceLogs, or resourceSpans; enforce lower-camel keys, decimal-string
  64-bit times, unique attribute keys, and deterministic resource/scope order;
  require the same declared signal family for every line in one artifact;
  reject mixed-signal files, unknown top-level signals, invalid hex IDs,
  non-integer enum names, and multiline JSON values. Multiple single-signal
  OTLP artifacts may coexist in one manifest.
- For every adapter, convert untrusted text to redacted/hash-bound evidence;
  never interpret payload text as an instruction.

## Normalization and provenance tests

- Produce exact-key deterministic P135 records wrapping complete independently
  validated P120 normalized records with stable IDs/hashes.
- Bind every record to provider, source ID, artifact hash, ordinal, selected
  source-record hash, and one execution receipt.
- Hash unknown/sensitive attribute values, bound labels/previews, and preserve
  useful metric values, units, severity, timestamps, service/name references.
- Detect and flag credential-like content, control characters, prompt-like
  action text, and invalid/unknown timestamps without exposing the secret.
- Reordering provider fields must not change semantic output; reordering source
  records must change ordered bundle provenance.
- Reject a bundle with rehashed changed bytes, record count, ordinal, source
  hash, adapter identity, or artifact binding.

## Receipt and ledger tests

- Recompute receipt IDs, previous links, pre/post identity hashes, counter
  transitions, authority counters, and ledger hash.
- Count successful non-duplicate file reads, bytes, and records exactly.
- Identical reattachment securely re-opens, re-reads, and re-hashes the current
  file, returns the original receipt and byte-identical success ledger, and
  discloses the duplicate validation read out of band.
- Changed content/spec with an existing source ID fails closed.
- Reject deletion, reorder, duplicate receipt, mixed contract/manifest,
  fabricated success, forged counters, wrong bundle hash, and any non-zero
  provider/network/credential/process/action authority.
- Disclose failed-read activity separately without promoting a success receipt.
  Any failure after content was read emits a hash-bound denominator-visible
  failure bundle containing a full P120 fail-closed record.

## Adversarial no-authority tests

- Patch `socket.socket`, DNS resolution, common HTTP clients, `os.environ`,
  subprocess/process helpers, shell helpers, signal senders, connector methods,
  delivery methods, and action executors to raise if called.
- Scan canonical outputs for URLs, absolute paths, credential/header values,
  raw log bodies, raw exception bodies, provider endpoint claims, raw
  production/staging target identifiers, and live-proof language.
- A release claim of live API use, authenticated provider identity, delivery,
  remediation, mutation, or operator replacement must block release.

## Fixed 30-case matrix

1. Prometheus matrix attachment succeeds.
2. Loki streams attachment succeeds.
3. Grafana dashboard topology attachment succeeds.
4. Sentry issues attachment succeeds.
5. Single-signal OTLP JSONL attachment succeeds.
6. Identical duplicate revalidates current bytes and keeps success ledger idempotent.
7. Denied P134 receipt blocks before read.
8. Wrong P134 capability blocks before read.
9. Byte estimate exceeded blocks before content read.
10. Record estimate exceeded fails closed without promotion.
11. Manifest total byte budget exceeded.
12. Manifest total record budget exceeded.
13. Absolute/traversal path rejected.
14. Symlink/hard-link/non-regular artifact rejected.
15. Source ID reuse with changed content rejected.
16. Prometheus wrong result type rejected.
17. Loki malformed nanosecond timestamp rejected.
18. Grafana duplicate panel ID rejected.
19. Sentry duplicate issue identity rejected.
20. OTLP mixed-signal artifact rejected.
21. Duplicate JSON key rejected.
22. Non-finite number rejected.
23. UTF-8/string/line structural budget rejection.
24. Prompt-injection text is flagged, redacted, and never executed.
25. Sensitive attribute value is hashed and absent from output.
26. Content hash mismatch rejected.
27. File mutation/replacement during read rejected.
28. Rehashed bundle/receipt/ledger forgery rejected.
29. Non-zero forbidden authority rejected.
30. Live/provider/credential/action claim blocks release.

The denominator is fixed at 30. Helper assertions do not increase the score.

## Release gates

- Dedicated tests, Ruff, Mypy, canonical runner, independent review validation,
  release validation, and full verification pass.
- Exactly 30/30 principal cases pass with all five providers represented.
- Canonical promoted bundles and execution ledger revalidate independently.
- File-read activity is exact and all forbidden authority is exact zero.
- Every successful and post-read fail-closed record wraps a valid
  denominator-visible P120 record.
- Source, fixture, review, matrix, ledger, bundle, summary, and release hashes
  are current.
- Release status is
  `p135_provider_shaped_export_attachment_qualified`.
