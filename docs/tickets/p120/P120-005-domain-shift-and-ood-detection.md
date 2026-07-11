# P120-005: domain shift and OOD detection

## Goal

Detect source, modality, topology, temporal, incident-family, action-family,
ontology, calibration, contradiction, and authority novelty before making
cross-system quality claims.

## Contract

- Report telemetry modality missingness shift, signal distribution shift,
  topology size/shape/dependency-pattern shift, incident-family novelty,
  action-family novelty, ontology-mapping ambiguity, source-origin shift,
  temporal drift, calibration drift, contradiction-rate shift, and
  authority-boundary novelty.
- Define OOD reports with system ID, dataset ID, shift dimensions, OOD score,
  threshold, decision effect, recommended label, calibration effect, affected
  denominators, and evidence refs.
- Allow OOD effects only as `continue_with_penalty`, `investigate_more`,
  `abstain`, `escalate`, or `aborted_fail_closed`.
- Keep OOD detection separate from action execution authority.

## Acceptance

Shift reports include score, threshold, affected denominators, evidence refs,
decision effect, and calibration effect. OOD effectiveness is reported where
labels support it. High shift, authority novelty, missing modality, topology
novelty, or calibration drift cannot silently proceed to confident action.

## Stop Rules

Stop if high-OOD or low-calibration cases can trigger action execution, if OOD
thresholds are tuned on holdout systems, if authority novelty is ignored, or if
shift failures are hidden by aggregate metrics.
