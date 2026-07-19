# P174 IAP Workload Deployment Runbook

This path deploys only the workload bundle to already-provisioned P174 VMs. It
does not create, apply, destroy, or mutate Terraform infrastructure.

## Fixed Scope

- Project: must match `EXPECTED_PROJECT_ID` and `^opscat-p174-[a-z0-9-]{6,20}$`.
- Zone: `asia-northeast3-a`.
- Target VM: `p174-target`, private bind IP `10.174.0.10`.
- Observer VM: `p174-observer`, private IP `10.174.0.20`.
- Transport: `gcloud compute ssh/scp --tunnel-through-iap`.
- Forbidden projects remain blocked by script allowlist checks.

## Plan

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
  infra/gcp/p174/workload-iap.sh plan
```

Review the printed `workload-plan.env` and its `.sha256`. The plan pins:

- lab bundle tarball path and SHA-256;
- per-file bundle manifest hash;
- observer host collector hash;
- exact project, zone, VM names, and private IPs.

## Apply

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-YYYYMMDDTHHMMSSZ/workload-plan.env \
EXPECTED_PLAN_SHA256=<reviewed plan sha256> \
APPLY_REVIEWED_WORKLOAD=1 \
  infra/gcp/p174/workload-iap.sh apply
```

Apply copies the pinned bundle over IAP, generates a fresh local-only action
capability, writes remote `.env` files with mode `0600`, runs `docker compose up
-d --build`, verifies health, installs the observer host evidence timer, blocks
Docker containers from the GCE metadata IP, and retrieves evidence archives.

No service-account key is created or used. The host-side observer collector uses
the attached observer service account metadata token only in memory. It calls the
exact Compute Engine GET for the frozen target instance and appends only bounded
evidence under `/var/lib/opscat-p174/evidence/compute-target-evidence.jsonl`.
It does not persist raw tokens or raw response bodies.

## Evidence

Apply retrieves evidence automatically. To retrieve again:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-YYYYMMDDTHHMMSSZ/workload-plan.env \
EXPECTED_PLAN_SHA256=<reviewed plan sha256> \
EVIDENCE_DIR=/tmp/p174-evidence \
  infra/gcp/p174/workload-iap.sh evidence
```

Evidence includes target health/log snapshots, observer collect receipts, and
`host-compute-evidence.tgz` from `/var/lib/opscat-p174/evidence`.

The evidence command is fail-closed: API operational metrics, a real Prometheus
query, and a real Loki log-stream query must all be healthy. It also extracts
the nested host-compute archive and proves every record is an HTTP 200 read of
the reviewed running target VM in the reviewed zone. Deployment and action
input collection explicitly allow unhealthy operational evidence because those
paths must capture startup and incident states; the standalone evidence command
does not.

## Typed Action

Every action first collects fresh target and observer archives, hashes both,
and binds that hash into the request and immutable provider receipt. Run a
dry-run before the reviewed live action:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-YYYYMMDDTHHMMSSZ/workload-plan.env \
EXPECTED_PLAN_SHA256=<reviewed plan sha256> \
P174_ACTION=tune_pool \
P174_POOL_SIZE=64 \
P174_REQUEST_ID=<unique request id> \
  infra/gcp/p174/workload-iap.sh action-dry-run

EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-YYYYMMDDTHHMMSSZ/workload-plan.env \
EXPECTED_PLAN_SHA256=<reviewed plan sha256> \
P174_ACTION=tune_pool \
P174_POOL_SIZE=64 \
P174_REQUEST_ID=<different unique request id> \
APPLY_REVIEWED_ACTION=1 \
  infra/gcp/p174/workload-iap.sh action
```

The HTTP provider takes three post-action samples. A live action is applied only
when the action-specific recovery is durable; a no-op, increasing queue, or
failed post-check produces a failure or rollback receipt instead of a success
claim.

`restart_worker` is an irreversible action in this lab. It must not be counted
as a rollback-closure claim. It may finish as `applied` only when three
independent post-action samples prove the worker pause is released, the service
is healthy, the queue is bounded and draining, and the restart generation has
stopped changing. If any of those checks is missing, harmful, or uncertain, the
provider receipt must fail closed and must not claim rollback closure.
`tune_pool` and `rollback_canary` keep their independent rollback-closure
requirements.

## P175 Live Harness

The deterministic P175 harness has its own review gate after workload apply.
It does not accept operator-provided endpoints or targets. The runner creates
two IAP SSH tunnels to fixed reviewed remote endpoints: target
`10.174.0.10:8020` and observer host loopback `127.0.0.1:8030`. Local tunnel ports are
ephemeral and are passed to `scripts/run_p174_live_harness.py` as loopback-only
URLs.

First freeze the reviewed harness manifest and live execution plan:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-YYYYMMDDTHHMMSSZ/workload-plan.env \
EXPECTED_PLAN_SHA256=<reviewed workload plan sha256> \
P175_REVIEWED_HARNESS=1 \
P175_REVIEWER_ID=<reviewer id> \
  infra/gcp/p174/workload-iap.sh p175-plan
```

Review the printed `p175-live-plan.env`, `.sha256`, harness manifest path, and
harness manifest SHA-256. The P175 plan pins the workload deployment plan hash,
the reviewed harness manifest hash, the local ignored provider manifest hash,
the project/target/run binding, the fixed remote loopback ports, and hashes of
the separated action and fault capabilities.

Then run the live harness:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
P175_PLAN_FILE=/tmp/opscat-p174-workload-XXXXXXXX/p175-live-plan.env \
EXPECTED_P175_PLAN_SHA256=<reviewed P175 plan sha256> \
EXPECTED_HARNESS_MANIFEST_SHA256=<reviewed harness manifest sha256> \
  infra/gcp/p174/workload-iap.sh p175-live
```

`p175-live` revalidates the P175 plan digest, the pinned workload plan digest,
the harness manifest SHA-256, the provider manifest SHA-256, and local runtime
authority bindings before opening tunnels. The action and fault capabilities
must be present and distinct. Their raw values remain in the ignored mode-0600
runtime authority file; the CLI receives only that file path and reparses it
with a strict allowlist instead of exposing capabilities in process arguments. The harness writes
`p175-live-summary.json` and `p175-live-evidence.jsonl` atomically under the
pinned eval directory. A blocked, partial, or non-qualified run exits nonzero
after preserving any generated summary and JSONL.

## Teardown

Teardown is also plan/apply separated:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
  infra/gcp/p174/workload-iap.sh teardown-plan
```

Then review and apply:

```bash
EXPECTED_PROJECT_ID=opscat-p174-example123 \
PLAN_FILE=/tmp/opscat-p174-workload-teardown-YYYYMMDDTHHMMSSZ/workload-teardown-plan.env \
EXPECTED_PLAN_SHA256=<reviewed teardown plan sha256> \
APPLY_REVIEWED_WORKLOAD_TEARDOWN=1 \
  infra/gcp/p174/workload-iap.sh teardown-apply
```

This runs `docker compose down --remove-orphans` on observer then target. It does
not run Terraform destroy and does not touch non-P174 projects. Set
`P174_TEARDOWN_VOLUMES=1` only for a reviewed clean-state replay. Successful
teardown also removes the installed host collector, systemd units, remote
release files, and local ignored runtime authority files.
