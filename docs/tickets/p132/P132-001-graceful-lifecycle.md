# P132-001 Graceful Lifecycle

Status: complete.

Add stop-aware waiting and SIGTERM/SIGINT handling. Persist a hash-verified
termination receipt, release the lease, and make status immediately fail
liveness with `runtime_stopped`. Preserve existing bounded-run behavior and
exact-zero runtime authority.
