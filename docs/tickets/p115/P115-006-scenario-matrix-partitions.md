# P115-006: scenario matrix and partition manifest

Create the P115 scenario matrix with at least 15 families and at least 300
cases: CPU, memory, disk, network delay, network loss, socket, deploy,
dependency, database pool, queue, DNS, certificate, quota, cache, and traffic
faults. Each family must include action, no-action, investigate-more,
contraindicated-action, and plausible-but-harmful or ineffective cases.

Define `p115.partition_manifest.v1` with grouped development and holdout splits
by source, service, topology, incident family, time, and action-pack family.
Row-level splits, exact duplicates, near duplicates, and shared topology/time
leakage fail closed.
