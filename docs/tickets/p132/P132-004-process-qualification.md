# P132-004 Process Qualification

Status: complete.

Build a closed temporary-directory harness that may launch only
`python -m app.monitor_cli`. Prove graceful stop, forced crash/restart,
split-brain lease rejection, checkpoint recovery, process-independent watchdog
behavior, bounded restart backoff, and stable-window reset. Disclose every
evaluator process launch and signal separately from runtime authority.
