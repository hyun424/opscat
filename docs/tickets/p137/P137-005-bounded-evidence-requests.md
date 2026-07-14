# P137-005 - Closed bounded evidence request catalog

## Scope

Implement the closed 15-entry catalog of bounded `LOCAL_SELECTION` reads over
validated P137 atoms and already-promoted P136/P135 evidence bytes.

## Acceptance

- All 15 catalog entries from the roadmap are implemented in exact lexical
  order: `compare_current_window_to_promoted_baseline`,
  `fetch_record_by_evidence_id`, `join_records_by_entity_and_window`,
  `select_records_by_content_hash`, `select_records_by_entity_ref`,
  `select_records_by_label_hash`, `select_records_by_provider`,
  `select_records_by_risk_flag`, `select_records_by_signal_family`,
  `select_records_by_system_id`, `select_records_by_time_window`,
  `select_rejections_by_reason`, `summarize_log_preview_hashes`,
  `summarize_numeric_samples`, and `summarize_topology_refs`.
- OTLP is represented as metrics and no separate distributed-telemetry request
  exists.
- Requests accept only exact-key parameters containing hashes, integer bounds,
  timestamps, enums, and closed labels.
- Each executable request derives a one-shot `attempted_request_hash`; equivalent
  replay returns durable bytes and does not execute again.
- Non-catalog names, unknown parameters, paths, URLs, provider queries, shell
  text, natural-language instructions, credential keys, mutation verbs, and
  unbounded regex fail closed.
- Request input-record, output-record, output-byte, per-incident request, wall,
  CPU, and memory budgets are enforced.
- Equivalent replay returns durable request bytes; conflicting deterministic
  path bytes fail closed.
