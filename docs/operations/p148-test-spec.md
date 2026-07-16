# P148 Reversible Lab Action Test Specification

Schema/status: `p148.report.v1`, `p148.freeze_manifest.v1`,
`p148.final_review.v1`, `p148.release_evidence.v1`, and
`p148_reversible_lab_action_qualified`. Artifacts and command are the exact P148
entries in the program plan.

1. Judgment schema, citations, evidence hashes, and safety route are validated before planning an action.
2. Judgment is deterministic; NVIDIA and every external model are outside P148
   execution and `nvidia_call_count` is exactly zero.
3. Unknown, shell, credential, external-message, staging, and production capabilities fail before execution.
4. Allowed actions target only a live process-owned disposable lab capability.
5. Pre-state hash mismatch, duplicate idempotency key, expired capability, kill switch, or missing rollback handler blocks.
6. Successful action records intent, commit, postcondition, bounded effect, and rollback snapshot.
7. Failed postcondition or injected crash restores the snapshot or ends blocked with unresolved-effect count nonzero.
8. Canonical report has zero external-provider and staging/production mutation counters.
9. Report and release metrics expose the committed real action receipt set,
   including case, target, idempotency key, rollback handler, and self-hash.
10. Fixtures cover success, duplicate, pre-state mismatch, expiry, kill switch,
    unknown capability, staging target, failed postcondition, injected crash,
    and rollback; unresolved effects must be zero for release.
