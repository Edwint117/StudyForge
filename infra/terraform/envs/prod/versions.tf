terraform {
  required_version = ">= 1.13.5, < 2.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
  backend "gcs" {}
}

provider "google" {
  project                     = var.project_id
  region                      = var.region
  impersonate_service_account = "sf-deployer@${var.project_id}.iam.gserviceaccount.com"
  default_labels = {
    app         = "studyforge"
    environment = "production"
    managed_by  = "terraform"
  }
}
