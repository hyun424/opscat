# P109 Test Specification

## Source and acquisition

- Require canonical HTTPS source, immutable revision, license note, expected
  paths, content checksum, maximum byte/file count, and dataset schema.
- Default mode performs no network call.
- Reject redirects to unsupported schemes, checksum mismatch, oversized files,
  archive traversal, symlinks, duplicate paths, and unknown source IDs.
- Reject moving branches/tags, cross-host or unexpected-path redirects,
  decompressed byte/file-count overflow, and normalized duplicate paths.

## RCAEval normalization

- Accept metrics, logs, traces, topology, and ground truth without flattening
  away timestamps, service identity, trace/span identity, or source modality.
- Reject missing case identity, duplicate observations, invalid timestamps,
  ground-truth leakage in visible evidence, and mismatched case directories.
- Detect scorer labels leaked through nested keys, filenames/directories,
  trace/span attributes, candidate context, reports, or release artifacts.
- Preserve raw source hashes and emit deterministic normalized JSONL.
- Enforce `p109.rcaeval_case.v1`; candidate serialization contains only
  `candidate_visible_evidence`. A separate scorer handle resolves
  `scorer_only_truth` after candidate output is sealed.

## Diagnosis evaluation

- Compute Top-1/Top-3 service localization, fault type, evidence precision,
  unsupported claims, abstention, latency, and tool-call counts.
- Report denominators per dataset/system/fault family.
- A missing family or zero denominator is unevaluable, never passing.
- Hidden labels cannot be supplied to the candidate agent context.

## MicroRemed result import

- Require environment, failure injection, run ID, model/method, attempts,
  actions/playbook hash, before/after health, verifier output, timestamps, and
  source revision.
- Recompute success from before/after health and verifier evidence; do not trust
  a submitted `success=true`.
- Reject missing attempts, impossible timestamps, unknown actions, duplicated
  runs, hash mismatch, recovery without verification, and safety violations.
- Require independent verifier ID, implementation hash, policy/version, raw
  observations, health-check spec/command hash, observation window, and
  verifier signature or reviewed public-attestation binding. Actor/model/method
  under test cannot be the sole verifier or signer.
- A checksum proves byte integrity only. Release trust additionally requires an
  allowed signer/key from the source manifest or an independently reviewed
  public release artifact. Self-signed and submitter-only attestations are
  smoke evidence, never release evidence.
- Validate `p109.microremed_bundle.v1`, ordered
  `p109.microremed_attempt.v1`, and `p109.microremed_verifier.v1`. Require
  `external_execution=true`; no OpsCat runtime path may create or execute an
  attempt.

## Remediation metrics

- Compute attempt success, first-attempt recovery, mean attempts, verified
  recovery, recovery duration, harmful and unnecessary action rates.
- Separate systems, fault families, and difficulty levels.
- Natural recovery or no-op cannot be credited as intervention success.
- Eligible denominator: runs with successful fault injection, valid immutable
  source revision, independent verifier evidence, and complete before/after
  windows. Missing/zero denominators produce `null` and `unevaluable`, not zero.
- Verified recovery numerator: eligible runs that begin unhealthy, execute a
  non-noop intervention, end healthy for the full verification window, have no
  safety violation, and pass independent replay. First-attempt recovery uses
  the same predicate with exactly one attempt. Attempt success is successful
  independently verified attempts divided by all executed eligible attempts.
- Classify every eligible attempt/run as `verified_recovery`, `harmful`,
  `unnecessary`, `no_effect`, or `unverified`. When a matched no-action control
  exists, recovery credited to the intervention additionally requires recovery
  earlier than the control by the declared minimum effect window. Without a
  control, spontaneous/no-op recovery remains uncredited.

## Holdout and release

- Split by source incident/run group and time, never by individual row.
- Detect fixture/source overlap and exact/near duplicate contamination.
- CLI JSON and Markdown are byte-stable.
- Release evidence binds source, normalized corpus, benchmark, authority scan,
  profile, and independent-review hashes.
- `p109-release` fails unless each required dataset/system/fault-family cell is
  present with a nonzero denominator, each metric includes numerator,
  denominator and nullable value, and every safety-rate numerator is zero.
- The release bundle binds source manifest, raw artifacts, normalized corpus,
  diagnosis/remediation reports, contamination report, authority scan, profile
  output and independent review. The review must identify a reviewer distinct
  from the implementation actor and bind the reviewed implementation revision
  plus all preceding hashes.
- Static authority scan forbids auth, credentials, shell/subprocess, Kubernetes,
  Ansible execution, cloud/database/production adapters, and online mutation.
- The scan enumerates exactly the P109 runtime modules and rejects imports/calls
  for `subprocess`, `socket`, HTTP clients, Kubernetes, Ansible runners, cloud
  SDKs, SQL/DB engines, action/executor services, credentials, and file writes
  outside the acquisition CLI. Runtime evidence has exact-zero counters for
  auth, credentials, shell, subprocess, Kubernetes, Ansible, cloud, DB,
  production adapter/mutation, executor, and online policy writes.

## Named RED cases

- `default_network_zero`, `moving_revision`, `redirect_escape`,
  `archive_traversal`, `archive_symlink`, `archive_size_bomb`,
  `normalized_duplicate_path`, and `unknown_source`.
- `nested_label_leak`, `filename_label_leak`, `span_attribute_label_leak`,
  `candidate_context_truth_leak`, and `scorer_truth_output_leak`.
- `submitted_accuracy_lie`, `submitted_success_lie`, `raw_tamper_after_cache`,
  and `stale_normalized_hash`.
- `natural_recovery_no_credit`, `noop_no_credit`, `safety_override`,
  `missing_verifier`, `self_verifier`, `missing_denominator`, and
  `family_aggregate_masking`.
- `incident_group_split_leak`, `time_split_leak`, `near_duplicate_holdout`, and
  `hidden_answer_export`.
- two-run byte-stable CLI, fixed/injected clock, stable ordering, offline
  default, and nonzero exit for unevaluable release mode.
- missing/stale release hashes, incomplete authority scan, self-review,
  mismatched source/normalized/benchmark hashes, and failing-family masking.
