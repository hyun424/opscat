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
}

provider "google" {
  alias                 = "p176_cost_quota"
  region                = var.region
  billing_project       = var.admin_project_id
  user_project_override = true
}
