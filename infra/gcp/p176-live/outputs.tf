output "project_id" {
  description = "Frozen disposable P176 live project ID."
  value       = var.project_id
}

output "target_instance" {
  description = "Target VM self link."
  value       = google_compute_instance.target.self_link
}

output "observer_instance" {
  description = "Observer VM self link."
  value       = google_compute_instance.observer.self_link
}

output "nat_gateway" {
  description = "Bounded auto-allocated Cloud NAT used only by the P176 live subnet."
  value       = google_compute_router_nat.p176_live.id
}

output "service_accounts" {
  description = "P176 live service account split. No service-account keys are created."
  value = {
    target        = google_service_account.target.email
    observer      = google_service_account.observer.email
    harness_fault = google_service_account.harness_fault.email
    opscat        = var.opscat_principal
  }
}
