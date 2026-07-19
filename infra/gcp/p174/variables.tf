variable "organization_id" {
  description = "GCP organization that owns the disposable P174 project."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{6,32}$", var.organization_id))
    error_message = "P174 organization_id must be supplied from local-only runtime configuration."
  }
}

variable "billing_account_id" {
  description = "Billing account attached to the disposable P174 project."
  type        = string

  validation {
    condition     = can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account_id))
    error_message = "P174 billing_account_id must be supplied from local-only runtime configuration."
  }
}

variable "project_id" {
  description = "Dedicated new GCP project ID for P174. Must not be an existing or forbidden project."
  type        = string

  validation {
    condition     = can(regex("^opscat-p174-[a-z0-9-]{6,20}$", var.project_id))
    error_message = "project_id must be a new opscat-p174-* project and must not be a forbidden existing project."
  }
}

variable "project_name" {
  description = "Human-readable name for the disposable P174 project."
  type        = string
  default     = "OpsCat P174 Disposable Lab"
}

variable "region" {
  description = "Region for P174 lab resources."
  type        = string
  default     = "asia-northeast3"

  validation {
    condition     = var.region == "asia-northeast3"
    error_message = "P174 lab resources must stay in asia-northeast3."
  }
}

variable "zone" {
  description = "Zone for target and observer VMs."
  type        = string
  default     = "asia-northeast3-a"

  validation {
    condition     = var.zone == "asia-northeast3-a"
    error_message = "P174 target and observer VMs must stay in asia-northeast3-a."
  }
}

variable "budget_amount_krw" {
  description = "Maximum alert budget for the disposable lab in KRW."
  type        = number
  default     = 250000

  validation {
    condition     = var.budget_amount_krw > 0 && var.budget_amount_krw <= 250000
    error_message = "P174 budget must be greater than 0 and must not exceed 250000 KRW."
  }
}

variable "budget_alert_email" {
  description = "Email address that receives P174 budget alerts."
  type        = string
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
    error_message = "P174 target VM machine type must be exactly e2-standard-8."
  }
}

variable "observer_machine_type" {
  description = "Bounded machine type for the disposable observer VM."
  type        = string
  default     = "e2-standard-2"

  validation {
    condition     = var.observer_machine_type == "e2-standard-2"
    error_message = "P174 observer VM machine type must be exactly e2-standard-2."
  }
}

variable "boot_disk_size_gb" {
  description = "Bounded boot disk size for each disposable VM."
  type        = number
  default     = 40

  validation {
    condition     = var.boot_disk_size_gb <= 40
    error_message = "P174 boot disks must not exceed 40 GB."
  }
}
