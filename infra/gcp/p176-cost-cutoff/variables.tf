variable "admin_project_id" {
  description = "Fresh explicitly non-production, non-lab admin project that hosts the out-of-band P176 cost cutoff controller."
  type        = string

  validation {
    condition = (
      can(regex("^opscat-p176-admin-[a-z0-9-]{6,20}$", var.admin_project_id)) &&
      length(regexall("(prod|production|shared-vpc|lab|live)", var.admin_project_id)) == 0
    )
    error_message = "admin_project_id must be a dedicated opscat-p176-admin-* non-production, non-lab admin project and must not match lab-hosted controller, production, shared-vpc, or live/lab patterns."
  }
}

variable "org_id" {
  description = "GCP organization ID that will own the fresh dedicated admin project. Supplied locally in terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{6,32}$", var.org_id))
    error_message = "org_id must be supplied from local terraform.tfvars as a numeric GCP organization ID."
  }
}

variable "lab_project_id" {
  description = "Separate disposable P176 lab project controlled by the out-of-band admin project."
  type        = string

  validation {
    condition     = can(regex("^opscat-p176-live-[a-z0-9-]{6,20}$", var.lab_project_id))
    error_message = "lab_project_id must be a separate disposable opscat-p176-live-* lab project."
  }
}

variable "billing_account_id" {
  description = "Billing account attached to the disposable lab project."
  type        = string

  validation {
    condition     = can(regex("^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$", var.billing_account_id))
    error_message = "billing_account_id must be supplied from local terraform.tfvars as a GCP billing account ID."
  }
}

variable "region" {
  description = "Region for Eventarc, Workflows, Scheduler, and the receipt bucket."
  type        = string
  default     = "asia-northeast3"

  validation {
    condition     = var.region == "asia-northeast3"
    error_message = "P176 cost cutoff control plane must stay in asia-northeast3."
  }
}

variable "soft_stop_krw" {
  description = "Soft stop threshold; stop compute but leave billing attached."
  type        = number
  default     = 24000

  validation {
    condition     = var.soft_stop_krw == 24000
    error_message = "P176 soft stop must be exactly 24000 KRW."
  }
}

variable "hard_cutoff_krw" {
  description = "Hard cutoff threshold; stop compute before disabling billing."
  type        = number
  default     = 27000

  validation {
    condition     = var.hard_cutoff_krw == 27000
    error_message = "P176 hard cutoff must be exactly 27000 KRW."
  }
}

variable "budget_krw" {
  description = "Budget amount used by the lab-side billing budget."
  type        = number
  default     = 30000

  validation {
    condition     = var.budget_krw == 30000
    error_message = "P176 budget must be exactly 30000 KRW."
  }
}

variable "budget_alert_email" {
  description = "Email address that receives P176 lab budget alerts."
  type        = string
}

variable "stale_after_seconds" {
  description = "Budget notification age after which the workflow refuses to act."
  type        = number
  default     = 600

  validation {
    condition     = var.stale_after_seconds == 600
    error_message = "P176 stale notification threshold must be exactly 600 seconds."
  }
}

variable "terminal_ttl_seconds" {
  description = "Terminal receipt lifecycle in seconds; 36 hours."
  type        = number
  default     = 129600

  validation {
    condition     = var.terminal_ttl_seconds == 129600
    error_message = "P176 terminal TTL must be exactly 36 hours."
  }
}

variable "absolute_lease_seconds" {
  description = "Absolute dedupe lease TTL in seconds; 48 hours."
  type        = number
  default     = 172800

  validation {
    condition     = var.absolute_lease_seconds == 172800
    error_message = "P176 absolute lease must be exactly 48 hours."
  }
}

variable "scheduler_time_zone" {
  description = "Time zone for the 5-minute scheduler fallback."
  type        = string
  default     = "Etc/UTC"
}
