# P106-004 - Shared Safety Gate

## Goal

Use one typed `PreventiveSafetyGateResult` for P106 planning and P107 gate
evidence, while preserving Night Autopilot compatibility.

## Contract

The result records confidence, policy, blast radius, reversibility, simulation,
incident memory, environment, ambiguity, reasons, route, and the immutable
simulation-only boundary fields.

## Acceptance

Production, critical severity, low confidence, conflicting evidence, ambiguity,
unknown/prohibited action, failed registry parity, non-local/service blast
radius, unavailable rollback, failed simulation, and prior failed remediation
all return observe/escalate with `passed=false`.
