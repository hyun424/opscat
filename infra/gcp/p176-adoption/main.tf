locals {
  labels = {
    purpose                 = "p176-workload-adoption"
    owner                   = "kdh"
    ticket                  = "p176-adoption-001"
    expected_project_prefix = "opscat-p176-admin-"
    adopted_workload_prefix = "opscat-p174-"
    adoption_owns_workload  = "false"
  }
}

resource "google_project" "p176_adoption_control" {
  name            = var.control_project_id
  project_id      = var.control_project_id
  billing_account = var.billing_account_id
  labels          = local.labels
}

resource "google_project_service" "control_pubsub" {
  project            = google_project.p176_adoption_control.project_id
  service            = "pubsub.googleapis.com"
  disable_on_destroy = true
}

resource "google_project_service" "control_logging" {
  project            = google_project.p176_adoption_control.project_id
  service            = "logging.googleapis.com"
  disable_on_destroy = true
}

resource "google_compute_network" "p176_adoption_control" {
  project                 = google_project.p176_adoption_control.project_id
  name                    = "p176-adoption-control-vpc"
  auto_create_subnetworks = false
}

resource "google_service_account" "harness" {
  project      = google_project.p176_adoption_control.project_id
  account_id   = "p176-adoption-harness"
  display_name = "P176 adoption control harness"
}

resource "google_pubsub_topic" "evidence" {
  project = google_project.p176_adoption_control.project_id
  name    = "p176-adoption-evidence"
  labels  = local.labels

  depends_on = [google_project_service.control_pubsub]
}

resource "google_pubsub_topic_iam_member" "harness_evidence_publisher" {
  project = google_project.p176_adoption_control.project_id
  topic   = google_pubsub_topic.evidence.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.harness.email}"
}

resource "google_project_iam_member" "harness_log_writer" {
  project = google_project.p176_adoption_control.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.harness.email}"
}

resource "google_logging_project_sink" "baseline_receipts" {
  project                = google_project.p176_adoption_control.project_id
  name                   = "p176-adoption-baseline-receipts"
  destination            = "pubsub.googleapis.com/${google_pubsub_topic.evidence.id}"
  filter                 = "resource.type=\"audited_resource\""
  unique_writer_identity = true

  depends_on = [google_project_service.control_logging]
}

output "adoption_binding" {
  value = {
    mode                       = "p174_workload_adoption"
    control_project_id         = google_project.p176_adoption_control.project_id
    workload_project_id        = var.workload_project_id
    workload_project_number    = var.workload_project_number
    workload_network_self_link = var.workload_network_self_link
    adoption_owns_workload     = false
    workload_project_delete_ok = false
    harness_control_principal  = google_service_account.harness.email
    evidence_topic             = google_pubsub_topic.evidence.id
  }
}
