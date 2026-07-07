# OpsCat P12 Ticket Roadmap — Real Dataset Evaluation Harness

## Requirements Summary

P12 validates whether OpsCat's existing local/mock incident judgment pipeline works on real-dataset-shaped logs and metrics before adding an LLM judgment layer. P11 expanded synthetic coverage; P12 adds a controlled harness for public or locally supplied datasets without putting downloads or large datasets into normal verification.

Boundary remains unchanged:

- no OIDC/SSO/login/password/session/CSRF browser auth work;
- no real production mutation, Kubernetes/cloud/database execution, unrestricted shell, customer credentials, or hosted SaaS claims;
- no external dataset download during normal verification;
- large public datasets are referenced through a manifest and local path import only;
- repo fixtures are tiny redacted samples, license-safe, and deterministic;
- automatic actions remain local/mock, allowlisted, policy-gated, simulated, audited, reversible, and test-backed.

## P12 Goal

Build a **Real Dataset Evaluation Harness** where OpsCat can:

1. register external dataset sources by manifest without downloading them;
2. ingest locally supplied LogHub/NAB/AIOps-shaped samples;
3. normalize real rows/windows/incidents into OpsCat `JudgmentCase` records;
4. preserve source labels for anomaly, incident type, and root-cause where available;
5. run the existing P10 benchmark over imported cases;
6. report conversion quality, label coverage, benchmark scores, and unsupported records;
7. keep full verification bounded with small built-in samples.

## P12 Tickets

### P12-001 — Dataset Source Manifest

**Outcome:** Define a manifest format for supported real-dataset sources.

**Acceptance criteria:**

- Manifest records dataset name, family, homepage/citation, license note, expected local path, supported files, labels, and import mode.
- Manifest explicitly states that normal verification does not download external data.
- Manifest supports LogHub-style logs, NAB-style metrics, and AIOps-style multi-signal datasets.

### P12-002 — Real Dataset Import Contract

**Outcome:** Define the import contract for local paths and normalized rows.

**Acceptance criteria:**

- Import API accepts only local files/directories.
- Unknown or missing paths fail with actionable errors.
- Import results include accepted, skipped, unsupported, and redacted counts.

### P12-003 — LogHub Real Sample Adapter

**Outcome:** Convert real LogHub-shaped local samples into judgment cases.

**Acceptance criteria:**

- Supports common LogHub fields such as timestamp, level/label, component, message, and anomaly/session labels.
- Produces anomaly, false-positive, and unknown-log-anomaly cases when labels are present or absent.
- Preserves source dataset metadata without leaking secrets.

### P12-004 — NAB Real Sample Adapter

**Outcome:** Convert real NAB-shaped local metric CSV/JSON samples into judgment cases.

**Acceptance criteria:**

- Supports timestamp/value windows and optional anomaly labels.
- Produces spike, no-data, stale, and healthy/false-positive cases.
- Stores baseline/current/ratio signal metadata deterministically.

### P12-005 — AIOps Multi-signal Adapter

**Outcome:** Convert AIOps-style incident samples containing logs, metrics, events, and labels.

**Acceptance criteria:**

- Supports JSON/JSONL incident records with logs, metrics, events, incident_type, and root_cause labels.
- Emits required evidence for every signal family present.
- Maps labels into expected hypotheses, route, and verification criteria.

### P12-006 — Label Mapping and Taxonomy Coverage

**Outcome:** Standardize external labels into OpsCat's internal taxonomy.

**Acceptance criteria:**

- Maps raw labels to anomaly status, incident class, root-cause hypothesis, severity, expected route, and tags.
- Reports unmapped labels separately instead of silently dropping them.
- Keeps mappings deterministic and test-backed.

### P12-007 — Dataset Fixture Pack

**Outcome:** Add tiny repo-local real-dataset-shaped fixture samples.

**Acceptance criteria:**

- Includes one LogHub-shaped sample, one NAB-shaped sample, and one AIOps-shaped sample.
- Fixtures are small, redacted, synthetic-or-license-safe excerpts, and suitable for normal verification.
- Fixture manifest explains provenance and boundary.

### P12-008 — Dataset Conversion CLI

**Outcome:** Add CLI for converting local dataset samples into OpsCat judgment cases.

**Acceptance criteria:**

- CLI supports `--family loghub`, `--family nab`, and `--family aiops`.
- CLI writes judgment cases and an import quality report.
- CLI refuses download URLs and remote paths.

### P12-009 — Real Dataset Evaluation Runner

**Outcome:** Run converted real-dataset-shaped cases through the P10 benchmark.

**Acceptance criteria:**

- Runner converts local samples, executes benchmark, and emits JSON/Markdown reports.
- Output includes import quality, benchmark score, route coverage, label coverage, and unsupported records.
- Runner can operate on fixture samples in bounded verification.

### P12-010 — Evaluation Report and Baseline

**Outcome:** Produce reviewer-friendly real-dataset evaluation reports.

**Acceptance criteria:**

- Report separates anomaly detection, incident classification, and response judgment signals.
- Report states limitations of labels and unsupported rows.
- Report states local/mock/no-auth/no-download boundary.

### P12-011 — Verification Integration

**Outcome:** Add bounded real-dataset fixture evaluation to eval/full profiles.

**Acceptance criteria:**

- `scripts/verify.sh --profile eval` runs fixture dataset evaluation.
- `scripts/verify.sh --profile full` runs fixture dataset evaluation.
- Docs profile validates P12 release evidence.

### P12-012 — P12 Release Evidence

**Outcome:** Close P12 with reproducible evidence and roadmap updates.

**Acceptance criteria:**

- Final summary maps P12-001 through P12-012 to code/tests/docs.
- Release evidence includes conversion/evaluation commands and temp artifacts.
- `bash scripts/verify.sh --profile full` passes before closure.

## Execution Order

1. P12-001 Dataset Source Manifest
2. P12-002 Real Dataset Import Contract
3. P12-006 Label Mapping and Taxonomy Coverage
4. P12-003 LogHub Real Sample Adapter
5. P12-004 NAB Real Sample Adapter
6. P12-005 AIOps Multi-signal Adapter
7. P12-007 Dataset Fixture Pack
8. P12-008 Dataset Conversion CLI
9. P12-009 Real Dataset Evaluation Runner
10. P12-010 Evaluation Report and Baseline
11. P12-011 Verification Integration
12. P12-012 P12 Release Evidence

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P12 closure.
