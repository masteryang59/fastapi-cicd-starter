terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }

  # Keep state somewhere shared before a team uses this, e.g.:
  # backend "gcs" {
  #   bucket = "my-tf-state"
  #   prefix = "fastapi-cicd-starter"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
variable "invalidate_cache" {
  type    = bool
  default = true
}
variable "invalidate_cache" {
  type    = bool
  default = true
}