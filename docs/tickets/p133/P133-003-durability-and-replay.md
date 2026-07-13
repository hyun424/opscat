# P133-003 Durability and Replay

Status: complete; independently reviewed and release-qualified.

Write immutable events before cursor advancement. Prove idempotent retry after
a crash between those writes, reject conflicting existing events, preserve prior
canonicals on pre-replace faults, and require reload/rewrite recovery after a
post-replace directory-sync uncertainty.
Event IDs exclude wall-clock time. Retry validates and reuses the first event's
`occurred_at` before advancing the cursor with the retry check time.
