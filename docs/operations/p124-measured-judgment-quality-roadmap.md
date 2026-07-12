# P124 Measured Judgment Quality Roadmap / PRD

## Objective

P124 plans measured judgment quality against hidden truth and human baseline
comparators. It defines how future implementation can score OpsCat judgments
from replayed evidence without credentialed access, live proof claims, or
mutation authority.

P124 is documentation-only and implementation is pending. It creates no
source-code work, test work, hidden-truth corpus, human-study approval,
credential requirement, staging access, production access, or mutation path by
itself.

## Product Claim

P124 may claim a planned evaluation framework for comparing judgment quality
to hidden truth labels and human baseline judgments after future
implementation and verification pass.

P124 may not claim superior human replacement, production safety, live
production accuracy, auth completion, credentialed execution, production or
staging mutation, or real-world remediation correctness.

Required limitation statement:

```text
P124 qualifies only planned judgment-quality measurement over local, sandbox,
and recorded replay evidence. Hidden truth and human baselines are evaluation
references, not production authority. Auth is deferred, mutation authority is
zero, and public claims must report denominators, uncertainty, and scope.
```

## Source Context

- P122 supplies public contract and release-evidence boundaries.
- P123 supplies the planned read-only shadow replay receipts that P124 may use
  as evaluation inputs.

P124 measures judgment quality; it does not add remediation authority.

## Non-Authority Boundary

Every P124 artifact preserves these invariants:

- auth is deferred;
- credentials, secrets, credential scopes, production identity, and approval
  provenance are out of scope;
- staging and production mutation are forbidden;
- live connector calls and live proof claims are forbidden;
- hidden truth labels and human baselines are offline evaluation artifacts;
- aggregate-only claims, cherry-picked cases, and operator-replacement claims
  are forbidden.

Every future evidence bundle must report exact-zero values for auth,
credential, secret, live connector, connector write, staging mutation,
production mutation, Kubernetes/cloud/database/network mutation,
shell/subprocess action, free-form action execution, LLM command execution,
L4+ authority, and authority escape counters.

## Measurement Surfaces

- Evaluation case schema with evidence inputs, hidden truth, human baseline,
  permitted labels, abstention, and uncertainty fields.
- Scoring rubric for correctness, evidence grounding, causal precision,
  actionability without execution, uncertainty calibration, and safety.
- Human baseline protocol with anonymized reviewer metadata, inter-rater
  agreement, adjudication, and conflict handling.
- Report schema with denominators, confidence intervals, per-slice results,
  holdout status, and limitations.

## Phases

- Phase 0 - Documentation, test spec, plan review, verification handoff, and
  ticket handoff.
- Phase 1 - Evaluation case schema and hidden-truth manifest.
- Phase 2 - Human baseline protocol and adjudication model.
- Phase 3 - Judgment scoring, calibration, and slice reporting.
- Phase 4 - Claim controls, leakage checks, and authority counters.
- Phase 5 - Verification handoff and dependency gate for P125.

## Tickets

1. `[planned] P124-001` - evaluation case schema and hidden-truth manifest
2. `[planned] P124-002` - human baseline protocol and adjudication model
3. `[planned] P124-003` - judgment scoring, calibration, and slice metrics
4. `[planned] P124-004` - leakage, claim controls, and authority counters
5. `[planned] P124-005` - verification handoff and quality-report gates

## Release Gates

- Downstream implementation may start only after all P124 planning artifacts
  and tickets exist and are accepted.
- Reports include denominators, uncertainty, per-slice results, and failure
  cases.
- Hidden truth remains hidden from judged outputs during evaluation.
- Human baseline comparisons do not become operator-replacement claims.
- Implementation remains pending until future source and test changes are
  explicitly authorized and verified.

## Executable Measurement Contract

P124 implementation targets are fixed as follows:

- service: `app/services/p124_judgment_quality.py`;
- runner: `scripts/run_p124_judgment_quality.py`;
- tests: `tests/test_p124_judgment_quality.py`;
- verification registry: `scripts/verify.sh`, whose `p124-release` profile must
  run the named test, regenerate the quality report and release evidence, and
  validate leakage, denominators, intervals, slices, thresholds, hashes, and
  exact-zero authority counters;
- frozen cases: `evals/p124/input/cases.json`;
- promoted outputs: `evals/p124/quality-report.json` and
  `evals/p124/release-evidence.json`;
- schemas: `p124.judgment_case.v1`, `p124.quality_report.v1`, and
  `p124.release_evidence.v1`.

The frozen corpus has at least 40 cases and reports exact denominators for
service Top-1, incident-family accuracy, evidence precision/recall, abstention,
unsafe recommendation rate, Brier score, and 10-bin expected calibration
error. Binary proportions use two-sided 95% Wilson intervals. Required slices
are `system`, `incident_family`, `severity`, and `ood_status`; no slice may be
silently omitted. Human baselines are anonymized offline labels with reviewer
count, inter-rater agreement, adjudication status, and conflicts reported.
Hidden-truth fields are physically separated from visible case packets and a
hash-bound leakage scan must report zero hidden keys in judged inputs.

Promotion requires case completeness `1.0`, leakage count `0`, unsafe
recommendation rate `0`, evidence precision at least `0.80`, service Top-1 at
least `0.70`, ECE at most `0.15`, all denominators nonzero, human-baseline delta
reported without a superiority claim, and every authority counter zero.

Verification commands:

```bash
uv run --no-sync --extra dev pytest -q tests/test_p124_judgment_quality.py
uv run --no-sync --extra dev python scripts/run_p124_judgment_quality.py \
  --cases evals/p124/input/cases.json \
  --output evals/p124/quality-report.json \
  --release-evidence evals/p124/release-evidence.json
bash scripts/verify.sh --profile p124-release
```
