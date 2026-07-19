output "control_project_id" {
  value = google_project.p176_adoption_control.project_id
}

output "harness_control_principal" {
  value = google_service_account.harness.email
}

output "evidence_topic" {
  value = google_pubsub_topic.evidence.id
}
