terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 6.28 added `invoked_via_function_url` to aws_lambda_permission.
      version = "~> 6.28"
    }
  }

  # Keep state somewhere shared before a team uses this, e.g.:
  # backend "s3" {
  #   bucket       = "my-tf-state"
  #   key          = "fastapi-cicd-starter/terraform.tfstate"
  #   region       = "eu-west-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      app        = var.app_name
      managed-by = "terraform"
      repository = var.github_repository
    }
  }
}
variable "audit_action" {
  type    = bool
  default = true
}
variable "audit_action" {
  type    = bool
  default = true
}