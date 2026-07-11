# P109 Real Ops Benchmark Roadmap

## Objective

Replace hand-authored-only success claims with reproducible external evidence:

1. RCAEval telemetry cases for diagnosis and evidence-grounding accuracy.
2. MicroRemed execution results for remediation success and recovery quality.

P109 imports and evaluates artifacts. It does not start Kubernetes, inject
faults, execute Ansible, access credentials, or mutate a production system.

## Versioned Contracts

Every artifact carries `schema_version` and rejects unknown major versions.

- `p109.source_manifest.v1`: manifest ID, generated-at value supplied by the
  caller, allowed signer/key IDs, and one or more `p109.source_artifact.v1`
  entries.
- `p109.source_artifact.v1`: source ID, canonical HTTPS URL, immutable commit or
  release revision, license/citation, expected relative paths, dataset schema,
  compressed/decompressed byte and file-count ceilings, redirect host/path
  allowlist, SHA-256, and `p109.provenance_hashes.v1`.
- `p109.provenance_hashes.v1`: canonical manifest, downloaded bytes, extracted
  tree, normalized corpus, and optional public-attestation hashes. A checksum
  proves integrity, not the identity or independence of the submitter.
- `p109.rcaeval_case.v1`: case/source/system identity, immutable revision,
  incident group and time range, topology, and two disjoint envelopes:
  `candidate_visible_evidence` and `scorer_only_truth`. Visible observations
  preserve modality, timestamp, service, trace/span identity, attributes,
  value/message, raw relative path, and raw SHA-256. Truth contains only scorer
  labels such as root service, fault type, acceptable aliases, and evidence
  references; it is never serialized into candidate input or candidate-facing
  reports.
- `p109.microremed_bundle.v1`: bundle/run/source/environment/injection IDs,
  system/fault/difficulty, immutable source revision, model/method actor,
  `external_execution=true`, attempts, verifier evidence, raw artifact hashes,
  bundle hash, signature/public-attestation reference, and timestamps.
- `p109.microremed_attempt.v1`: ordered attempt ID, proposed and executed action
  IDs, playbook/action hash, start/end time, no-op flag, safety result, and raw
  before/after observation hashes. Submitted success fields are ignored.
- `p109.microremed_verifier.v1`: verifier ID distinct from the actor,
  implementation and policy hashes/versions, health-check specification or
  command hash, observation window, raw before/after observations and hashes,
  independently replayed result, signer/key ID, and signature or reviewed
  public-attestation binding.

The normalized RCA envelope follows the existing P97 hidden-truth boundary;
the outcome scorer follows P97 measured post-state semantics and additionally
classifies `verified_recovery`, `harmful`, `unnecessary`, `no_effect`, and
`unverified`. Natural recovery and no-op are never credited.

## Release Metrics

- RCA service localization Top-1 and Top-3 accuracy;
- fault-type accuracy;
- evidence-grounding precision and unsupported-claim rate;
- abstention accuracy for missing or conflicting telemetry;
- remediation attempt success rate;
- first-attempt recovery rate and mean attempts to recovery;
- harmful/unnecessary action rate;
- recovery verification rate and mean recovery duration;
- per-system and per-fault-family denominators.

No aggregate score may hide a failing system or fault family.
Every dataset/system/fault-family cell is emitted with an explicit denominator;
zero or missing cells are `null`/`unevaluable`, never passing. Release requires
all required cells to have nonzero denominators and all safety-zero gates to
pass, mirroring the explicit P57 bridge-gate style.

## Tickets

- P109-000 source provenance, license, revision, and checksum manifest.
- P109-001 bounded opt-in acquisition with archive/path safety.
- P109-002 RCAEval raw telemetry discovery and normalization.
- P109-003 RCAEval ground-truth and evidence contract.
- P109-004 diagnosis benchmark and per-family metrics.
- P109-005 MicroRemed result schema and provenance adapter.
- P109-006 execution-outcome and recovery-quality metrics.
- P109-007 external holdout split and contamination guard.
- P109-008 deterministic CLI, reports, and release evidence.
- P109-009 independent adversarial review and full verification.

## Authority Boundary

Default verification is offline and fixture-backed. Network acquisition is an
explicit bounded CLI operation. Runtime evaluation has zero auth, credential,
shell, subprocess, Kubernetes, Ansible, cloud, database, production-adapter,
or remediation-execution authority. MicroRemed execution must occur outside
OpsCat and export a signed/checksummed result bundle for import.

## Completion Gate

P109 completes only when provenance and contamination checks pass, metrics are
computed from raw records rather than submitted summaries, every denominator
is reported, safety failures block release, and independent review finds no
P0/P1 fail-open path.

Fixture-backed verification can prove parser and evaluator behavior only. It
must report `unevaluable_real_data_missing` and cannot satisfy a real-data
release gate. Real-data qualification requires immutable RCAEval source
revisions and independently verified MicroRemed result bundles with nonzero
per-system and per-fault-family denominators.

MicroRemed currently has no repository-root license file. P109 therefore ships
only a clean-room compatibility schema and importer; it does not redistribute
MicroRemed code or claim that imported runs are release-qualified until source
license/provenance and independent verification are supplied.

`p109-release` binds SHA-256 hashes for the source manifest, every raw artifact,
the normalized corpus, diagnosis and remediation reports, contamination report,
exact authority scan, release-profile output, and independent-review document.
The review records reviewer identity, reviewed implementation revision, every
bound hash, verdict, and findings; self-review or stale/mismatched hashes fail.
