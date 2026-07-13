# P133-002 Transitions and Deduplication

Status: complete; independently reviewed and release-qualified.

Implement healthy, opened, updated, reminder, and recovered transitions with a
single active incident, monotonic sequence, deterministic IDs, previous-event
links, exact reminder boundaries, and fail-closed clock behavior. Repeated
unchanged checks before the reminder boundary must emit no event.
