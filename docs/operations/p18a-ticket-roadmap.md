# OpsCat P18A Ticket Roadmap — Realtime Source Reader

## Scope

P18A adds the realtime ingestion foundation needed before broader model-judgment quality evaluation. The production-shaped path must read original log/metric sources incrementally, keep lightweight rolling windows, and create JSON incident/evidence snapshots only when a trigger fires.

## Boundary

- No auth work: no OIDC, SSO, login, password auth, session UI, CSRF/session hardening, or production tenant provisioning.
- No production mutation: no Kubernetes/cloud/database mutation, no unrestricted shell, no real restart/rollback/scale/delete, and no customer credentials.
- Normal verification remains local/mock and does not call external model APIs.
- Realtime readers are local file/fixture readers only in P18A.
- P18A does not claim unattended production operation.

## Tickets

### P18A-001 — FileTailReader with cursor

Read appended log bytes from a source file using a persisted cursor with path, inode, offset, and timestamp.

Acceptance:
- First read can start at beginning for replay or at end for live mode.
- Subsequent reads return only newly appended lines.
- Truncation/rotation resets safely without rereading unbounded data.

### P18A-002 — Lightweight log parsers

Parse plain text, JSON log, logfmt, and LogHub structured rows into normalized log events.

Acceptance:
- Each event has timestamp, severity, service/source, message, raw line, and metadata.
- Parser preserves original raw text for audit.
- Parser redacts obvious secrets.

### P18A-003 — Metric window parser

Parse CSV metric rows and Prometheus-style timestamp/value points into normalized metric events.

Acceptance:
- Metric events carry timestamp, name, value, source, labels, and raw row.
- CSV headers used by NAB are supported.
- Invalid numeric rows are skipped with a reason.

### P18A-004 — Rolling incident window

Maintain bounded recent log and metric windows without converting the full source into JSON.

Acceptance:
- Window enforces max event count.
- Window can summarize severity counts and metric baseline/current/ratio.
- Window can produce evidence candidates on demand.

### P18A-005 — Trigger detector

Detect conditions that justify building an evidence snapshot and optionally calling an LLM later.

Acceptance:
- Detect error spikes, no-data metric windows, metric spikes, and prompt-injection/unsafe-action log evidence.
- Do not trigger on every line.
- Trigger output includes reason, severity, and cited event IDs.

### P18A-006 — Evidence snapshot builder

Convert a triggered rolling window into a bounded OpsCat `JudgmentCase` JSON snapshot.

Acceptance:
- Snapshot has incident, evidence, rubric, required evidence IDs, and safety boundaries.
- Snapshot is local/mock and action-execution disabled.
- Snapshot can be fed into existing P13-P17 LLM judgment/evaluation code.

### P18A-007 — Replay real LogHub/NAB through realtime reader

Replay the downloaded LogHub/NAB local cache through the realtime reader and write reproducible local artifacts.

Acceptance:
- Uses `/private/tmp/opscat-real-datasets` if present.
- Repo verification uses tiny fixtures only; no external downloads.
- Report documents source paths, counts, triggers, and generated snapshot counts.

### P18A-008 — Release evidence

Document P18A artifacts and update roadmap/release evidence.

Acceptance:
- Final summary maps all P18A tickets to code/tests/docs.
- `scripts/verify.sh` includes bounded local/mock realtime replay smoke.
- Full verification passes.
