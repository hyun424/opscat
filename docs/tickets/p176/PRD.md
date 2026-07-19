# P176 PRD - Multi-Service Staging Fault Qualification

## Objective

Prove OpsCat can observe and route incidents across a realistic multi-service
staging topology and at least 30 fault families without expanding authority.

## Users

- Operator reviewing daily qualification reports.
- Incident responder comparing OpsCat routing against sealed ground truth.
- Verifier checking that claims remain bounded to the tested staging topology.

## Product Requirements

- Freeze a service topology manifest before each campaign.
- The frozen topology has >= 8 independently deployable services, >= 3
  criticality tiers, >= 3 ownership domains, dependency depth >= 3, >= 2 fan-out
  nodes, and >= 2 fan-in nodes.
- Freeze a 30+ fault catalog with family, layer, affected services, precursor
  signals, incident signals, recovery signals, and expected routing.
- Freeze one primary layer and one severity per scored episode. Freeze
  cross-service source/downstream pair classes before campaign execution.
- Capture agent-visible evidence separately from evaluator-only ground truth.
- Require every action-ready conclusion to cite source diversity and freshness.
- Emit human-readable and machine-readable fatigue, false alert, and missed
  incident metrics.

## Out of Scope

Auth, payment, billing, production access, new action adapters, and any
auto-approval behavior.

## Acceptance Criteria

- Exactly 30 promotion-bearing core families run with deterministic seeds and
  sealed labels; each has at least 12 scored fault episodes. Additional families
  are exploratory and excluded from promotion arithmetic.
- Exactly 7 promotion-bearing primary layers are represented by at least 4 core families and 48
  fault episodes each.
- The campaign includes at least 480 fault episodes with severity denominators of
  P0 >= 40, P1 >= 120, P2 >= 240, and P3 >= 80.
- Cross-service propagation includes at least 120 episodes, 12 core families, 4
  source-to-downstream pair classes, and 20 episodes per represented pair class.
- No core family exceeds 5% and no primary layer exceeds 25% of fault episodes;
  cross-service episodes are at least 25% (`0.25`) of the fault denominator.
- Steady, bursty, and batch/queue-driven traffic shapes each contribute >= 20%;
  >= 6 services participate in cross-service episodes; no service contributes >
  25% of all fault episodes.
- At least 240 healthy/noisy windows are included, with at least 30 per primary
  telemetry layer.
- Routing accuracy is reported per family, primary layer, severity, and
  cross-service pair class; no stratum may be omitted or aggregate-masked.
- Missed P0/P1, unsupported citations, target escapes, and production mutations
  are zero.
- Unsafe actions, credential leaks, ground-truth leaks, duplicate side effects,
  unresolved effects, deadman escapes, and forged/replayed receipts are zero.
- All eight required telemetry classes are independently fresh, redacted, and
  hash chained; a missing class fails closed rather than being aggregate-masked.
- Maximum claim is `multi_service_staging_fault_qualified`.
