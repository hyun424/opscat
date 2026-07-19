locals {
  # Static contract labels:
  # purpose   = "opscat-lab"
  # owner     = "p174-lab"
  # expires_on = "20260801"
  labels = {
    purpose    = "opscat-lab"
    owner      = "p174-lab"
    expires_on = "20260801"
    ticket     = "p174"
  }

  required_services = toset([
    "billingbudgets.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "oslogin.googleapis.com",
  ])
}

resource "google_project" "p174" {
  name                = var.project_name
  project_id          = var.project_id
  org_id              = var.organization_id
  billing_account     = var.billing_account_id
  auto_create_network = false
  deletion_policy     = "DELETE"
  labels              = local.labels
}

resource "google_project_service" "p174" {
  for_each = local.required_services

  project            = google_project.p174.project_id
  service            = each.value
  disable_on_destroy = true
}

resource "google_monitoring_notification_channel" "budget_email" {
  project      = google_project.p174.project_id
  display_name = "P174 budget email"
  type         = "email"
  labels = {
    email_address = var.budget_alert_email
  }
  user_labels = local.labels

  depends_on = [google_project_service.p174]
}

resource "google_billing_budget" "p174" {
  provider        = google.p174_quota
  billing_account = var.billing_account_id
  display_name    = "P174 disposable lab budget"

  budget_filter {
    projects = ["projects/${google_project.p174.number}"]
  }

  amount {
    specified_amount {
      currency_code = "KRW"
      units         = tostring(var.budget_amount_krw)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.75
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.budget_email.id]
    disable_default_iam_recipients   = true
  }
}

resource "google_compute_network" "p174" {
  project                 = google_project.p174.project_id
  name                    = "p174-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.p174]
}

resource "google_compute_subnetwork" "p174" {
  project                  = google_project.p174.project_id
  name                     = "p174-subnet"
  ip_cidr_range            = "10.174.0.0/24"
  region                   = var.region
  network                  = google_compute_network.p174.id
  private_ip_google_access = true
}

resource "google_service_account" "target" {
  project      = google_project.p174.project_id
  account_id   = "p174-target"
  display_name = "P174 target VM runtime"
}

resource "google_service_account" "observer" {
  project      = google_project.p174.project_id
  account_id   = "p174-observer"
  display_name = "P174 observer read-only runtime"
}

resource "google_project_iam_member" "observer_compute_viewer" {
  project = google_project.p174.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_member" "observer_logging_viewer" {
  project = google_project.p174.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_member" "observer_monitoring_viewer" {
  project = google_project.p174.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_member" "iap_ssh_admin" {
  for_each = var.ssh_admin_members

  project = google_project.p174.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = each.value
}

resource "google_project_iam_member" "oslogin_admin" {
  for_each = var.ssh_admin_members

  project = google_project.p174.project_id
  role    = "roles/compute.osAdminLogin"
  member  = each.value
}

resource "google_compute_firewall" "iap_ssh" {
  project = google_project.p174.project_id
  name    = "p174-iap-ssh"
  network = google_compute_network.p174.name

  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["opscat-target", "opscat-observer"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "observer_to_target_private" {
  project = google_project.p174.project_id
  name    = "p174-observer-to-target-private"
  network = google_compute_network.p174.name

  direction   = "INGRESS"
  source_tags = ["opscat-observer"]
  target_tags = ["opscat-target"]

  allow {
    protocol = "tcp"
    ports    = ["8000", "8020", "9090", "3100"]
  }
}

resource "google_compute_instance" "target" {
  project      = google_project.p174.project_id
  name         = "p174-target"
  machine_type = var.target_machine_type
  zone         = var.zone
  tags         = ["opscat-target"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.boot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.p174.id
    network_ip = "10.174.0.10"

    access_config {
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
    startup-script = file("${path.module}/target-startup.sh")
  }

  service_account {
    email  = google_service_account.target.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }
}

resource "google_compute_instance" "observer" {
  project      = google_project.p174.project_id
  name         = "p174-observer"
  machine_type = var.observer_machine_type
  zone         = var.zone
  tags         = ["opscat-observer"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.boot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.p174.id
    network_ip = "10.174.0.20"

    access_config {
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
    startup-script = file("${path.module}/observer-startup.sh")
  }

  service_account {
    email  = google_service_account.observer.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }
}
