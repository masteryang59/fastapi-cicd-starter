variable "region" {
  description = "AWS region for ECR and Lambda."
  type        = string
  default     = "eu-west-1"
}

variable "github_repository" {
  description = "The GitHub repository allowed to deploy, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the owner/name form, e.g. acme/fastapi-cicd-starter."
  }
}

variable "app_name" {
  description = "Base name. Each environment gets a Lambda function called <app_name>-<environment>."
  type        = string
  default     = "shortlinks"
}

variable "environments" {
  description = "GitHub environments, one Lambda function and one deploy role each."
  type        = list(string)
  default     = ["staging", "production"]
}

variable "create_github_oidc_provider" {
  description = "Create the account's GitHub OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "bootstrap_image_tag" {
  description = <<-EOT
    Tag of an image already in the ECR repository, used to create the functions (Lambda
    can't be created without an image). See "First deploy on AWS" in the README.
  EOT
  type        = string
  default     = "bootstrap"
}

variable "memory_size" {
  description = "Lambda memory in MB (CPU scales with it)."
  type        = number
  default     = 512
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 15
}

variable "reserved_concurrency" {
  description = <<-EOT
    Concurrency cap per function, so a traffic spike can't become a bill. -1 = no cap.
    New accounts often have an account-wide limit of 10 and can't reserve any, hence the default.
  EOT
  type        = number
  default     = -1
}

variable "database_urls" {
  description = <<-EOT
    Optional PostgreSQL DATABASE_URL per environment. These end up in Terraform state and
    in the function's configuration, so protect both. Without one, the function uses SQLite
    in /tmp, which is lost whenever an execution environment is recycled.
  EOT
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "admin_api_keys" {
  description = "Optional ADMIN_API_KEY per environment (same caveat as database_urls)."
  type        = map(string)
  default     = {}
  sensitive   = true
}
variable "mask_pii" {
  type    = bool
  default = true
}
variable "mask_pii" {
  type    = bool
  default = true
}