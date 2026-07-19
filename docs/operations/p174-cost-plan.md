# P174 GCP Cost Plan

## Credit Snapshot

- Billing account: local-only P174 billing account
- Free Trial balance observed on 2026-07-17: `KRW 263,495.44`
- Remaining percentage: `60%`
- Console expiration: `2026-08-01`
- P174 project budget alert: `KRW 250,000`

The budget is an alert threshold, not a hard spending cap. The lab keeps a
separate project and frozen destroy guard so the project can be stopped without
affecting existing workloads.

## Official Catalog Snapshot

The Cloud Billing Catalog API was queried in KRW for Compute Engine SKUs serving
`asia-northeast3` on 2026-07-17.

| SKU | Unit price |
| --- | ---: |
| E2 instance core running in Seoul | KRW 43.012847439 / core-hour |
| E2 instance RAM running in Seoul | KRW 5.738505595 / GiB-hour |
| Balanced PD capacity in Seoul | KRW 199.514250022 / GiB-month |
| Static IP charge in Seoul while in use | KRW 0 / hour |

Official references:

- `https://cloudbilling.googleapis.com/v1/services/6F81-5844-456A/skus`
- `https://cloud.google.com/compute/vm-instance-pricing`
- `https://cloud.google.com/billing/docs/how-to/budgets`

## Default 15-Day Profile

| Resource | Calculation | Estimated cost |
| --- | --- | ---: |
| Target `e2-standard-8` | 8 cores + 32 GiB, 360 hours | KRW 189,984.59 |
| Observer `e2-standard-2` | 2 cores + 8 GiB, 360 hours | KRW 47,496.15 |
| Balanced PD, 80 GiB | 80 GiB for half month | KRW 7,980.57 |
| **Base total** | compute + disk | **KRW 245,461.31** |

The remaining margin is approximately KRW 18,034 before small Artifact
Registry, logging, monitoring, snapshot, or network charges. Images, log volume,
retention, snapshots, and egress are therefore bounded and measured daily.

## Operating Rule

1. Start with the default profile only after a reviewed Terraform plan.
2. Capture a billing/cost snapshot after the first 6 and 24 hours.
3. Reduce the target machine or stop load generation if forecast cost exceeds
   the KRW 250,000 project budget before the final evidence export.
4. Do not deliberately generate useless traffic merely to consume credit;
   spending must correspond to healthy denominators, fault episodes, soak, or
   independent evaluation evidence.
