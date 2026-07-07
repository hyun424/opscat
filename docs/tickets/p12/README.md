# P12 Tickets — Real Dataset Evaluation Harness

P12 validates OpsCat's local/mock judgment pipeline against real-dataset-shaped logs, metrics, and multi-signal incidents before adding LLM judgment. Auth remains deferred and normal verification does not download external datasets.

## Tickets

- [P12-001 — Dataset Source Manifest](p12-001-dataset-source-manifest.md)
- [P12-002 — Real Dataset Import Contract](p12-002-real-dataset-import-contract.md) — depends on P12-001
- [P12-003 — LogHub Real Sample Adapter](p12-003-loghub-real-sample-adapter.md) — depends on P12-002, P12-006
- [P12-004 — NAB Real Sample Adapter](p12-004-nab-real-sample-adapter.md) — depends on P12-002, P12-006
- [P12-005 — AIOps Multi-signal Adapter](p12-005-aiops-multi-signal-adapter.md) — depends on P12-002, P12-006
- [P12-006 — Label Mapping and Taxonomy Coverage](p12-006-label-mapping-and-taxonomy-coverage.md) — depends on P12-001
- [P12-007 — Dataset Fixture Pack](p12-007-dataset-fixture-pack.md) — depends on P12-003, P12-004, P12-005
- [P12-008 — Dataset Conversion CLI](p12-008-dataset-conversion-cli.md) — depends on P12-003, P12-004, P12-005, P12-007
- [P12-009 — Real Dataset Evaluation Runner](p12-009-real-dataset-evaluation-runner.md) — depends on P12-008
- [P12-010 — Evaluation Report and Baseline](p12-010-evaluation-report-and-baseline.md) — depends on P12-009
- [P12-011 — Verification Integration](p12-011-verification-integration.md) — depends on P12-009, P12-010
- [P12-012 — P12 Release Evidence](p12-012-release-evidence.md) — depends on P12-001 through P12-011

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.

## Final Gate

`bash scripts/verify.sh --profile full` must pass before P12 closure.
