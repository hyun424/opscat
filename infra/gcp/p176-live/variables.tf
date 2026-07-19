variable "billing_account_id" {
  description = "Reviewed billing account for the externally provisioned P176 live lab project."
  type        = string

  validation {
    condition     = can(regex("^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$", var.billing_account_id))
    error_message = "billing_account_id must be supplied from local terraform.tfvars as a GCP billing account ID."
  }
}

variable "project_id" {
  description = "Externally provisioned disposable P176 live lab project ID created by ../p176-cost-cutoff."
  type        = string

  validation {
    condition     = can(regex("^opscat-p176-live-[a-z0-9-]{6,20}$", var.project_id))
    error_message = "project_id must be a new opscat-p176-live-* project and must not be a forbidden existing project."
  }
}

variable "region" {
  description = "Region for P176 live lab resources."
  type        = string
  default     = "asia-northeast3"

  validation {
    condition     = var.region == "asia-northeast3"
    error_message = "P176 live lab resources must stay in asia-northeast3."
  }
}

variable "zone" {
  description = "Zone for target and observer VMs."
  type        = string
  default     = "asia-northeast3-a"

  validation {
    condition     = var.zone == "asia-northeast3-a"
    error_message = "P176 live target and observer VMs must stay in asia-northeast3-a."
  }
}

variable "cost_cutoff_budget_topic_name" {
  description = "Reviewed external admin project Pub/Sub topic name created by ../p176-cost-cutoff."
  type        = string

  validation {
    condition     = can(regex("^projects/opscat-p176-admin-[a-z0-9-]{6,20}/topics/p176-cost-cutoff-budget$", var.cost_cutoff_budget_topic_name))
    error_message = "cost_cutoff_budget_topic_name must be the external admin project topic projects/opscat-p176-admin-*/topics/p176-cost-cutoff-budget."
  }
}

variable "ssh_admin_members" {
  description = "IAM members allowed to administer VMs through IAP SSH and OS Login."
  type        = set(string)
  default     = []
}

variable "target_machine_type" {
  description = "Bounded machine type for the disposable target VM."
  type        = string
  default     = "e2-standard-8"

  validation {
    condition     = var.target_machine_type == "e2-standard-8"
    error_message = "P176 live target VM machine type must be exactly e2-standard-8."
  }
}

variable "observer_machine_type" {
  description = "Bounded machine type for the disposable observer VM."
  type        = string
  default     = "e2-standard-2"

  validation {
    condition     = var.observer_machine_type == "e2-standard-2"
    error_message = "P176 live observer VM machine type must be exactly e2-standard-2."
  }
}

variable "boot_disk_size_gb" {
  description = "Bounded boot disk size for each disposable VM."
  type        = number
  default     = 40

  validation {
    condition     = var.boot_disk_size_gb <= 40
    error_message = "P176 live boot disks must not exceed 40 GB."
  }
}

variable "opscat_principal" {
  description = "Optional OpsCat principal recorded for evidence only. This module never grants it IAM."
  type        = string
  default     = ""
}
