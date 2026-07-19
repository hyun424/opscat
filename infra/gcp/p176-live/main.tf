locals {
  # Static contract labels:
  # purpose   = "p176-live-lab"
  # owner     = "kdh"
  # expires_on = "20260801"
  labels = {
    purpose                 = "p176-live-lab"
    owner                   = "kdh"
    expires_on              = "20260801"
    ticket                  = "p176-live-001"
    expected_project_prefix = "opscat-p176-live-"
    ownership               = "external-cost-cutoff-foundation"
  }
}

resource "google_compute_network" "p176_live" {
  project                 = var.project_id
  name                    = "p176-live-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "p176_live" {
  project                  = var.project_id
  name                     = "p176-live-subnet"
  ip_cidr_range            = "10.176.0.0/24"
  region                   = var.region
  network                  = google_compute_network.p176_live.id
  private_ip_google_access = true
}

resource "google_compute_router" "p176_live" {
  project = var.project_id
  name    = "p176-live-router"
  network = google_compute_network.p176_live.id
  region  = var.region
}

resource "google_compute_router_nat" "p176_live" {
  project                            = var.project_id
  name                               = "p176-live-nat"
  router                             = google_compute_router.p176_live.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  min_ports_per_vm                   = 64

  subnetwork {
    name                    = google_compute_subnetwork.p176_live.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

resource "google_service_account" "target" {
  project      = var.project_id
  account_id   = "p176-live-target"
  display_name = "P176 live target VM runtime"
}

resource "google_service_account" "observer" {
  project      = var.project_id
  account_id   = "p176-live-observer"
  display_name = "P176 live observer read-only runtime"
}

resource "google_service_account" "harness_fault" {
  project      = var.project_id
  account_id   = "p176-live-harness-fault"
  display_name = "P176 live harness fault injection and cleanup"
}

resource "google_project_iam_member" "observer_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_member" "observer_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_member" "observer_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.observer.email}"
}

resource "google_project_iam_custom_role" "harness_fault_operator" {
  project     = var.project_id
  role_id     = "p176LiveHarnessFaultOperator"
  title       = "P176 Live Harness Fault Operator"
  description = "Harness-only P176 fault injection and cleanup permissions."
  permissions = [
    "compute.instances.get",
    "compute.instances.list",
    "compute.instances.start",
    "compute.instances.stop",
  ]
}

resource "google_project_iam_member" "harness_fault_operator" {
  project = var.project_id
  role    = google_project_iam_custom_role.harness_fault_operator.id
  member  = "serviceAccount:${google_service_account.harness_fault.email}"
}

resource "google_project_iam_member" "iap_ssh_admin" {
  for_each = var.ssh_admin_members

  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = each.value
}

resource "google_project_iam_member" "oslogin_admin" {
  for_each = var.ssh_admin_members

  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = each.value
}

resource "google_compute_firewall" "iap_ssh" {
  project = var.project_id
  name    = "p176-live-iap-ssh"
  network = google_compute_network.p176_live.name

  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["opscat-p176-live-target", "opscat-p176-live-observer"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "observer_to_target_private" {
  project = var.project_id
  name    = "p176-live-observer-to-target-private"
  network = google_compute_network.p176_live.name

  direction   = "INGRESS"
  source_tags = ["opscat-p176-live-observer"]
  target_tags = ["opscat-p176-live-target"]

  allow {
    protocol = "tcp"
    ports    = ["8000", "8020", "9090", "3100"]
  }
}

resource "google_compute_firewall" "bounded_web_dns_egress" {
  project = var.project_id
  name    = "p176-live-bounded-web-dns-egress"
  network = google_compute_network.p176_live.name

  direction          = "EGRESS"
  priority           = 1000
  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["opscat-p176-live-target", "opscat-p176-live-observer"]

  allow {
    protocol = "tcp"
    ports    = ["53", "80", "443"]
  }

  allow {
    protocol = "udp"
    ports    = ["53"]
  }
}

resource "google_compute_firewall" "deny_other_egress" {
  project = var.project_id
  name    = "p176-live-deny-other-egress"
  network = google_compute_network.p176_live.name

  direction          = "EGRESS"
  priority           = 1100
  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["opscat-p176-live-target", "opscat-p176-live-observer"]

  deny {
    protocol = "all"
  }
}

resource "google_compute_instance" "target" {
  project      = var.project_id
  name         = "p176-live-target"
  machine_type = var.target_machine_type
  zone         = var.zone
  tags         = ["opscat-p176-live-target"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.boot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.p176_live.id
    network_ip = "10.176.0.10"
  }

  metadata = {
    block-project-ssh-keys = "TRUE"
    enable-oslogin         = "TRUE"
    startup-script         = file("${path.module}/target-startup.sh")
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

  depends_on = [
    google_compute_router_nat.p176_live,
    google_compute_firewall.bounded_web_dns_egress,
    google_compute_firewall.deny_other_egress,
  ]
}

resource "google_compute_instance" "observer" {
  project      = var.project_id
  name         = "p176-live-observer"
  machine_type = var.observer_machine_type
  zone         = var.zone
  tags         = ["opscat-p176-live-observer"]
  labels       = local.labels

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.boot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.p176_live.id
    network_ip = "10.176.0.20"
  }

  metadata = {
    block-project-ssh-keys = "TRUE"
    enable-oslogin         = "TRUE"
    startup-script         = file("${path.module}/observer-startup.sh")
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

  depends_on = [
    google_compute_router_nat.p176_live,
    google_compute_firewall.bounded_web_dns_egress,
    google_compute_firewall.deny_other_egress,
  ]
}
