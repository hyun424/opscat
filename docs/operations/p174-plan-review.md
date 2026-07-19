# P174 Plan Review — GCP Disposable Provider-Adapter Lab

## Decision

**Conditionally approved for implementation.** The existing P174 goal remains a
disposable provider-shaped write sandbox. GCP is the isolation substrate, not a
reason to weaken the P169-P173 evidence, authority, or claim boundaries.

## Accepted Design

- A new project under a locally supplied organization and billing account.
- Two Compute Engine VMs in `asia-northeast3-a`: one target and one observer.
- Self-hosted Prometheus and Loki plus Compute Engine API reads.
- Attached service accounts only; no service-account keys.
- Separate target and observer VM identities. Containers cannot reach the GCP
  metadata endpoint; action, fault, and evaluator separation is enforced by
  exact application capabilities and immutable receipts rather than unused
  service-account objects.
- Only `tune_pool`, `restart_worker`, and `rollback_canary` may mutate the lab.
- `restart_worker` is explicitly irreversible: it is not eligible for a
  rollback-closure claim. Apply status requires three independent sampled
  checks proving worker pause release, service health, bounded/draining queue,
  and stable restart generation; missing or unclear proof must fail closed.
  `tune_pool` and `rollback_canary` retain independent rollback-closure checks.
- Real load and fault injection must generate the observed telemetry. Fixture
  replay cannot satisfy the live gate.

## Rejected Alternatives

1. **Reuse an existing non-P174 project.** Rejected because it contains unrelated
   workloads and cannot prove target isolation or safe teardown.
2. **Single local Docker process.** Rejected because it cannot exercise cloud
   identity, VM lifecycle, private-network enforcement, or GCP telemetry.
3. **Regional GKE cluster.** Rejected for this disposable lab because the extra
   availability and cost do not improve the intended evidence enough.
4. **GKE-first.** Rejected for P174 because the current Docker Compose runtime,
   short credit window, and process/DB/queue fault families can be proved faster
   and with a smaller authority surface on two VMs. GKE remains a later
   Kubernetes-generalization target.
5. **LLM-generated shell or kubectl.** Rejected because it bypasses typed
   adapters and cannot satisfy the authority or replay contract.
6. **Budget alert as hard stop.** Rejected because GCP budgets notify but do not
   automatically cap spend.

## Required Changes Before Apply

- Terraform plan must show only a new project and resources in that project.
- Budget, owner, purpose, and expiry metadata must be present.
- IAM and endpoint tests must prove that observation cannot mutate, containers
  cannot inherit host credentials, and action capabilities cannot read secrets,
  execute arbitrary commands, widen scope, or touch another VM/project.
- Firewall rules must expose no public application or OpsCat endpoint and allow
  only IAP administration plus private target-observer traffic.
- The teardown command must verify the expected project ID before destruction.
- Canonical evidence must contain no access token, raw credential, service
  account material, full raw provider response, or unredacted customer-like payload.

## Review Status

Implementation may begin. Live writes remain restricted to the dedicated,
disposable P174 project and the frozen target VM/run identity.

## Live Validation Status — 2026-07-17

The disposable project and both VMs were created and validated in local-only
operator evidence. Current proven
facts are:

- Terraform refresh plan reports **No changes** against the live project.
- API operational metrics, a Prometheus query, and a Loki log-stream query are
  all healthy in `evals/p174/live/20260717T2222-throughput-recovery/`.
- The observer host collector returned HTTP 200 evidence for the exact running
  `p174-target` VM without persisting an access token or service-account key.
- A real overload was captured, `tune_pool=64` was dry-run and then applied,
  and the independent outcome score was `62.406538` from measured recovery.
- Final target metrics were error rate `0.0`, latency `25.312 ms`, queue depth
  `1`, pool size `64`, and service up `1`.
- Negative authority probes rejected mutation attempts from the observer and
  container metadata-token access.

This is **partial live qualification**, not production qualification. The
remaining release gates are live `restart_worker` and `rollback_canary`
scenarios, at least 200 healthy evaluator windows, the 100-episode adversarial
matrix, final teardown proof, and a complete release-bundle review.
