# P176 Adoption Amendment

P176 supports a second mode, `p174-workload-adoption`, alongside the existing
fresh-lab mode. Adoption uses one fresh `opscat-p176-admin-*` control project and
an existing non-prod `opscat-p174-*` workload.

The adoption plan never owns or deletes the P174 project, VM, network, or disks.
Only P176 control resources and harness IAM in the fresh control project are in
scope. Evidence must bind the reviewed adoption plan, reviewed adoption destroy
plan, reviewed P174 workload plan artifact, and baseline workload inventory.

Qualification fails closed when the baseline binding is missing, the workload
looks shared/prod, or workload mutation/delete authority is present.
