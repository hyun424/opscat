# P176 P174 Workload Adoption Control Root

This root is plan-only until a reviewed operator explicitly applies a saved
plan. It creates a fresh `opscat-p176-admin-*` control project and tightly scoped
P176 harness/control resources.

It must not own, delete, or mutate the existing `opscat-p174-*` workload
project, VM, network, or disks. P174 workload identifiers are baseline bindings
used for evidence only.

Required evidence bindings:

- reviewed adoption apply plan hash
- reviewed adoption destroy plan hash
- reviewed P174 workload plan artifact hash
- baseline inventory hash for the existing P174 workload

Fail closed for missing baseline evidence, shared/prod identifiers, or any plan
that grants IAM against the workload project.
