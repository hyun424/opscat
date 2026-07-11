# P122-006: performance, soak, crash/replay, and agent observability

## Goal

Prove the local/sample deployment is observable, durable, and stable under
documented local load and soak conditions.

## Contract

- Performance report covers install time, cold-start time, demo startup and
  completion time, local event throughput, replay throughput, CPU, memory,
  storage, hardware/context, denominators, and expected envelope.
- Promoted soak reports local duration, workload, restart/crash conditions,
  incident/audit/timeline/replay/authority record counts, and zero lost
  records.
- Crash/replay coverage spans install, demo startup, incident ingest, evidence
  request, decision, approval, validation, rollback, replay write, eval write,
  release-evidence write, and report write.
- Observability exposes health, readiness, metrics, structured logs with
  correlation IDs, timeline spans or trace-like records, audit inspection,
  replay inspection, diagnostics, redaction, no secret logging, and
  fail-closed reasons.

## Acceptance

Performance evidence includes denominators and context. Promoted soak loses
zero incident, audit, timeline, replay, or authority records. Crash/replay
reproduces deterministic local evidence. Health, metrics, logs, timeline,
diagnostics, audit/replay inspection, redaction, authority rejections, and
fail-closed reasons are documented and tested.

## Stop Rules

Stop if records are lost, replay is not inspectable, authority rejection is not
observable, logs expose secrets, performance claims lack denominators,
hardware/context is omitted, restart loses data, report-write crash corrupts
evidence, observability requires production access, or soak results are used
to claim production autonomy.
