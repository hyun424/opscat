# P133-005 Runtime and Supervisor Contracts

Status: complete; independently reviewed and release-qualified.

Add closed `deadman-run`, `deadman-check`, `outbox-list`, and `outbox-ack` CLI
commands plus systemd, launchd, and Compose sidecar examples. The systemd and
Compose contracts qualify fixed argv, immutable image digest, non-root use,
read-only monitor state, writable outbox only, restart throttling, graceful
stop, and absence of shells, secrets, network/provider fields, and action
commands. The launchd plist is structurally validated but remains an explicit
example because plist configuration alone cannot enforce equivalent filesystem
and network isolation.
`--no-sleep` is evaluator-only, requires bounded `--max-cycles`, and is forbidden
in all supervisor manifests.
