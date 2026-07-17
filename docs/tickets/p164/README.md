# P164 Tickets

Dependency: canonical P163 release evidence. Owner surface:
`app/services/p164_p168_disposable_operator_program.py`, the P164 input under
`evals/p164`, and the shared runner/verifier/test files.

1. **P164-001 — Fault catalog.** Implement six named families with three stages
   across gateway, checkout, database, and worker. Test every family/stage and
   reject unknown values.
2. **P164-002 — Telemetry transport.** Implement the six documented endpoints,
   numeric-loopback server/client, and deterministic response schemas. Positive
   test all 108 canonical reads; negative-test wrong path and destination.
3. **P164-003 — Boundary gates.** Redact token/password/authorization values;
   reject localhost, IPv6, alternate loopback, public IP, redirect, and
   non-HTTP input.
4. **P164-004 — Evidence.** Emit report/freeze/review/release artifacts bound to
   P163 and all P164 sources. Done when family/stage/source/redaction coverage is
   1.0, 108 loopback reads are recorded, and every external-authority counter is
   zero.
