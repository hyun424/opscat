# OpsCat P18A Final Summary — Realtime Source Reader

P18A adds source-native incremental ingestion before model judgment quality evaluation. OpsCat can now read original log/metric files incrementally, parse lightweight events, maintain bounded rolling windows, detect triggers, and emit JSON `JudgmentCase` evidence snapshots only when judgment/replay/audit requires them.

Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; no Kubernetes/cloud/database mutation; no unrestricted shell; does not claim unattended production operation.

## Ticket closure

| Ticket | Result | Artifact |
| --- | --- | --- |
| P18A-001 | DONE | `FileTailReader` and `FileTailCursor` read appended bytes and handle truncation/rotation. |
| P18A-002 | DONE | `parse_log_line` handles plain text, JSON logs, logfmt, and LogHub-style structured fields. |
| P18A-003 | DONE | `parse_metric_csv_rows` parses timestamp/value CSV metrics and skips invalid numeric rows. |
| P18A-004 | DONE | `RollingIncidentWindow` keeps bounded logs/metrics and summarizes severity/metric windows. |
| P18A-005 | DONE | `detect_realtime_triggers` detects error spikes, metric spikes, no-data windows, and unsafe log instructions. |
| P18A-006 | DONE | `build_judgment_case_from_trigger` emits bounded `JudgmentCase` snapshots. |
| P18A-007 | DONE | `scripts/replay_realtime_sources.py` replays local LogHub/NAB-style sources into snapshots/reports. |
| P18A-008 | DONE | Release evidence, roadmap, and verify smoke document the source-native incremental boundary. |

## Implementation evidence

- `app/services/realtime_source_reader.py`
- `scripts/replay_realtime_sources.py`
- `tests/test_realtime_source_reader.py`
- `tests/test_p18a_release_evidence.py`
- `docs/operations/p18a-ticket-roadmap.md`
- `docs/tickets/p18a/README.md`
- `scripts/verify.sh`

## Local real-data cache evidence

P18A can use the local cache prepared under `/private/tmp/opscat-real-datasets` when present:

- LogHub Apache 2k raw/structured source files.
- NAB realKnownCause ambient temperature source file.
- Derived local judgment/replay artifacts for P18 model-quality work.

These files are not committed and are not required for normal verification.

## Verification

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_realtime_source_reader.py tests/test_p18a_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app tests scripts`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app tests scripts`
- `bash scripts/verify.sh --profile full`

## Safety position

P18A does not make OpsCat an unattended production operator. It only adds a local/mock source-native incremental ingestion and replay path so later P18 model-quality evaluation can operate on production-shaped streams without forcing all runtime inputs through prebuilt JSON files.
