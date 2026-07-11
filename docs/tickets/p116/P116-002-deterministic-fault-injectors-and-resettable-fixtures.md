# P116-002: deterministic fault injectors and resettable fixtures

## Goal

Create the fixture and fault-injection plan for reproducible local service
failures across the P115 scenario families.

## Contract

- Provide disposable Docker or local Kubernetes-compatible fixture manifests
  with no production adapters, credentials, or external mutable resources.
- Support deterministic seeds for CPU, memory, disk, latency, loss, socket,
  deploy, dependency, database pool, queue, DNS, certificate, quota, cache, and
  traffic-skew faults.
- Emit fault injection receipts with pre-fault healthy evidence,
  post-injection unhealthy evidence, fixture hash, seed, and raw observation
  hashes.
- Define a reset plan that restores canonical initial state and inventories
  containers, processes, sockets, ports, volumes, queues, leases, locks, and
  persisted app data.
- Mark any family without perfect reset evidence as non-release-counting.

## Acceptance

The fixture suite proves byte-stable reset for identical fixture version and
seed, rejects fault receipts that survive reset or leak labels, and reports
family-level denominators for supported and unsupported faults.
