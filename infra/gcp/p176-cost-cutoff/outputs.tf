output "budget_topic_name" {
  description = "External admin-project Pub/Sub topic name to bind from the lab budget."
  value       = google_pubsub_topic.budget_notifications.id
}

output "lab_project_id" {
  description = "Disposable P176 lab project owned by the cost-cutoff foundation."
  value       = google_project.lab.project_id
}

output "workflow_name" {
  description = "Out-of-band cutoff workflow resource name."
  value       = google_workflows_workflow.cutoff.id
}

output "receipt_bucket" {
  description = "Immutable/minimal GCS receipt bucket for leases and terminal receipts."
  value       = google_storage_bucket.receipts.name
}

output "service_accounts" {
  description = "Dedicated control-plane service accounts; no keys are created."
  value = {
    workflow  = google_service_account.workflow.email
    eventarc  = google_service_account.eventarc.email
    scheduler = google_service_account.scheduler.email
  }
}
