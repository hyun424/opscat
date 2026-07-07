---
id: P12-001
title: Dataset Source Manifest
status: DONE
phase: P12
depends_on: []
---

# P12-001 — Dataset Source Manifest

## Outcome

Implement the P12 slice for Dataset Source Manifest.

## Acceptance Criteria

- [x] manifest records name, family, homepage/citation, license note, local path, supported files, labels, import mode
- [x] manifest states normal verification does not download external data
- [x] manifest supports LogHub, NAB, and AIOps families

## Boundary

No auth/session work, no external dataset download during normal verification, no production mutation, no Kubernetes/cloud/database execution, no unrestricted shell, no customer credentials, and no unattended production-operation claim.
