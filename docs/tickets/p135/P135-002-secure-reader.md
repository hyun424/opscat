# P135-002 - Secure bounded local reader

## Deliverable

Implement root-relative, no-follow, regular-file-only, chunk-bounded local
artifact reads with pre/post identity and content-hash verification.

## Acceptance

- Traversal, symlink, hard-link, non-regular, mutation, and oversize fail closed.
- Strict UTF-8 and structural JSON/JSONL budgets.
- No path or payload leakage into promoted evidence.
- Duplicate validation securely rereads current bytes and discloses that read.
