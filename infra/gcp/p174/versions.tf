terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  region = var.region
  zone   = var.zone
}

provider "google" {
  alias                 = "p174_quota"
  region                = var.region
  zone                  = var.zone
  billing_project       = var.project_id
  user_project_override = true
}
