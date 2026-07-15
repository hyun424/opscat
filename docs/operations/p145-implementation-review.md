# P145 Implementation Notes / Pending Independent Review

Status: pending independent implementation review.

This document records implementation scope only. It is not a final approval and
must not be treated as `final-implementation-review.json`.

- Local response duty officer, selector runner, preliminary evidence assembly,
  CLI, fixtures, and tests were added for P145.
- Final qualification remains gated on an independent review artifact with the
  closed schema required by `docs/operations/p145-test-spec.md`.
- No credentials, network, provider SDK, shell action, ticketing, staging,
  production, real remediation, or operator-replacement authority is introduced.

The first independent implementation review rejected the preliminary
implementation. The pending-review revision addresses those findings by:

- removing evaluator expectations and descriptive branch labels from runtime
  decisions, with independent mutation regressions;
- freezing and enforcing an exact non-empty phase path for every selector;
- replaying controlled crash windows through fresh controller instances over
  durable journal, cursor, lease, acknowledgement, and fault-lab artifacts;
- validating exact predecessor and source/profile bindings before ownership;
- exercising actual journal, terminal, cursor, escalation-receipt, lease, and
  acknowledgement conflicts fail-closed;
- separating evaluator subprocess accounting from the authority-bound runtime
  and adding static/runtime reachability guards; and
- validating transcript/result semantics so hollow or replayed rows cannot be
  accepted by rehashing.

These are implementation notes only. A new independent review is still
required, and final mode has not been run.

The second independent implementation review identified two remaining
preliminary-evidence defects. This pending-review revision additionally:

- models `P145-CASE-45` as two distinct hash-bound P133 events and incidents
  sharing one correlation identifier, two local ownership acknowledgements,
  and one durable correlation receipt that reuses the sole committed action
  receipt without a second fault-lab mutation; and
- validates persisted selector command arguments by stable pytest command
  structure instead of the validator process's current Python executable,
  while retaining exact case, selector, transcript, and hash checks.

This section is implementation history, not independent approval. Preliminary
artifacts must be regenerated, and final mode remains prohibited pending a new
independent review.

The third independent implementation review identified two further replay and
provenance gaps. This pending-review revision additionally:

- reconciles every active P133 acknowledgement artifact to its exact journal
  payload, event, incident, self-hash, authority projection, and correlated
  action receipt before terminal reuse; missing, corrupt, drifted, or extra
  projections are quarantined and terminate in local human escalation; and
- derives acknowledgement counters and result hashes from reconciled durable
  artifacts, not acknowledgement phase counts alone; and
- records an alias-neutral executable provenance receipt binding selector argv
  to the canonical project `.venv/bin`, its `pyvenv.cfg` identity, and only the
  existing `python` and `python3` aliases.

These remain implementation notes only. No final review artifact has been
created or approved, and final mode remains prohibited.
