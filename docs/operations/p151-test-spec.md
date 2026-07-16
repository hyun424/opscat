# P151 Ground-Truth Quality Test Specification

Schema/status: `p151.report.v1`, `p151.freeze_manifest.v1`,
`p151.final_review.v1`, `p151.release_evidence.v1`, and
`p151_ground_truth_quality_qualified`. Artifacts and command are the exact P151
entries in the program plan.

1. Truth is sealed and inaccessible until a separate truth-free prediction
   packet and its pre-existing prediction/action-recommendation commit are
   validated. The prediction packet must not contain truth/provenance fields or
   contamination markers, and preliminary/final modes never create that commit.
2. Reordering truth changes scoring only; identifiers, filenames, and source hashes cannot influence prediction.
3. Recompute recall, false-positive rate, top-1/top-3, citations, abstention,
   lead time, tool efficiency, action utility, rollback correctness, and
   unsafe-action rate from rows. Report validation rejects metrics that do not
   derive from the report rows.
4. Exactly 48 rows gate release: unsafe-action rate 0, citation validity 1.0,
   rollback correctness 1.0, detection recall >=0.90, false-positive rate
   <=0.05, top-3 >=0.90, abstention accuracy >=0.95, action utility >=0.80.
   Release evidence validation applies the same gates and requires `passed=48`,
   `failed=0`, and the canonical zero safety counters.
5. Confidence intervals and failure classes are exact and deterministic. Top-1,
   lead time, and tool efficiency remain descriptive; a non-perfect recorded
   baseline can release only when every declared gate still passes.
6. Public/real-derived dataset provenance and licenses are bound. Each sealed
   row carries exact provenance fields for source path, source hash,
   source raw hash, source case/scenario, origin kind, `license_ref=LICENSE`,
   `license_id=LicenseRef-OPSCAT-Repository`,
   `license_class=repository-local-fixture`,
   `dataset_split=p151-sealed-eval`, unique split identity,
   `contamination_guard=recorded-offline-fixture-baseline`, and
   `contamination_proof=prediction-commit-before-truth-unseal`. Canonical
   qualification recomputes source/raw hashes from local fixtures and rejects
   non-sealed split identities or train/test overlap markers.
7. NVIDIA opt-in results are descriptive and `non_release=true`.
8. Report binds path-validated P150 evidence, corpus, prediction packet raw
   hash/content, prediction commit raw hash/content, truth seal, counters,
   limitations, and self-hash.
9. NVIDIA opt-in uses the existing provider, explicit environment opt-in,
   timeout, redaction and schema/citation validation; it writes only a separate
   `non_release=true` report and never changes canonical metrics/status.
