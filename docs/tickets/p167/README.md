# P167 Tickets

Dependency: canonical P166 release. Owner surface: policy/controller classes in
the shared service, P167 fixtures/tests, runner/verifier, and `evals/p167`.

1. **P167-001 — Policy.** Implement only the three documented cause/action
   mappings and the `0.90`, two-source, 30s telemetry, 60s heartbeat, target,
   deadman, and kill-switch gates. Test every denial reason.
2. **P167-002 — Approval/idempotency.** Bind the documented approval fields to a
   capability-derived signature. Reusing an identical request ID returns the
   receipt; changed content, forged signature, unknown action, or replay under a
   new target fails closed.
3. **P167-003 — Effect closure.** Capture pre-state hash, execute once, require a
   newer independent post-check, and either prove recovery or restore the exact
   pre-state hash. Test all fixed actions and a harmful mismatch.
4. **P167-004 — Evidence.** Done when every allowed action is covered, denial
   accuracy and rollback closure are 1.0, unsafe/duplicate/deadman escapes are
   zero, and staging/production authority remains zero.
