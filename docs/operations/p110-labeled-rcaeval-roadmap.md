# P110 Labeled RCAEval Benchmark Roadmap

## Objective

Measure OpsCat's diagnosis quality on an official RCAEval dataset whose labels
are encoded by the upstream case directory structure. P110 must keep those
labels outside the candidate prompt, run deterministic offline/replay tests by
default, and permit explicitly opted-in NVIDIA model calls only for diagnosis.
No suggested remediation is executed.

## Official source

- Dataset: RCAEval RE1-OB, 125 Online Boutique incidents.
- Canonical record: Zenodo record `14590730`, file `RE1-OB.zip`.
- Upstream MD5: `47cce26ed24140e8974e68f9db2a5e9c`.
- Verified SHA-256: `4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4`.
- Label convention: `{root_service}_{fault_type}/{repetition}`.
- Fault families: cpu, mem, disk, delay, loss.

The archive is not committed. A bounded acquisition command downloads and
verifies it, or an operator may provide an already downloaded archive.

## Tickets

- P110-000 source contract and bounded acquisition.
- P110-001 official RE1-OB archive importer and label derivation.
- P110-002 candidate telemetry packet with scorer-only label isolation.
- P110-003 evidence feature extraction around the injection timestamp.
- P110-004 strict candidate output schema and evidence validation.
- P110-005 offline mock/replay and opt-in NVIDIA candidate runner.
- P110-006 Top-1/Top-3, fault, grounding, abstention, variance metrics.
- P110-007 incident-group holdout and contamination controls.
- P110-008 deterministic CLI, budget ledger, and release evidence.
- P110-009 independent adversarial review and full verification.
- P110-010 adversarial provenance hardening after review: sealed scorer truth,
  pinned source/replay/batch bindings, evaluator-owned action safety, and
  release requalification.
- P110-011 out-of-band cryptographic reviewer identity and provider-call
  attestation. Until configured, locally verified evidence is reportable but
  `release_qualified` remains false.

## Candidate boundary

The candidate receives only a pseudonymous case ID, system name, injection
timestamp, service/metric catalog, and evidence records derived from telemetry.
It never receives archive paths, source case directory names, root service,
fault type, scorer hashes, release qualification, or truth references.

The candidate may return ranked services, fault type, cited evidence IDs,
confidence, abstention, and optional advisory actions. Candidate-submitted
scores or success flags are ignored. Citations must resolve to the sealed
candidate packet. Advisory actions are scored for harmfulness but never run.

## Execution modes

1. `mock`: deterministic contract verification; no network.
2. `replay`: score sealed provider responses; no network.
3. `nvidia`: explicit opt-in, key-gated provider call with case/token/call
   ceilings and a content-addressed response cache.

Provider failure, malformed JSON, budget exhaustion, duplicate case output, or
cache mismatch becomes abstention and blocks release; it never becomes a pass.

## Release gate

P110 release evidence requires official archive checksum verification, at least
25 held-out cases, all five fault families, at least five root services,
nonzero denominators per required cell, zero truth leaks, zero invalid evidence
citations, zero harmful actions, exact artifact hashes, and independent review.
Live model quality is reported with bootstrap intervals and repeated-run
agreement; a single successful case cannot qualify a model.

## Authority boundary

The only online authority is HTTPS acquisition of the pinned dataset and an
explicit NVIDIA chat-completions request. P110 has zero shell-command,
subprocess, Kubernetes, Ansible, cloud mutation, database mutation, credential
export, production connector, or remediation execution authority.
