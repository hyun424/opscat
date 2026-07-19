variable "billing_account_id" {
  description = "Reviewed billing account for the fresh P176 adoption control project."
  type        = string

  validation {
    condition     = can(regex("^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$", var.billing_account_id))
    error_message = "billing_account_id must be a GCP billing account ID."
  }
}

variable "control_project_id" {
  description = "Fresh P176 adoption control project ID."
  type        = string

  validation {
    condition     = can(regex("^opscat-p176-admin-[a-z0-9-]{6,20}$", var.control_project_id))
    error_message = "control_project_id must be a fresh opscat-p176-admin-* project."
  }
}

variable "workload_project_id" {
  description = "Existing P174 workload project ID to observe/adopt without ownership."
  type        = string

  validation {
    condition = (
      can(regex("^opscat-p174-[a-z0-9-]{6,32}$", var.workload_project_id))
      && !can(regex("(prod|production|shared-vpc)", var.workload_project_id))
    )
    error_message = "workload_project_id must be a non-prod existing opscat-p174-* workload project."
  }
}

variable "workload_project_number" {
  description = "Observed numeric project number for the existing P174 workload baseline."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{6,20}$", var.workload_project_number))
    error_message = "workload_project_number must be the numeric baseline project number."
  }
}

variable "workload_network_self_link" {
  description = "Observed P174 workload network self-link, bound to workload_project_id."
  type        = string

  validation {
    condition = (
      startswith(var.workload_network_self_link, "projects/${var.workload_project_id}/global/networks/")
      && !can(regex("(prod|production|shared-vpc)", var.workload_network_self_link))
    )
    error_message = "workload_network_self_link must be bound to workload_project_id and must not be shared/prod."
  }
}

variable "region" {
  description = "Region for P176 adoption control resources."
  type        = string
  default     = "asia-northeast3"

  validation {
    condition     = var.region == "asia-northeast3"
    error_message = "P176 adoption control resources must stay in asia-northeast3."
  }
}
