output "project_id" {
  description = "Frozen disposable P174 project ID."
  value       = google_project.p174.project_id
}

output "project_number" {
  description = "Numeric project identifier for budget and audit evidence."
  value       = google_project.p174.number
}

output "target_instance" {
  description = "Target VM self link."
  value       = google_compute_instance.target.self_link
}

output "observer_instance" {
  description = "Observer VM self link."
  value       = google_compute_instance.observer.self_link
}

output "service_accounts" {
  description = "VM-attached service accounts. Containers do not receive per-container GCP identities."
  value = {
    target   = google_service_account.target.email
    observer = google_service_account.observer.email
  }
}
