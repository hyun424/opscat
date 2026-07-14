# P140 Plan Review

## Result

Approved after revision. Independent architect and critic passes found no
remaining P0/P1/P2 planning issues.

## Closed findings

- Missing P139 state is detected from `stopped_unclean/no_terminal_receipt`
  only when readiness, heartbeat, and receipt hashes are all absent.
- Invalid observations use a deterministic redacted category fingerprint so
  distinct failures do not collapse through a null state hash.
- Healthy/valid state identity uses a stable P140 projection that excludes
  P139's volatile `observed_at` and `status_hash` fields.
- Release evidence preserves both the exact P133/P121 authority tuple and the
  exact P139/P138 15-key forbidden-authority tuple.
- P140 config self-hashing excludes only `config_hash` from canonical input.
- Source and dependency bindings enumerate concrete paths and qualified P133/
  P139 release hashes.

## Design decision

P133 remains the sole event/cursor/ack/retention writer. P140 adds a whole-run
adapter lease in front of P133 so two long-running adapter processes cannot
alternate serialized checks; the lease order is P140 -> P133 -> read-only P139
lease probe. P140 never acquires the P138/P139 writer lease or starts P139.

## Residual boundary

P139's current lease probe opens the lease file through its existing local
status implementation. Deployment must use the same unprivileged local service
identity and grant access to that lease path. This does not grant network,
notification, command, or remediation authority.

## Implementation-review remediation

The first independent implementation and test-adequacy passes requested
changes rather than approving release. Before freezing P140, the implementation
was amended to:

- require every P133 allowed root and write path to remain inside P140's
  declared artifact roots;
- replace stat-then-reopen reads with descriptor-relative `O_NOFOLLOW` opens
  and `fstat` validation;
- bind `pyproject.toml` and directly imported P110/P121/P133/P139 modules into
  release evidence;
- make the P139 lease-file precondition machine-readable in Compose and
  explicit in deployment documentation;
- replace reused selectors with distinct tamper, stale, unclean-stop,
  restart-generation, no-mutation, and real-subprocess signal tests;
- add tracked final-artifact validation and strict profile/matrix/reviewer
  integrity checks; and
- fix and requalify P139 after the P140 integration test proved future-dated
  controls could otherwise satisfy `ready`.

P140 remains blocked until the remediated source, exact 32-case matrix, freeze
manifest, and final review are all mutually bound and reproduce.
